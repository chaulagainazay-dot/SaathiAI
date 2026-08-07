"""M62.4 — single-host SQLite persistence for strategy + backtest evidence.

Tenant-scoped by org_id. Strategy definitions carry an optimistic-concurrency
version. Strategy VERSIONS and COMPLETED backtest manifests are immutable — the
store refuses to mutate them. Not multi-node safe; distributed mode disabled.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time as _time
from pathlib import Path
from typing import Any

from saathi.platform.models import new_id


def _dumps(obj) -> str:
    return json.dumps(obj, default=str)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS strat_defs (
    strategy_id TEXT PRIMARY KEY, org_id TEXT NOT NULL, workspace_id TEXT NOT NULL,
    name TEXT NOT NULL, definition_json TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'DRAFT',
    created_by TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1, created_at REAL NOT NULL, updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS strat_versions (
    strategy_id TEXT NOT NULL, version INTEGER NOT NULL, org_id TEXT NOT NULL,
    code_hash TEXT NOT NULL, config_json TEXT NOT NULL, parameters_json TEXT NOT NULL DEFAULT '{}',
    dataset_req_json TEXT NOT NULL DEFAULT '{}', parent_version INTEGER, change_rationale TEXT NOT NULL DEFAULT '',
    created_by TEXT NOT NULL, created_at REAL NOT NULL, validation_state TEXT NOT NULL DEFAULT 'UNVALIDATED',
    PRIMARY KEY (strategy_id, version)
);
CREATE TABLE IF NOT EXISTS strat_datasets (
    dataset_id TEXT PRIMARY KEY, org_id TEXT NOT NULL, provider TEXT NOT NULL, dataset_version TEXT NOT NULL,
    instrument TEXT NOT NULL, timeframe TEXT NOT NULL, start_epoch REAL NOT NULL, end_epoch REAL NOT NULL,
    content_hash TEXT NOT NULL, source TEXT NOT NULL, calendar TEXT NOT NULL, bar_count INTEGER NOT NULL DEFAULT 0,
    quality_json TEXT NOT NULL DEFAULT '{}', created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS strat_backtests (
    run_id TEXT PRIMARY KEY, org_id TEXT NOT NULL, workspace_id TEXT NOT NULL, strategy_id TEXT NOT NULL,
    strategy_version INTEGER NOT NULL, dataset_id TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'DRAFT',
    seed INTEGER NOT NULL DEFAULT 0, config_json TEXT NOT NULL DEFAULT '{}', manifest_json TEXT NOT NULL DEFAULT '{}',
    result_hash TEXT NOT NULL DEFAULT '', engine_version TEXT NOT NULL DEFAULT '', correlation_id TEXT NOT NULL DEFAULT '',
    completed INTEGER NOT NULL DEFAULT 0, version INTEGER NOT NULL DEFAULT 1,
    created_by TEXT NOT NULL, started_at REAL NOT NULL DEFAULT 0, completed_at REAL NOT NULL DEFAULT 0, created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS strat_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL, org_id TEXT NOT NULL, seq INTEGER NOT NULL,
    order_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS strat_equity (
    id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL, org_id TEXT NOT NULL, epoch REAL NOT NULL,
    point_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS strat_results (
    run_id TEXT NOT NULL, org_id TEXT NOT NULL, kind TEXT NOT NULL, payload_json TEXT NOT NULL,
    PRIMARY KEY (run_id, kind)
);
CREATE INDEX IF NOT EXISTS idx_sv_strat ON strat_versions(org_id, strategy_id, version DESC);
CREATE INDEX IF NOT EXISTS idx_bt_strat ON strat_backtests(org_id, strategy_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ord_run ON strat_orders(org_id, run_id, seq);
CREATE INDEX IF NOT EXISTS idx_eq_run ON strat_equity(org_id, run_id, epoch);
"""


