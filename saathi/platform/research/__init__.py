"""M62.3 — evidence-backed agentic research pipeline (server-authoritative).

No trading/approval/broker/execution authority. Source text is untrusted data.
See docs/trading/RESEARCH_PIPELINE.md.
"""
from saathi.platform.research.models import (
    FactClass, SourceType, TrustClass, SourceQuality, InjectionState, Verification,
    ContradictionType, ResearchState, ThesisState, RESEARCH_TRANSITIONS, can_research_transition,
    ResearchSource, Claim, Citation, Contradiction, content_hash,
)
from saathi.platform.research import analysis
from saathi.platform.research.store import ResearchStore
from saathi.platform.research.service import ResearchService, MAX_SOURCE_BYTES
from saathi.platform.research.fixtures import FIXTURES, fixture_manifest, get_fixture, FIXTURE_VERSION

__all__ = [
    "FactClass", "SourceType", "TrustClass", "SourceQuality", "InjectionState", "Verification",
    "ContradictionType", "ResearchState", "ThesisState", "RESEARCH_TRANSITIONS", "can_research_transition",
    "ResearchSource", "Claim", "Citation", "Contradiction", "content_hash",
    "analysis", "ResearchStore", "ResearchService", "MAX_SOURCE_BYTES",
    "FIXTURES", "fixture_manifest", "get_fixture", "FIXTURE_VERSION",
]
