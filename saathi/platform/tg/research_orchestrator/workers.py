"""Deterministic in-process worker pool (no external compute)."""
from __future__ import annotations

import time
from typing import Any

from saathi.platform.tg.research_orchestrator.models import (
    AUTHORITY_VALUES,
    DEFAULT_MAX_WORKERS,
    WorkerState,
)
from saathi.platform.tg.research_orchestrator.storage import OrchestratorStore, _uid


class WorkerPool:
    def __init__(self, store: OrchestratorStore, max_workers: int = DEFAULT_MAX_WORKERS):
        self.store = store
        self.max_workers = max(1, min(int(max_workers), 8))
        self._ensure_workers()

    def _ensure_workers(self) -> None:
        existing = self.store.fetchall("SELECT worker_id FROM orch_workers")
        n = len(existing)
        now = time.time()
        for i in range(n, self.max_workers):
            wid = f"worker_{i:02d}"
            self.store.execute(
                "INSERT OR IGNORE INTO orch_workers(worker_id, state, current_job_id, "
                "jobs_completed, jobs_failed, created_at, updated_at) VALUES(?,?,?,?,?,?,?)",
                (wid, WorkerState.IDLE.value, None, 0, 0, now, now),
            )

    def list(self) -> dict[str, Any]:
        rows = self.store.fetchall("SELECT * FROM orch_workers ORDER BY worker_id")
        return {
            "ok": True,
            "max_workers": self.max_workers,
            "workers": rows,
            "idle": sum(1 for r in rows if r["state"] == WorkerState.IDLE.value),
            "busy": sum(1 for r in rows if r["state"] == WorkerState.BUSY.value),
            **AUTHORITY_VALUES,
        }

    def acquire(self) -> str | None:
        row = self.store.fetchone(
            "SELECT worker_id FROM orch_workers WHERE state=? ORDER BY worker_id LIMIT 1",
            (WorkerState.IDLE.value,),
        )
        if not row:
            return None
        wid = row["worker_id"]
        self.store.execute(
            "UPDATE orch_workers SET state=?, updated_at=? WHERE worker_id=? AND state=?",
            (WorkerState.BUSY.value, time.time(), wid, WorkerState.IDLE.value),
        )
        # verify
        check = self.store.fetchone("SELECT state FROM orch_workers WHERE worker_id=?", (wid,))
        if check and check["state"] == WorkerState.BUSY.value:
            return wid
        return None

    def assign_job(self, worker_id: str, job_id: str) -> None:
        self.store.execute(
            "UPDATE orch_workers SET current_job_id=?, updated_at=? WHERE worker_id=?",
            (job_id, time.time(), worker_id),
        )

    def release(self, worker_id: str, *, success: bool) -> None:
        row = self.store.fetchone("SELECT * FROM orch_workers WHERE worker_id=?", (worker_id,))
        if not row:
            return
        completed = int(row["jobs_completed"]) + (1 if success else 0)
        failed = int(row["jobs_failed"]) + (0 if success else 1)
        self.store.execute(
            "UPDATE orch_workers SET state=?, current_job_id=NULL, jobs_completed=?, "
            "jobs_failed=?, updated_at=? WHERE worker_id=?",
            (WorkerState.IDLE.value, completed, failed, time.time(), worker_id),
        )
