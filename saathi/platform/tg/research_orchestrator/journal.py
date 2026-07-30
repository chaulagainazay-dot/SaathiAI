"""Lab notebook, research journal, observation timeline, hypothesis tracking."""
from __future__ import annotations

import json
import time
from typing import Any

from saathi.platform.tg.research_orchestrator.models import AUTHORITY_VALUES, MAX_JOURNAL_ENTRIES
from saathi.platform.tg.research_orchestrator.storage import OrchestratorStore, _uid


class HypothesisTracker:
    def __init__(self, store: OrchestratorStore):
        self.store = store

    def create(self, statement: str, *, status: str = "OPEN") -> dict[str, Any]:
        hid = _uid("hyp")
        now = time.time()
        self.store.execute(
            "INSERT INTO orch_hypotheses(hypothesis_id, statement, status, job_ids_json, evidence_json, "
            "created_at, updated_at) VALUES(?,?,?,?,?,?,?)",
            (hid, statement, status, "[]", "{}", now, now),
        )
        self.store.timeline("hypothesis.created", hid, {"status": status})
        return {"ok": True, "hypothesis_id": hid, "statement": statement, "status": status, **AUTHORITY_VALUES}

    def link_job(self, hypothesis_id: str, job_id: str) -> dict[str, Any]:
        row = self.store.fetchone("SELECT * FROM orch_hypotheses WHERE hypothesis_id=?", (hypothesis_id,))
        if not row:
            return {"ok": False, "code": "HYPOTHESIS_NOT_FOUND", **AUTHORITY_VALUES}
        jobs = json.loads(row["job_ids_json"] or "[]")
        if job_id not in jobs:
            jobs.append(job_id)
        self.store.execute(
            "UPDATE orch_hypotheses SET job_ids_json=?, updated_at=? WHERE hypothesis_id=?",
            (json.dumps(jobs), time.time(), hypothesis_id),
        )
        return {"ok": True, "hypothesis_id": hypothesis_id, "job_ids": jobs, **AUTHORITY_VALUES}

    def update_status(self, hypothesis_id: str, status: str, evidence: dict | None = None) -> dict[str, Any]:
        row = self.store.fetchone("SELECT * FROM orch_hypotheses WHERE hypothesis_id=?", (hypothesis_id,))
        if not row:
            return {"ok": False, "code": "HYPOTHESIS_NOT_FOUND", **AUTHORITY_VALUES}
        ev = json.loads(row["evidence_json"] or "{}")
        if evidence:
            ev.update(evidence)
        self.store.execute(
            "UPDATE orch_hypotheses SET status=?, evidence_json=?, updated_at=? WHERE hypothesis_id=?",
            (status, json.dumps(ev, sort_keys=True, default=str), time.time(), hypothesis_id),
        )
        return {"ok": True, "hypothesis_id": hypothesis_id, "status": status, **AUTHORITY_VALUES}

    def list(self, limit: int = 50) -> dict[str, Any]:
        rows = self.store.fetchall(
            "SELECT * FROM orch_hypotheses ORDER BY created_at DESC LIMIT ?", (limit,)
        )
        out = []
        for r in rows:
            out.append({
                "hypothesis_id": r["hypothesis_id"],
                "statement": r["statement"],
                "status": r["status"],
                "job_ids": json.loads(r["job_ids_json"] or "[]"),
                "evidence": json.loads(r["evidence_json"] or "{}"),
            })
        return {"ok": True, "count": len(out), "hypotheses": out, **AUTHORITY_VALUES}


class ResearchJournal:
    def __init__(self, store: OrchestratorStore):
        self.store = store

    def write(self, title: str, body: str, *, kind: str = "note", refs: dict | None = None) -> dict[str, Any]:
        count = self.store.fetchone("SELECT COUNT(*) AS c FROM orch_journal")
        if (count or {}).get("c", 0) >= MAX_JOURNAL_ENTRIES:
            return {"ok": False, "code": "JOURNAL_FULL", **AUTHORITY_VALUES}
        eid = _uid("jnl")
        self.store.execute(
            "INSERT INTO orch_journal(entry_id, kind, title, body, refs_json, created_at) VALUES(?,?,?,?,?,?)",
            (eid, kind, title, body, json.dumps(refs or {}, sort_keys=True, default=str), time.time()),
        )
        return {"ok": True, "entry_id": eid, "kind": kind, "title": title, **AUTHORITY_VALUES}

    def list(self, limit: int = 50) -> dict[str, Any]:
        rows = self.store.fetchall(
            "SELECT entry_id, kind, title, body, refs_json, created_at FROM orch_journal "
            "ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        for r in rows:
            r["refs"] = json.loads(r.pop("refs_json") or "{}")
        return {"ok": True, "count": len(rows), "entries": rows, **AUTHORITY_VALUES}

    def notebook(self, limit: int = 100) -> dict[str, Any]:
        """Lab notebook view: journal + recent timeline + hypotheses."""
        j = self.list(limit=limit)
        timeline = self.store.fetchall(
            "SELECT event_id, kind, subject, detail_json, created_at FROM orch_timeline "
            "ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        for t in timeline:
            t["detail"] = json.loads(t.pop("detail_json") or "{}")
        return {
            "ok": True,
            "title": "Research Lab Notebook",
            "journal": j.get("entries"),
            "timeline": timeline,
            "research_only": True,
            **AUTHORITY_VALUES,
        }


class FailureAnalysis:
    def __init__(self, store: OrchestratorStore):
        self.store = store

    def analyse(self, limit: int = 50) -> dict[str, Any]:
        failed = self.store.fetchall(
            "SELECT job_id, name, error_json, retry_count, config_checksum, finished_at "
            "FROM orch_jobs WHERE state='FAILED' ORDER BY finished_at DESC LIMIT ?",
            (limit,),
        )
        by_code: dict[str, int] = {}
        items = []
        for f in failed:
            err = json.loads(f["error_json"] or "{}")
            code = err.get("code") or "UNKNOWN"
            by_code[code] = by_code.get(code, 0) + 1
            items.append({
                "job_id": f["job_id"],
                "name": f["name"],
                "error": err,
                "retry_count": f["retry_count"],
                "config_checksum": f["config_checksum"],
            })
        return {
            "ok": True,
            "failed_count": len(items),
            "by_error_code": by_code,
            "failures": items,
            "recommendations": [
                "Inspect config checksums for non-determinism",
                "Increase max_retries only with disclosed trial counts",
                "Do not delete failed jobs from the record",
            ],
            **AUTHORITY_VALUES,
        }
