"""Job dependency graph — block until parents succeed."""
from __future__ import annotations

import json
from typing import Any

from saathi.platform.tg.research_orchestrator.models import AUTHORITY_VALUES, JobState
from saathi.platform.tg.research_orchestrator.storage import OrchestratorStore


class DependencyGraph:
    def __init__(self, store: OrchestratorStore):
        self.store = store

    def parents_satisfied(self, job_id: str) -> tuple[bool, list[str]]:
        row = self.store.fetchone("SELECT depends_on_json FROM orch_jobs WHERE job_id=?", (job_id,))
        if not row:
            return False, ["JOB_NOT_FOUND"]
        deps = json.loads(row["depends_on_json"] or "[]")
        pending = []
        for d in deps:
            p = self.store.fetchone("SELECT state FROM orch_jobs WHERE job_id=?", (d,))
            if not p:
                pending.append(f"missing:{d}")
            elif p["state"] != JobState.SUCCEEDED.value:
                pending.append(f"{d}:{p['state']}")
        return len(pending) == 0, pending

    def unblock_ready(self) -> dict[str, Any]:
        """Move BLOCKED jobs to QUEUED when all parents succeeded."""
        blocked = self.store.fetchall("SELECT job_id FROM orch_jobs WHERE state=?", (JobState.BLOCKED.value,))
        released = []
        still = []
        for b in blocked:
            ok, pending = self.parents_satisfied(b["job_id"])
            if ok:
                self.store.execute(
                    "UPDATE orch_jobs SET state=?, queued_at=COALESCE(queued_at, ?) WHERE job_id=?",
                    (JobState.QUEUED.value, __import__("time").time(), b["job_id"]),
                )
                released.append(b["job_id"])
            else:
                still.append({"job_id": b["job_id"], "pending": pending})
        return {"ok": True, "released": released, "still_blocked": still, **AUTHORITY_VALUES}

    def graph_snapshot(self, limit: int = 100) -> dict[str, Any]:
        rows = self.store.fetchall(
            "SELECT job_id, name, state, depends_on_json FROM orch_jobs ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        nodes = []
        edges = []
        for r in rows:
            nodes.append({"job_id": r["job_id"], "name": r["name"], "state": r["state"]})
            for d in json.loads(r["depends_on_json"] or "[]"):
                edges.append({"from": d, "to": r["job_id"]})
        return {"ok": True, "nodes": nodes, "edges": edges, **AUTHORITY_VALUES}
