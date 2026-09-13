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
from saathi.browser_research.bs_date import Calendar, bs_to_ad, is_valid_bs, parse_date
from saathi.browser_research.records import (
    ExtractedRecord, ExtractionMethod, SymbolResolution, deduplicate,
)
from saathi.browser_research.extractors import extractor_for
from saathi.browser_research.extract_v2 import extract_facts_v2, extract_records
from saathi.browser_research.durable import DurableBrowserResearch
from saathi.browser_research.status import status_line
from saathi.browser_research.nepse_endpoint import (
    EndpointClass, NEPSEJsonExtractor, SecurityIndex, classify_endpoint, is_adoptable,
)
from saathi.browser_research.nepse_v3 import run_nepse_deep_mission
from saathi.browser_research.documents import (
    DocumentIngestionRequest, DocumentIngestionResult, DocumentStatus,
    governed_fetch, ingest_document,
)
from saathi.browser_research.endpoint_monitor import EndpointHealth, health_from_capture, validate_schema
from saathi.browser_research.intelligence import (
    ResearchEvent, ResearchEventType, ResearchIntelligenceSnapshot, ContradictionState,
    build_snapshot, build_from_evidence, daily_brief, deterministic_summary,
    optional_model_summary, chat_answer, voice_answer, central_command_projection,
    unify_source_health, classify_event_type,
)

__all__ = [
    "AUTHORITY", "SCHEMA_VERSION", "MissionType", "ResearchStatus", "DataDomain",
    "Provenance", "FactGroup", "ContractError", "ResearchRequest", "ResearchResult",
    "ExtractedFact", "Citation", "FetchedPage", "BrowserResearchProvider",
    "GovernedBrowserResearchProvider", "Freshness", "classify_freshness",
    "meets_requirement", "SourceTier", "classify_source", "is_official",
    "tier1_allowlist", "ArbitrationOutcome", "CanonicalDatum", "Observation",
    "arbitrate_event", "arbitrate_market_value", "BrowserResearchOrchestrator",
    "MAX_BROWSER_WORKERS", "Calendar", "bs_to_ad", "is_valid_bs", "parse_date",
    "ExtractedRecord", "ExtractionMethod", "SymbolResolution", "deduplicate",
    "extractor_for", "extract_facts_v2", "extract_records",
    "DurableBrowserResearch", "status_line", "EndpointClass", "NEPSEJsonExtractor",
    "SecurityIndex", "classify_endpoint", "is_adoptable", "run_nepse_deep_mission",
    "DocumentIngestionRequest", "DocumentIngestionResult", "DocumentStatus",
    "governed_fetch", "ingest_document", "EndpointHealth", "health_from_capture",
    "validate_schema", "ResearchEvent", "ResearchEventType",
    "ResearchIntelligenceSnapshot", "ContradictionState", "build_snapshot",
    "build_from_evidence", "daily_brief", "deterministic_summary",
    "optional_model_summary", "chat_answer", "voice_answer",
    "central_command_projection", "unify_source_health", "classify_event_type",
]
