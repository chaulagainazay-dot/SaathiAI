"""Deterministic experiment scheduler — single-threaded tick loop."""
from __future__ import annotations

import json
import time
from typing import Any, Callable

from saathi.platform.tg.research_orchestrator.budget import ComputeBudgetManager
from saathi.platform.tg.research_orchestrator.dependencies import DependencyGraph
from saathi.platform.tg.research_orchestrator.errors import OrchestratorError
from saathi.platform.tg.research_orchestrator.models import AUTHORITY_VALUES, JobState
from saathi.platform.tg.research_orchestrator.queue import ExperimentQueue
from saathi.platform.tg.research_orchestrator.storage import OrchestratorStore, evidence_hash
from saathi.platform.tg.research_orchestrator.workers import WorkerPool


class ExperimentScheduler:
    """Schedule queued jobs onto workers under budget and dependency constraints."""

    def __init__(
        self,
        store: OrchestratorStore,
        queue: ExperimentQueue,
        workers: WorkerPool,
        budget: ComputeBudgetManager,
        deps: DependencyGraph,
        *,
        job_executor: Callable[[dict], dict] | None = None,
    ):
        self.store = store
        self.queue = queue
        self.workers = workers
        self.budget = budget
        self.deps = deps
        self.job_executor = job_executor or self._default_executor

    def _default_executor(self, job: dict[str, Any]) -> dict[str, Any]:
        """Deterministic offline research job — composes research_lab when requested."""
        config = job.get("config") or {}
        kind = config.get("kind", "noop")
        seed = int(config.get("seed", 42))
        if kind == "research_lab_bootstrap":
            from saathi.platform.tg.research_lab.service import ResearchLabService
            from pathlib import Path
            db = Path(self.store.db_path).parent / f"rl_job_{job['job_id']}.db"
            svc = ResearchLabService(db_path=db)
            result = svc.bootstrap_demo_pipeline()
            return {
                "ok": True,
                "kind": kind,
                "seed": seed,
                "lab_experiment_id": result.get("experiment_id"),
                "candidate_state": (result.get("candidate") or {}).get("state"),
                "preserved_oos_failures": result.get("preserved_oos_failures"),
                "deterministic": True,
            }
        if kind == "strategy_compare":
            from saathi.platform.tg.research_lab.service import ResearchLabService
            from pathlib import Path
            db = Path(self.store.db_path).parent / f"rl_job_{job['job_id']}.db"
            svc = ResearchLabService(db_path=db)
            strategies = config.get("strategy_ids") or ["tf_dual_ma", "mom_rs_equity"]
            cmp = svc.compare_strategies(strategies, seed=seed)
            return {
                "ok": True,
                "kind": kind,
                "seed": seed,
                "scorecard_count": len(cmp.get("scorecards") or []),
                "comparison_id": cmp.get("comparison_id"),
                "deterministic": True,
            }
        if kind == "fail_probe":
            raise OrchestratorError("INTENTIONAL_FAILURE", "fail_probe kind always fails")
        # noop / generic research step
        return {
            "ok": True,
            "kind": kind,
            "seed": seed,
            "name": job.get("name"),
            "config_checksum": job.get("config_checksum"),
            "deterministic": True,
            "message": "offline research step completed",
        }

    def tick(self, max_jobs: int = 1) -> dict[str, Any]:
        """Run up to max_jobs from the queue (deterministic order)."""
        ran = []
        errors = []
        for _ in range(max(1, max_jobs)):
            # Re-evaluate deps each iteration so children free after parents in same tick
            self.deps.unblock_ready()
            nxt = self.queue.peek_next()
            if not nxt:
                break
            worker_id = self.workers.acquire()
            if not worker_id:
                errors.append({"code": "NO_IDLE_WORKER", "job_id": nxt["job_id"]})
                break
            job_id = nxt["job_id"]
            units = float(nxt.get("budget_units") or 1.0)
            try:
                self.budget.reserve(units)
            except OrchestratorError as e:
                self.workers.release(worker_id, success=False)
                errors.append({"code": e.code, "job_id": job_id, "message": e.message})
                break

            now = time.time()
            self.store.execute(
                "UPDATE orch_jobs SET state=?, worker_id=?, started_at=? WHERE job_id=?",
                (JobState.RUNNING.value, worker_id, now, job_id),
            )
            self.workers.assign_job(worker_id, job_id)
            self.store.timeline("job.started", job_id, {"worker_id": worker_id})

            job_pub = self.queue.get(job_id)
            try:
                result = self.job_executor(job_pub)
                eh = evidence_hash(result)
                self.store.execute(
                    "UPDATE orch_jobs SET state=?, result_json=?, evidence_hash=?, finished_at=?, "
                    "immutable=1 WHERE job_id=?",
                    (
                        JobState.SUCCEEDED.value,
                        json.dumps(result, sort_keys=True, default=str),
                        eh,
                        time.time(),
                        job_id,
                    ),
                )
                self.budget.commit(units)
                self.workers.release(worker_id, success=True)
                self.store.audit("job.succeeded", subject=job_id, detail={"evidence_hash": eh})
                self.store.timeline("job.succeeded", job_id, {"evidence_hash": eh})
                ran.append({"job_id": job_id, "state": JobState.SUCCEEDED.value, "evidence_hash": eh})
            except Exception as e:
                code = getattr(e, "code", "JOB_FAILED")
                msg = getattr(e, "message", str(e))
                retry_count = int(nxt.get("retry_count") or 0)
                max_retries = int(nxt.get("max_retries") or 0)
                err = {"code": code, "message": msg}
                if retry_count < max_retries:
                    self.store.execute(
                        "UPDATE orch_jobs SET state=?, retry_count=retry_count+1, error_json=?, "
                        "worker_id=NULL, started_at=NULL WHERE job_id=?",
                        (
                            JobState.RETRYING.value,
                            json.dumps(err, sort_keys=True),
                            job_id,
                        ),
                    )
                    # re-queue for retry
                    self.store.execute(
                        "UPDATE orch_jobs SET state=?, queued_at=? WHERE job_id=?",
                        (JobState.QUEUED.value, time.time(), job_id),
                    )
                    self.budget.release_reservation(units)
                    self.workers.release(worker_id, success=False)
                    self.store.timeline("job.retrying", job_id, err)
                    ran.append({"job_id": job_id, "state": JobState.RETRYING.value, "error": err})
                else:
                    self.store.execute(
                        "UPDATE orch_jobs SET state=?, error_json=?, finished_at=?, immutable=1 WHERE job_id=?",
                        (
                            JobState.FAILED.value,
                            json.dumps(err, sort_keys=True),
                            time.time(),
                            job_id,
                        ),
                    )
                    self.budget.commit(units)  # failed jobs still consume budget
                    self.workers.release(worker_id, success=False)
                    self.store.audit("job.failed", subject=job_id, detail=err)
                    self.store.timeline("job.failed", job_id, err)
                    ran.append({"job_id": job_id, "state": JobState.FAILED.value, "error": err})
                    errors.append({"job_id": job_id, **err})

        return {
            "ok": True,
            "ran": ran,
            "errors": errors,
            "queue": self.queue.stats(),
            "workers": self.workers.list(),
            "budget": self.budget.status(),
            **AUTHORITY_VALUES,
        }

    def cancel(self, job_id: str, *, actor: str = "system", reason: str = "cancelled") -> dict[str, Any]:
        row = self.store.fetchone("SELECT * FROM orch_jobs WHERE job_id=?", (job_id,))
        if not row:
            raise OrchestratorError("JOB_NOT_FOUND", job_id)
        if row["immutable"] and row["state"] in (JobState.SUCCEEDED.value, JobState.FAILED.value):
            raise OrchestratorError("IMMUTABLE_JOB", "Cannot cancel completed immutable job")
        if row["state"] in (JobState.SUCCEEDED.value, JobState.FAILED.value, JobState.CANCELLED.value):
            raise OrchestratorError("CANCEL_INVALID_STATE", f"Cannot cancel from {row['state']}")
        self.store.execute(
            "UPDATE orch_jobs SET state=?, cancelled_at=?, error_json=?, worker_id=NULL WHERE job_id=?",
            (
                JobState.CANCELLED.value,
                time.time(),
                json.dumps({"reason": reason}, sort_keys=True),
                job_id,
            ),
        )
        if row.get("worker_id"):
            self.workers.release(row["worker_id"], success=False)
        self.store.audit("job.cancelled", actor=actor, subject=job_id, detail={"reason": reason})
        self.store.timeline("job.cancelled", job_id, {"reason": reason})
        return {"ok": True, "job_id": job_id, "state": JobState.CANCELLED.value, **AUTHORITY_VALUES}

    def suspend(self, job_id: str, *, actor: str = "system") -> dict[str, Any]:
        row = self.store.fetchone("SELECT * FROM orch_jobs WHERE job_id=?", (job_id,))
        if not row:
            raise OrchestratorError("JOB_NOT_FOUND", job_id)
        if row["state"] not in (JobState.QUEUED.value, JobState.BLOCKED.value, JobState.RETRYING.value):
            raise OrchestratorError("SUSPEND_INVALID_STATE", f"Cannot suspend from {row['state']}")
        self.store.execute(
            "UPDATE orch_jobs SET state=? WHERE job_id=?",
            (JobState.SUSPENDED.value, job_id),
        )
        self.store.timeline("job.suspended", job_id, {"actor": actor})
        return {"ok": True, "job_id": job_id, "state": JobState.SUSPENDED.value, **AUTHORITY_VALUES}

    def resume(self, job_id: str, *, actor: str = "system") -> dict[str, Any]:
        row = self.store.fetchone("SELECT * FROM orch_jobs WHERE job_id=?", (job_id,))
        if not row:
            raise OrchestratorError("JOB_NOT_FOUND", job_id)
        if row["state"] != JobState.SUSPENDED.value:
            raise OrchestratorError("RESUME_INVALID_STATE", f"Cannot resume from {row['state']}")
        deps = json.loads(row["depends_on_json"] or "[]")
        state = JobState.BLOCKED.value if deps else JobState.QUEUED.value
        self.store.execute(
            "UPDATE orch_jobs SET state=?, queued_at=? WHERE job_id=?",
            (state, time.time(), job_id),
        )
        self.store.timeline("job.resumed", job_id, {"actor": actor, "state": state})
        return {"ok": True, "job_id": job_id, "state": state, **AUTHORITY_VALUES}

    def replay(self, job_id: str) -> dict[str, Any]:
        """Read-only reproducible replay of a completed job."""
        row = self.store.fetchone("SELECT * FROM orch_jobs WHERE job_id=?", (job_id,))
        if not row:
            raise OrchestratorError("JOB_NOT_FOUND", job_id)
        if row["state"] not in (JobState.SUCCEEDED.value, JobState.FAILED.value):
            raise OrchestratorError("REPLAY_NOT_AVAILABLE", f"Job state {row['state']} has no frozen result")
        result = json.loads(row["result_json"]) if row.get("result_json") else None
        error = json.loads(row["error_json"]) if row.get("error_json") else None
        return {
            "ok": True,
            "replay": True,
            "job_id": job_id,
            "state": row["state"],
            "config_checksum": row["config_checksum"],
            "immutable": bool(row["immutable"]),
            "result": result,
            "error": error,
            "evidence_hash": row.get("evidence_hash"),
            "reproducible": bool(row["immutable"]),
            **AUTHORITY_VALUES,
        }