class StrategyStore:
    def __init__(self, db_path: str | Path | None = None):
        env = os.environ.get("SAATHI_STRATEGY_DB") or os.environ.get("SAATHI_PLATFORM_DB", "")
        default = Path(__file__).resolve().parents[3] / "data" / "platform" / "platform.db"
        self.db_path = Path(db_path) if db_path else (Path(env) if env else default)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    @staticmethod
    def _j(v, default="{}"):
        try:
            return json.loads(v or default)
        except Exception:
            return json.loads(default)

    # ── strategy definitions ─────────────────────────────────────────────
    def create_strategy(self, *, org_id, workspace_id, name, definition: dict, created_by) -> dict:
        sid = new_id("strat_")
        ts = _time.time()
        self._conn.execute(
            "INSERT INTO strat_defs (strategy_id, org_id, workspace_id, name, definition_json, status,"
            " created_by, version, created_at, updated_at) VALUES (?,?,?,?,?,?,?,1,?,?)",
            (sid, org_id, workspace_id, name, _dumps(definition), definition.get("status", "DRAFT"),
             created_by, ts, ts))
        self._conn.commit()
        return self.get_strategy(org_id, sid)

    def get_strategy(self, org_id, sid) -> dict | None:
        r = self._conn.execute("SELECT * FROM strat_defs WHERE org_id=? AND strategy_id=?", (org_id, sid)).fetchone()
        if not r:
            return None
        d = dict(r); d["definition"] = self._j(d.pop("definition_json")); return d

    def list_strategies(self, org_id, *, limit=200) -> list[dict]:
        rows = self._conn.execute(
            "SELECT strategy_id, name, status, version, created_at FROM strat_defs WHERE org_id=?"
            " ORDER BY created_at DESC LIMIT ?", (org_id, int(limit))).fetchall()
        return [dict(r) for r in rows]

    def update_strategy(self, org_id, sid, *, expected_version, definition=None, status=None) -> tuple[str, dict | None]:
        cur = self.get_strategy(org_id, sid)
        if not cur:
            return ("not_found", None)
        if int(expected_version) != int(cur["version"]):
            return ("conflict", cur)
        new_def = definition if definition is not None else cur["definition"]
        new_status = status or new_def.get("status") or cur["status"]
        new_def["status"] = new_status
        self._conn.execute(
            "UPDATE strat_defs SET definition_json=?, status=?, version=?, updated_at=? WHERE strategy_id=?",
            (_dumps(new_def), new_status, int(cur["version"]) + 1, _time.time(), sid))
        self._conn.commit()
        return ("ok", self.get_strategy(org_id, sid))

    # ── immutable versions ───────────────────────────────────────────────
    def add_version(self, org_id, sid, *, code_hash, config: dict, parameters: dict, dataset_req: dict,
                    parent_version=None, rationale="", created_by="") -> dict:
        prev = self.latest_version(org_id, sid)
        version = (prev["version"] + 1) if prev else 1
        self._conn.execute(
            "INSERT INTO strat_versions (strategy_id, version, org_id, code_hash, config_json, parameters_json,"
            " dataset_req_json, parent_version, change_rationale, created_by, created_at, validation_state)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,'UNVALIDATED')",
            (sid, version, org_id, code_hash, _dumps(config), _dumps(parameters), _dumps(dataset_req),
             parent_version, rationale, created_by, _time.time()))
        self._conn.commit()
        return self.get_version(org_id, sid, version)

    def get_version(self, org_id, sid, version) -> dict | None:
        r = self._conn.execute("SELECT * FROM strat_versions WHERE org_id=? AND strategy_id=? AND version=?",
                               (org_id, sid, version)).fetchone()
        if not r:
            return None
        d = dict(r); d["config"] = self._j(d.pop("config_json")); d["parameters"] = self._j(d.pop("parameters_json"))
        d["dataset_req"] = self._j(d.pop("dataset_req_json")); return d

    def latest_version(self, org_id, sid) -> dict | None:
        r = self._conn.execute("SELECT * FROM strat_versions WHERE org_id=? AND strategy_id=? ORDER BY version DESC LIMIT 1",
                               (org_id, sid)).fetchone()
        if not r:
            return None
        d = dict(r); d["config"] = self._j(d.pop("config_json")); d["parameters"] = self._j(d.pop("parameters_json"))
        d["dataset_req"] = self._j(d.pop("dataset_req_json")); return d

    def list_versions(self, org_id, sid) -> list[dict]:
        rows = self._conn.execute(
            "SELECT strategy_id, version, code_hash, parent_version, change_rationale, created_by, created_at,"
            " validation_state FROM strat_versions WHERE org_id=? AND strategy_id=? ORDER BY version",
            (org_id, sid)).fetchall()
        return [dict(r) for r in rows]

    def set_version_validation(self, org_id, sid, version, state) -> None:
        self._conn.execute("UPDATE strat_versions SET validation_state=? WHERE org_id=? AND strategy_id=? AND version=?",
                           (state, org_id, sid, version))
        self._conn.commit()

    # ── datasets ─────────────────────────────────────────────────────────
    def add_dataset(self, org_id, ref: dict) -> str:
        did = new_id("ds_")
        self._conn.execute(
            "INSERT INTO strat_datasets (dataset_id, org_id, provider, dataset_version, instrument, timeframe,"
            " start_epoch, end_epoch, content_hash, source, calendar, bar_count, quality_json, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (did, org_id, ref["provider"], ref["dataset_version"], ref["instrument"], ref["timeframe"],
             ref["start_epoch"], ref["end_epoch"], ref["content_hash"], ref["source"], ref["calendar"],
             ref.get("bar_count", 0), _dumps(ref.get("quality_summary", {})), _time.time()))
        self._conn.commit()
        return did

    def get_dataset(self, org_id, did) -> dict | None:
        r = self._conn.execute("SELECT * FROM strat_datasets WHERE org_id=? AND dataset_id=?", (org_id, did)).fetchone()
        if not r:
            return None
        d = dict(r); d["quality_summary"] = self._j(d.pop("quality_json")); return d

    # ── backtest runs ────────────────────────────────────────────────────
    def create_run(self, *, org_id, workspace_id, strategy_id, strategy_version, dataset_id, config: dict,
                   seed=0, created_by, correlation_id="") -> dict:
        rid = new_id("bt_")
        ts = _time.time()
        self._conn.execute(
            "INSERT INTO strat_backtests (run_id, org_id, workspace_id, strategy_id, strategy_version, dataset_id,"
            " status, seed, config_json, correlation_id, completed, version, created_by, created_at)"
            " VALUES (?,?,?,?,?,?,'DRAFT',?,?,?,0,1,?,?)",
            (rid, org_id, workspace_id, strategy_id, strategy_version, dataset_id, seed, _dumps(config),
             correlation_id, created_by, ts))
        self._conn.commit()
        return self.get_run(org_id, rid)

    def get_run(self, org_id, rid) -> dict | None:
        r = self._conn.execute("SELECT * FROM strat_backtests WHERE org_id=? AND run_id=?", (org_id, rid)).fetchone()
        if not r:
            return None
        d = dict(r); d["config"] = self._j(d.pop("config_json")); d["manifest"] = self._j(d.pop("manifest_json")); return d

    def list_runs(self, org_id, *, strategy_id=None, limit=100) -> list[dict]:
        if strategy_id:
            rows = self._conn.execute(
                "SELECT run_id, strategy_id, strategy_version, status, result_hash, created_at FROM strat_backtests"
                " WHERE org_id=? AND strategy_id=? ORDER BY created_at DESC LIMIT ?",
                (org_id, strategy_id, int(limit))).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT run_id, strategy_id, strategy_version, status, result_hash, created_at FROM strat_backtests"
                " WHERE org_id=? ORDER BY created_at DESC LIMIT ?", (org_id, int(limit))).fetchall()
        return [dict(r) for r in rows]

    def update_run_status(self, org_id, rid, *, expected_version, status) -> tuple[str, dict | None]:
        cur = self.get_run(org_id, rid)
        if not cur:
            return ("not_found", None)
        if cur["completed"]:
            return ("immutable", cur)   # completed run manifests are frozen
        if int(expected_version) != int(cur["version"]):
            return ("conflict", cur)
        self._conn.execute("UPDATE strat_backtests SET status=?, version=?, started_at=CASE WHEN started_at=0 THEN ? ELSE started_at END"
                           " WHERE run_id=?", (status, int(cur["version"]) + 1, _time.time(), rid))
        self._conn.commit()
        return ("ok", self.get_run(org_id, rid))

    def finalize_run(self, org_id, rid, *, status, manifest: dict, result_hash, engine_version) -> tuple[str, dict | None]:
        cur = self.get_run(org_id, rid)
        if not cur:
            return ("not_found", None)
        if cur["completed"]:
            return ("immutable", cur)
        self._conn.execute(
            "UPDATE strat_backtests SET status=?, manifest_json=?, result_hash=?, engine_version=?, completed=1,"
            " version=version+1, completed_at=? WHERE run_id=?",
            (status, _dumps(manifest), result_hash, engine_version, _time.time(), rid))
        self._conn.commit()
        return ("ok", self.get_run(org_id, rid))

    # ── run artifacts (bounded) ──────────────────────────────────────────
    def save_orders(self, org_id, rid, orders: list[dict], *, cap: int = 5000) -> None:
        for o in orders[:cap]:
            self._conn.execute("INSERT INTO strat_orders (run_id, org_id, seq, order_json) VALUES (?,?,?,?)",
                               (rid, org_id, o.get("seq", 0), _dumps(o)))
        self._conn.commit()

    def list_orders(self, org_id, rid, *, limit=1000, offset=0) -> list[dict]:
        rows = self._conn.execute("SELECT order_json FROM strat_orders WHERE org_id=? AND run_id=? ORDER BY seq LIMIT ? OFFSET ?",
                                  (org_id, rid, int(limit), int(offset))).fetchall()
        return [self._j(r["order_json"]) for r in rows]

    def save_equity(self, org_id, rid, points: list[dict], *, cap: int = 20000) -> None:
        for p in points[:cap]:
            self._conn.execute("INSERT INTO strat_equity (run_id, org_id, epoch, point_json) VALUES (?,?,?,?)",
                               (rid, org_id, p.get("epoch", 0.0), _dumps(p)))
        self._conn.commit()

    def list_equity(self, org_id, rid, *, limit=5000, offset=0) -> list[dict]:
        rows = self._conn.execute("SELECT point_json FROM strat_equity WHERE org_id=? AND run_id=? ORDER BY epoch LIMIT ? OFFSET ?",
                                  (org_id, rid, int(limit), int(offset))).fetchall()
        return [self._j(r["point_json"]) for r in rows]

    def save_result(self, org_id, rid, kind: str, payload: dict) -> None:
        self._conn.execute("INSERT OR REPLACE INTO strat_results (run_id, org_id, kind, payload_json) VALUES (?,?,?,?)",
                           (rid, org_id, kind, _dumps(payload)))
        self._conn.commit()

    def get_result(self, org_id, rid, kind: str) -> dict | None:
        r = self._conn.execute("SELECT payload_json FROM strat_results WHERE org_id=? AND run_id=? AND kind=?",
                               (org_id, rid, kind)).fetchone()
        return self._j(r["payload_json"]) if r else None
