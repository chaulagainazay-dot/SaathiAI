"""Governed public-web research subsystem (v1).

BROWSER USE → PUBLIC WEB ACQUISITION → NORMALIZED EVIDENCE → PROVENANCE →
RECONCILIATION → RESEARCH / SIGNAL INPUT.  RESEARCH ONLY / READ ONLY.

Composes EXISTING SaathiOS parts — GovernedBrowser (+ Playwright tier), the
evidence store, and the research-confidence framework — behind one narrow
contract. Does NOT install browser-use, does NOT create a second research
architecture, and has zero trade/broker/market_data-write authority.
"""
from saathi.browser_research.contract import (
    AUTHORITY, BrowserResearchProvider, Citation, ContractError, DataDomain,
    ExtractedFact, FactGroup, FetchedPage, MissionType, Provenance,
    ResearchRequest, ResearchResult, ResearchStatus, SCHEMA_VERSION,
)
from saathi.browser_research.freshness import Freshness, classify_freshness, meets_requirement
from saathi.browser_research.orchestrator import (
    MAX_BROWSER_WORKERS, BrowserResearchOrchestrator,
)
from saathi.browser_research.provider import GovernedBrowserResearchProvider
from saathi.browser_research.reconciliation import (
    ArbitrationOutcome, CanonicalDatum, Observation, arbitrate_event,
    arbitrate_market_value,
)
from saathi.browser_research.tiers import SourceTier, classify_source, is_official, tier1_allowlist

__all__ = [
    "AUTHORITY", "SCHEMA_VERSION", "MissionType", "ResearchStatus", "DataDomain",
    "Provenance", "FactGroup", "ContractError", "ResearchRequest", "ResearchResult",
    "ExtractedFact", "Citation", "FetchedPage", "BrowserResearchProvider",
    "GovernedBrowserResearchProvider", "Freshness", "classify_freshness",
    "meets_requirement", "SourceTier", "classify_source", "is_official",
    "tier1_allowlist", "ArbitrationOutcome", "CanonicalDatum", "Observation",
    "arbitrate_event", "arbitrate_market_value", "BrowserResearchOrchestrator",
    "MAX_BROWSER_WORKERS",
]
