# M62.3 — Evidence-Backed Research Pipeline

Package `saathi/platform/research/`. Server-authoritative, tenant-scoped, audited,
optimistic-concurrency. Reuses M62.1/M62.2 read-only. NO trading/approval/broker/
execution authority (safety scan clean; no runtime/gateway/execution import).

## Flow (orchestration state machine)
DRAFT → PLANNED → COLLECTING_SOURCES → VALIDATING_SOURCES → EXTRACTING_CLAIMS →
VERIFYING_CITATIONS → SEARCHING_CONTRADICTIONS → SYNTHESIZING → CHALLENGE_REQUIRED →
UNDER_CHALLENGE → HUMAN_REVIEW_REQUIRED → APPROVED_FOR_PUBLICATION → PUBLISHED
(+ REJECTED/EXPIRED/FAILED). Transitions validated; no jump to PUBLISHED.

## Modules
- `models.py` — enums (FactClass, SourceType, TrustClass, SourceQuality, InjectionState,
  Verification, ContradictionType, ResearchState, ThesisState), state machines, records.
- `analysis.py` — pure: prompt-injection detection, rule-based extractor, citation
  verification, contradiction discovery, component confidence, independent challenge.
- `store.py` — SQLite: projects/sources/claims/citations/contradictions/theses;
  versioned; published theses immutable.
- `service.py` — ResearchService: ctx-gated + audited orchestration; fail-closed publish.
- `fixtures.py` — 7 deterministic hashed source sets (valid/contradictory/stale/
  injection/unsupported-certainty/weak/calculation/failed-challenge).

## Fact classification (mandatory before publication)
FACT / CALCULATION / ASSUMPTION / INFERENCE / OPINION / FORECAST. FACT/CALCULATION
without a verified citation is a critical challenge finding → blocks publication.

## Confidence
Component-based (source_quality, source_diversity, citation_coverage, data_freshness,
contradiction_severity, assumption_burden) with documented weights; scalar + full
component breakdown preserved. A high score is not a correctness guarantee.

## Publication is fail-closed
Blocked when: unresolved critical challenge findings, unresolved critical
contradictions, or (via challenge) uncited critical facts. Publish requires
RESEARCH_PUBLISH (owner+); agents cannot self-grant publishing authority.
