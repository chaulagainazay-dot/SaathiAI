"""Phase 11/14 — bounded browser-research runner.

This is a RUNNER, not a second scheduler: one mission at a time, one browser
worker, one context, hard cleanup after every mission. It reuses the existing
GovernedBrowser, evidence store, and research-confidence framework via the
provider and bridges. Authority is locked to governed public-web research.
"""
from __future__ import annotations

import sys
import threading
import time

from saathi.browser_research.confidence_bridge import to_research_confidence
from saathi.browser_research.contract import (
    AUTHORITY, MissionType, ResearchRequest, ResearchResult, ResearchStatus,
)
from saathi.browser_research.evidence_bridge import write_result_to_evidence
from saathi.browser_research.nepse import NEPSE_SEED_URLS, run_nepse_mission
from saathi.browser_research.provider import GovernedBrowserResearchProvider
from saathi.browser_research.tiers import tier1_allowlist

MAX_BROWSER_WORKERS = 1

_worker_lock = threading.Lock()


def _peak_rss_mb() -> float:
    try:
        import resource
        ru = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        # macOS reports bytes; Linux reports kilobytes.
        return round(ru / (1024 * 1024), 1) if sys.platform == "darwin" else round(ru / 1024, 1)
    except Exception:
        return 0.0


class BrowserResearchOrchestrator:
    """Single-worker bounded runner for governed web-research missions."""

    authority = dict(AUTHORITY)

    def __init__(self, *, mode: str = "service", write_evidence: bool = True):
        self.mode = mode
        self.write_evidence = write_evidence

    def run(
        self,
        request: ResearchRequest,
        *,
        provider: GovernedBrowserResearchProvider | None = None,
        seed_urls: tuple[str, ...] | None = None,
        now=time.time,
    ) -> dict:
        request.validate()
        # Enforce MAX_BROWSER_WORKERS = 1 (non-blocking).
        if not _worker_lock.acquire(blocking=False):
            return {
                "status": ResearchStatus.BLOCKED.value,
                "reason": "MAX_BROWSER_WORKERS=1 busy",
                "authority": dict(self.authority),
            }
        owns_provider = provider is None
        rss_before = _peak_rss_mb()
        try:
            if provider is None:
                provider = GovernedBrowserResearchProvider(
                    allowed_hosts=tier1_allowlist(),
                    mode=self.mode,
                    max_pages=request.max_pages,
                    max_runtime_sec=request.max_runtime_sec,
                )
            if request.mission_type == MissionType.NEPSE_DAILY_INTELLIGENCE:
                result = run_nepse_mission(
                    provider, request, seed_urls=seed_urls or NEPSE_SEED_URLS, now=now)
            else:
                return {"status": ResearchStatus.FAILED.value,
                        "reason": f"unsupported mission_type {request.mission_type}",
                        "authority": dict(self.authority)}

            confidence = to_research_confidence(result, now=now() if callable(now) else now)
            episode_id = ""
            if self.write_evidence:
                episode_id, result = write_result_to_evidence(result)
            # A mission is one-shot: always clean up the browser after it, even a
            # caller-supplied provider (Phase 14 shutdown-after-mission).
            cleanup = provider.cleanup()
            result.resource.update({
                "runtime_sec": round((now() if callable(now) else now) - result.started_at, 3),
                "pages_fetched": getattr(provider, "pages_fetched", cleanup.get("pages_fetched", 0)),
                "peak_rss_mb": max(rss_before, _peak_rss_mb()),
                "cleanup": cleanup,
                "worker": f"1/{MAX_BROWSER_WORKERS}",
            })
            return {
                "status": result.status.value,
                "result": result.as_dict(),
                "confidence": confidence,
                "evidence_episode_id": episode_id,
                "authority": dict(self.authority),
            }
        finally:
            # Guaranteed cleanup even on exception; skip if already closed above.
            if provider is not None and not getattr(provider, "_closed", True):
                try:
                    provider.cleanup()
                except Exception:
                    pass
            _worker_lock.release()
