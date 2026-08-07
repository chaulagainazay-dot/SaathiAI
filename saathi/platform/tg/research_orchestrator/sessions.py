"""Reproducible research sessions."""
from __future__ import annotations

import json
import time
from typing import Any

from saathi.platform.tg.research_orchestrator.models import AUTHORITY_VALUES
from saathi.platform.tg.research_orchestrator.storage import OrchestratorStore, config_checksum, _uid


class ResearchSessionManager:
    def __init__(self, store: OrchestratorStore):
        self.store = store

    def open(self, name: str, *, seed: int = 42, config: dict | None = None) -> dict[str, Any]:
        sid = _uid("sess")
        cfg = dict(config or {})
        cfg["seed"] = seed
        self.store.execute(
            "INSERT INTO orch_sessions(session_id, name, seed, config_json, job_ids_json, status, created_at) "
            "VALUES(?,?,?,?,?,?,?)",
            (sid, name, seed, json.dumps(cfg, sort_keys=True), "[]", "OPEN", time.time()),
        )
        self.store.timeline("session.opened", sid, {"name": name, "seed": seed})
        return {
            "ok": True,
            "session_id": sid,
            "name": name,
            "seed": seed,
            "config_checksum": config_checksum(cfg),
            "status": "OPEN",
            **AUTHORITY_VALUES,
        }

    def attach_job(self, session_id: str, job_id: str) -> dict[str, Any]:
        row = self.store.fetchone("SELECT * FROM orch_sessions WHERE session_id=?", (session_id,))
        if not row:
            return {"ok": False, "code": "SESSION_NOT_FOUND", **AUTHORITY_VALUES}
        jobs = json.loads(row["job_ids_json"] or "[]")
        if job_id not in jobs:
            jobs.append(job_id)
        self.store.execute(
            "UPDATE orch_sessions SET job_ids_json=? WHERE session_id=?",
            (json.dumps(jobs), session_id),
        )
        return {"ok": True, "session_id": session_id, "job_ids": jobs, **AUTHORITY_VALUES}

    def close(self, session_id: str) -> dict[str, Any]:
        row = self.store.fetchone("SELECT * FROM orch_sessions WHERE session_id=?", (session_id,))
        if not row:
            return {"ok": False, "code": "SESSION_NOT_FOUND", **AUTHORITY_VALUES}
        self.store.execute(
            "UPDATE orch_sessions SET status=?, closed_at=? WHERE session_id=?",
            ("CLOSED", time.time(), session_id),
        )
        self.store.timeline("session.closed", session_id, {})
        return {"ok": True, "session_id": session_id, "status": "CLOSED", **AUTHORITY_VALUES}

    def get(self, session_id: str) -> dict[str, Any]:
        row = self.store.fetchone("SELECT * FROM orch_sessions WHERE session_id=?", (session_id,))
        if not row:
            return {"ok": False, "code": "SESSION_NOT_FOUND", **AUTHORITY_VALUES}
        return {
            "ok": True,
            "session_id": row["session_id"],
            "name": row["name"],
            "seed": row["seed"],
            "config": json.loads(row["config_json"]),
            "job_ids": json.loads(row["job_ids_json"] or "[]"),
            "status": row["status"],
            "created_at": row["created_at"],
            "closed_at": row.get("closed_at"),
            **AUTHORITY_VALUES,
        }

    def list(self, limit: int = 50) -> dict[str, Any]:
        rows = self.store.fetchall(
            "SELECT session_id, name, seed, status, created_at, closed_at FROM orch_sessions "
            "ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        return {"ok": True, "count": len(rows), "sessions": rows, **AUTHORITY_VALUES}
