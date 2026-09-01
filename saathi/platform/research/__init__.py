"""M62.3 evidence-backed research pipeline plus TA-1 typed contracts."""
from saathi.platform.research.models import (FactClass, SourceType, TrustClass, SourceQuality, InjectionState, Verification, ContradictionType, ResearchState, ThesisState, RESEARCH_TRANSITIONS, can_research_transition, ResearchSource, Claim, Citation, Contradiction, content_hash)
from saathi.platform.research import analysis
from saathi.platform.research.store import ResearchStore
from saathi.platform.research.service import ResearchService, MAX_SOURCE_BYTES
from saathi.platform.research.fixtures import FIXTURES, fixture_manifest, get_fixture, FIXTURE_VERSION
from saathi.platform.research.evidence import EvidenceReference, ResearchClaim, StructuredInvestmentThesis, ResearchCheckpoint, ResearchEvidenceSnapshot, UntrustedData, EvidenceTrustClass, ClaimStatus, visible_at, validate_claim
from saathi.platform.research.specialists import ResearchContext, SpecialistResult, ResearchBundle, SpecialistOrchestrator, SPECIALISTS
