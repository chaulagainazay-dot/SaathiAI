"""Experiment priority queue with deterministic ordering."""
from __future__ import annotations

import json
import time
from typing import Any

from saathi.platform.tg.research_orchestrator.errors import OrchestratorError
from saathi.platform.tg.research_orchestrator.models import (
    AUTHORITY_VALUES,
    MAX_QUEUE_DEPTH,
    PRIORITY_RANK,
    JobPriority,
    JobState,
)
from saathi.platform.tg.research_orchestrator.storage import (
    OrchestratorStore,
    config_checksum,
    evidence_hash,
    _uid,
)


class ExperimentQueue:
    def __init__(self, store: OrchestratorStore):
        self.store = store

    def enqueue(
        self,
        name: str,
        config: dict[str, Any],
        *,
        priority: str = JobPriority.NORMAL.value,
        template_id: str | None = None,
        depends_on: list[str] | None = None,
        budget_units: float = 1.0,
        estimated_runtime_sec: float = 1.0,
        max_retries: int = 2,
        actor: str = "system",
    ) -> dict[str, Any]:
        depth = self.store.fetchone(
            "SELECT COUNT(*) AS c FROM orch_jobs WHERE state IN ('QUEUED','SCHEDULED','BLOCKED','RUNNING','RETRYING')"
        )
        if (depth or {}).get("c", 0) >= MAX_QUEUE_DEPTH:
            raise OrchestratorError("QUEUE_FULL", f"Queue depth exceeds {MAX_QUEUE_DEPTH}")

        pr = PRIORITY_RANK.get(priority, PRIORITY_RANK[JobPriority.NORMAL.value])
        cs = config_checksum(config)
        job_id = _uid("job")
        depends_on = list(depends_on or [])
        state = JobState.BLOCKED.value if depends_on else JobState.QUEUED.value
        now = time.time()
        self.store.execute(
            "INSERT INTO orch_jobs(job_id, name, template_id, state, priority, priority_label, "
            "config_json, config_checksum, depends_on_json, budget_units, estimated_runtime_sec, "
            "retry_count, max_retries, created_at, queued_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                job_id, name, template_id, state, pr, priority,
                json.dumps(config, sort_keys=True, default=str), cs,
                json.dumps(depends_on), float(budget_units), float(estimated_runtime_sec),
                0, int(max_retries), now, now if state == JobState.QUEUED.value else None,
            ),
        )
        self.store.audit("job.enqueued", actor=actor, subject=job_id,
                         detail={"priority": priority, "state": state, "checksum": cs})
        self.store.timeline("job.enqueued", job_id, {"state": state, "priority": priority})
        return {
            "ok": True,
            "job_id": job_id,
            "state": state,
            "priority": priority,
            "priority_rank": pr,
            "config_checksum": cs,
            "depends_on": depends_on,
            **AUTHORITY_VALUES,
        }

    def peek_next(self) -> dict[str, Any] | None:
        """Deterministic next: lowest priority rank, then earliest queued_at, then job_id."""
        row = self.store.fetchone(
            "SELECT * FROM orch_jobs WHERE state='QUEUED' "
            "ORDER BY priority ASC, queued_at ASC, job_id ASC LIMIT 1"
        )
        return row

    def list(self, state: str | None = None, limit: int = 100) -> dict[str, Any]:
        if state:
            rows = self.store.fetchall(
                "SELECT job_id, name, state, priority, priority_label, config_checksum, "
                "budget_units, retry_count, created_at, finished_at FROM orch_jobs "
                "WHERE state=? ORDER BY priority ASC, created_at ASC LIMIT ?",
                (state, limit),
            )
        else:
            rows = self.store.fetchall(
                "SELECT job_id, name, state, priority, priority_label, config_checksum, "
                "budget_units, retry_count, created_at, finished_at FROM orch_jobs "
                "ORDER BY created_at DESC LIMIT ?",
                (limit,),
            )
        return {"ok": True, "count": len(rows), "jobs": rows, **AUTHORITY_VALUES}

    def get(self, job_id: str) -> dict[str, Any]:
        row = self.store.fetchone("SELECT * FROM orch_jobs WHERE job_id=?", (job_id,))
        if not row:
            return {"ok": False, "code": "JOB_NOT_FOUND", "job_id": job_id, **AUTHORITY_VALUES}
        out = dict(row)
        out["config"] = json.loads(out.pop("config_json") or "{}")
        out["depends_on"] = json.loads(out.pop("depends_on_json") or "[]")
        if out.get("result_json"):
            out["result"] = json.loads(out["result_json"])
        if out.get("error_json"):
            out["error"] = json.loads(out["error_json"])
        out["ok"] = True
        out.update(AUTHORITY_VALUES)
        return out

    def stats(self) -> dict[str, Any]:
        rows = self.store.fetchall("SELECT state, COUNT(*) AS c FROM orch_jobs GROUP BY state")
        by = {r["state"]: r["c"] for r in rows}
        return {"ok": True, "by_state": by, "total": sum(by.values()), **AUTHORITY_VALUES}
