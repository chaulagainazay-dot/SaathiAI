"""M17.9 JSONL → run-ledger migration (safe, reversible, provenance-preserving).

The M17.8 append-only JSONL journal is treated as READ-ONLY legacy: it is never
mutated. `migrate_jsonl` backs the file up, imports each legacy run into the SQLite
ledger with `origin='migrated_jsonl'`, preserves timestamps + terminal results,
rejects malformed records safely, and is idempotent (a re-run imports nothing new).
`rollback` removes only the migrated rows, restoring the ledger to its pre-migration
state. No secrets are imported (records carry only pid/pgid/harness/owner/state).
"""
from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

from saathi.application_harness import run_ledger as L


def _read_legacy(path: Path) -> tuple[list[dict], int]:
    """Return (valid records, malformed count). A torn/invalid line is skipped,
    never imported — malformed record injection fails closed."""
    records, bad = [], 0
    if not path.exists():
        return records, bad
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            bad += 1
            continue
        if not isinstance(obj, dict) or not obj.get("run_id"):
            bad += 1
            continue
        records.append(obj)
    return records, bad


def _fold(records: list[dict]) -> dict[str, dict]:
    """Fold the append-only log into one final row per run_id (last write wins
    for state; first start carries pid/owner/harness + created_at)."""
    runs: dict[str, dict] = {}
    for r in records:
        rid = r["run_id"]
        cur = runs.setdefault(rid, {"run_id": rid, "created_at": r.get("ts"),
                                    "owner": "", "harness_id": "", "pid": None,
                                    "pgid": None, "state": None, "exit_code": None,
                                    "terminal_at": None})
        if r.get("event") == "start":
            cur["owner"] = r.get("owner", cur["owner"])
            cur["harness_id"] = r.get("harness_id", cur["harness_id"])
            cur["pid"] = r.get("pid", cur["pid"])
            cur["pgid"] = r.get("pgid", cur["pgid"])
            cur["created_at"] = cur["created_at"] or r.get("ts")
            cur["state"] = cur["state"] or "running"
        # last state wins
        st = r.get("state")
        if st:
            cur["state"] = st
        if r.get("event") == "end":
            cur["exit_code"] = r.get("exit_code")
            cur["terminal_at"] = r.get("ts")
    return runs


def _import_run(ledger: L.RunLedger, run: dict, *, is_alive) -> str | None:
    """Insert a single historical run directly at its final state (bypassing the
    live state machine — these are settled facts), refusing to overwrite an
    existing run_id. Returns the ledger state written, or None if skipped."""
    rid = run["run_id"]
    if not isinstance(rid, str) or L._CTRL.search(rid):
        return None
    if ledger.inspect(rid) is not None:
        return None                            # idempotent: already imported/live
    legacy_state = run.get("state") or "running"
    state = L._LEGACY_STATE.get(legacy_state, legacy_state)
    if state == L.RUNNING:
        # a run left 'running' in the legacy log with a dead pid is a crash
        state = L.RUNNING if is_alive(run.get("pid")) else L.CRASH_RECOVERED
    if state not in L.ALL_STATES:
        return None                            # unknown legacy state — reject
    owner = L._clean_str(run.get("owner") or "legacy", field="owner")
    created = run.get("created_at") or L._now()
    terminal = run.get("terminal_at") or (created if state in L.TERMINAL else 0)
    ver = 1 if state in L.ACTIVE else 2
    recovery = "crash_reconciled" if state == L.CRASH_RECOVERED else "none"
    c = ledger._conn()
    try:
        c.execute("BEGIN IMMEDIATE")
        try:
            c.execute(
                "INSERT INTO run(run_id,owner,harness_id,pid,pgid,state,state_version,"
                "created_at,started_at,terminal_at,exit_code,recovery_status,origin) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (rid, owner, L._clean_str(run.get("harness_id") or "", field="harness_id"),
                 run.get("pid"), run.get("pgid"), state, ver, created, created,
                 terminal, run.get("exit_code"), recovery, "migrated_jsonl"))
        except Exception:
            c.execute("ROLLBACK")
            return None
        c.execute("INSERT INTO run_transition(run_id,from_state,to_state,state_version,"
                  "actor,reason,ts) VALUES(?,?,?,?,?,?,?)",
                  (rid, None, state, ver, "migration", "migrated_jsonl", created))
        c.execute("COMMIT")
    finally:
        c.close()
    return state


def migrate_jsonl(jsonl_path, ledger: L.RunLedger, *, backup_dir=None,
                  is_alive=None) -> dict:
    """Back up the legacy JSONL, import every well-formed run into the ledger,
    and report provenance. Legacy file is left untouched (read-only compat)."""
    alive = is_alive or L._pid_alive
    src = Path(jsonl_path)
    records, malformed = _read_legacy(src)
    backup = None
    if src.exists():
        bdir = Path(backup_dir) if backup_dir else src.parent
        bdir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        backup = bdir / f"{src.name}.pre-m17_9.{stamp}.bak"
        shutil.copy2(src, backup)              # provenance-preserving backup
    runs = _fold(records)
    imported, skipped = [], 0
    for run in runs.values():
        st = _import_run(ledger, run, is_alive=alive)
        if st:
            imported.append(run["run_id"])
        else:
            skipped += 1
    ledger._event("harness.ledger.migrated",
                  {"imported": len(imported), "malformed": malformed})
    return {"backup": str(backup) if backup else None,
            "source": str(src), "records_read": len(records),
            "malformed_rejected": malformed, "runs_folded": len(runs),
            "imported": imported, "skipped": skipped, "reversible": True}


def rollback(ledger: L.RunLedger) -> dict:
    """Reverse a migration: delete only rows imported from JSONL. Live/native
    ledger runs are untouched."""
    c = ledger._conn()
    try:
        c.execute("BEGIN IMMEDIATE")
        ids = [r["run_id"] for r in c.execute(
            "SELECT run_id FROM run WHERE origin='migrated_jsonl'").fetchall()]
        for rid in ids:
            c.execute("DELETE FROM run_transition WHERE run_id=? AND reason='migrated_jsonl'",
                      (rid,))
            c.execute("DELETE FROM run WHERE run_id=? AND origin='migrated_jsonl'", (rid,))
        c.execute("COMMIT")
    finally:
        c.close()
    return {"rolled_back": len(ids), "run_ids": ids}
