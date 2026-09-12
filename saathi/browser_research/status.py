"""Phase 17 — minimal read-only status for Central Command.

No new UI. A tiny, read-only projection of a research result into the short
status line CC already renders for agents ("Researching… / N sources checked /
M official notices found / Research complete"). Full CC tile wiring is deferred.
"""
from __future__ import annotations

from saathi.browser_research.contract import FactGroup, ResearchResult, ResearchStatus
from saathi.browser_research.tiers import SourceTier

_PHASE = {
    ResearchStatus.RUNNING: "Researching official NEPSE sources",
    ResearchStatus.COMPLETE: "Research complete",
    ResearchStatus.PARTIAL: "Research complete (partial)",
    ResearchStatus.FAILED: "Research failed",
    ResearchStatus.TIMEOUT: "Research timed out",
    ResearchStatus.BLOCKED: "Research blocked (busy)",
    ResearchStatus.PENDING: "Research queued",
}


def status_line(result: ResearchResult) -> dict:
    official_notices = sum(
        1 for f in result.extracted_facts
        if f.source_tier == SourceTier.TIER_1_OFFICIAL
        and f.group in (FactGroup.OFFICIAL_NOTICES, FactGroup.CORPORATE_ACTIONS,
                        FactGroup.REGULATORY, FactGroup.COMPANY_EVENTS)
    )
    return {
        "mission_id": result.mission_id,
        "phase": _PHASE.get(result.status, "Researching"),
        "sources_checked": len(result.sources),
        "official_notices_found": official_notices,
        "facts": len(result.extracted_facts),
        "warnings": len(result.warnings),
        "complete": result.status in (ResearchStatus.COMPLETE, ResearchStatus.PARTIAL),
        "read_only": True,
    }
