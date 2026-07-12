"""M17.8 harness run journal — durable long-running-task records + crash recovery.

An append-only JSONL journal of harness process runs. A run gets a "running"
record BEFORE the adapter blocks on the process, and a terminal record
(success/failed/timeout/cancelled) when it ends. If the host crashes mid-run, the
"running" record survives with no terminal peer; on the next boot `reconcile()`
detects it (the recorded PID is no longer alive) and appends a terminal
`crash_recovered` record — turning a silent interrupted run into explicit incident
evidence instead of a dangling unknown state.

Journal is single-process append-only; concurrent writers are serialized by a
lock. Records are small and PID/pgid-scoped — no command output or secrets.
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

_TERMINAL = {"success", "failed", "timeout", "cancelled", "crash_recovered"}
ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_STORE = ROOT / "data" / "application_harness_runs" / "journal.jsonl"


def _now() -> float:
    return round(time.time(), 3)


class RunJournal:
    def __init__(self, store_path: str | os.PathLike | None = None):
        self.path = Path(store_path) if store_path else DEFAULT_STORE
        self._lock = threading.Lock()

    # ── writes ───────────────────────────────────────────────────────────────
    def _append(self, rec: dict) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "a") as f:
                f.write(json.dumps(rec, separators=(",", ":")) + "\n")
                f.flush()
                os.fsync(f.fileno())

    def record_start(self, run_id: str, *, harness_id: str, owner: str,
                     pid: int, pgid: int | None) -> None:
        self._append({"run_id": run_id, "event": "start", "state": "running",
                      "harness_id": harness_id, "owner": owner, "pid": pid,
                      "pgid": pgid, "ts": _now()})

    def record_end(self, run_id: str, state: str, exit_code: int | None) -> None:
        self._append({"run_id": run_id, "event": "end", "state": state,
                      "exit_code": exit_code, "ts": _now()})

    # ── reads ────────────────────────────────────────────────────────────────
    def _records(self) -> list[dict]:
        if not self.path.exists():
            return []
        out = []
        for line in self.path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                continue   # a torn final line (crash mid-write) is skipped
        return out

    def latest_state(self, run_id: str) -> str | None:
        st = None
        for r in self._records():
            if r.get("run_id") == run_id:
                st = r.get("state")
        return st

    def active_runs(self) -> list[dict]:
        """Runs whose most recent record is still 'running' (no terminal peer)."""
        last: dict[str, dict] = {}
        for r in self._records():
            rid = r.get("run_id")
            if rid:
                last[rid] = r
        return [r for r in last.values() if r.get("state") == "running"]

    # ── crash recovery ───────────────────────────────────────────────────────
    def reconcile(self, *, is_alive=None) -> list[str]:
        """Append a `crash_recovered` terminal record for every run left
        'running' whose process is no longer alive. Returns the reconciled ids."""
        alive = is_alive or _pid_alive
        recovered = []
        for r in self.active_runs():
            pid = r.get("pid")
            if pid is None or not alive(pid):
                self.record_end(r["run_id"], "crash_recovered", None)
                recovered.append(r["run_id"])
        return recovered


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True      # exists but not ours
    except Exception:
        return False
