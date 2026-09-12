"""Phase 21 — durable integration with the EXISTING research orchestrator.

Reuses ``tg/research_orchestrator`` for durable job tracking (mission id, budget
estimate, queue record, journal) — it is NOT a second scheduler and its compute
worker pool is never asked to execute the browser mission. The browser mission
runs on the single-worker BrowserResearchOrchestrator (MAX_BROWSER_WORKERS=1);
the durable job is the audit/status record. Degrades cleanly if the orchestrator
API is unavailable — the mission still runs.
"""
from __future__ import annotations

import time

from saathi.browser_research.contract import ResearchRequest
from saathi.browser_research.orchestrator import (
    MAX_BROWSER_WORKERS, BrowserResearchOrchestrator,
)


class DurableBrowserResearch:
    def __init__(self, *, orchestrator_db=None, mode: str = "service", write_evidence: bool = True):
        self.mode = mode
        self.write_evidence = write_evidence
        self.runner = BrowserResearchOrchestrator(mode=mode, write_evidence=write_evidence)
        self._svc = None
        try:
            from saathi.platform.tg.research_orchestrator.service import ResearchOrchestratorService
            self._svc = ResearchOrchestratorService(db_path=orchestrator_db, max_workers=1)
        except Exception:
            self._svc = None

    def _enqueue(self, request: ResearchRequest) -> tuple[str, str]:
        if self._svc is None:
            return "", "orchestrator_unavailable"
        try:
            job = self._svc.enqueue_job(
                name=f"browser_research:{request.mission_type.value}",
                config={
                    "kind": "browser_research", "mission_id": request.mission_id,
                    "market": request.market, "max_pages": request.max_pages,
                    "browser_workers": MAX_BROWSER_WORKERS,
                    "authority": "RESEARCH_ONLY_NO_BROKER_NO_EXECUTION",
                },
                actor=request.actor,
            )
            jid = job.get("job_id") or job.get("id") or (job.get("job") or {}).get("job_id") or ""
            return str(jid), ("ok" if jid else "enqueued_no_id")
        except Exception as e:
            return "", f"enqueue_error:{type(e).__name__}"

    def _journal(self, request: ResearchRequest, out: dict, job_id: str) -> None:
        if self._svc is None:
            return
        try:
            facts = len((out.get("result") or {}).get("extracted_facts", []))
            self._svc.write_journal(
                title=f"browser_research {request.mission_id}",
                body=f"status={out.get('status')} facts={facts} job={job_id} "
                     f"worker=1/{MAX_BROWSER_WORKERS}",
            )
        except Exception:
            pass

    def run(self, request: ResearchRequest, *, provider=None, seed_urls=None, now=time.time) -> dict:
        request.validate()
        job_id, enq = self._enqueue(request)
        out = self.runner.run(request, provider=provider, seed_urls=seed_urls, now=now)
        self._journal(request, out, job_id)
        out["durable_job_id"] = job_id
        out["durable_status"] = enq
        out["max_browser_workers"] = MAX_BROWSER_WORKERS
        return out
