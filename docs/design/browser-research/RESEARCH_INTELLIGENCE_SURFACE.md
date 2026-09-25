# SaathiOS — Research Intelligence Surface

**Builds on `55d9f552`.** Unifies existing research assets (NEPSE V3, SEBON/NRB extraction,
document ingestion, evidence store, reconciliation, freshness, source tiering) into one
read-only, evidence-backed intelligence surface for Central Command, chat, voice, and a daily
brief. **Deterministic first (works with no model). ZERO write authority.** No second research
system. Browser Use = DEFER (not invoked).

## Existing-surface audit (Phase 1)
- `saathi/evidence`, `saathi/research.py`, `browser_research/{contract,reconciliation,freshness,tiers,endpoint_monitor,documents}` → **REUSE/INTEGRATE**.
- Central Command `status.py` (prior) → **COMBINE** (new `central_command_projection`).
- Trading Guardian / ExecutionGateway / market-data / portfolio → **KEEP untouched** (read-only relevance only).
- No prior unified research read-model → **built** (projection, additive).

## New module (additive): `intelligence.py`
- `ResearchEventType` (DIVIDEND…MACRO_EVENT/SECURITY_INCIDENT — crypto-compatible), `ContradictionState`, `ResearchEvent`, `ResearchIntelligenceSnapshot`.
- `build_snapshot(facts, documents, …)` — clusters ExtractedFacts into events (one event, many evidence refs), reconciliation-based contradiction state, best-tier/freshest selection, document linkage by symbol, `RESEARCH_PRIORITY` (deterministic, non-trading), read-only portfolio relevance (injected holdings).
- `build_from_evidence(store, …)` — **projection over the existing evidence store** (no re-collection).
- `daily_brief`, `deterministic_summary` (no BUY/SELL/target/position wording — tested), `optional_model_summary` (ModelRouter-gated; `MODEL_UNAVAILABLE` in no-model mode), `chat_answer`, `voice_answer`, `central_command_projection`, `unify_source_health` (NEPSE endpoint + SEBON + NRB + documents, incl `DOCUMENT_UNAVAILABLE_TOKEN_GATED`).

## Authority hierarchy & contradictions
Reuses `reconciliation.arbitrate_event`: official TIER_1 confirms → `OFFICIAL_SOURCE_WINS`
(records confirmed value + conflicting sources, never deletes them); multiple reputable, no
official → `UNCONFIRMED_MULTI_SOURCE`. Canonical market-data authority unchanged; a research
event never becomes canonical price.

## Determinism / model
Evidence → deterministic normalization → reconciliation → events → snapshot → optional model
summary. The LLM never decides source authority. No-model mode returns the full deterministic
brief. Any model summary routes via ModelRouter (empty chain → `MODEL_UNAVAILABLE`).

## Live validation (Phase 31)
Real NEPSE deep mission → evidence store → `build_from_evidence`:
- **13 official events** (MBL dividend, PMHPL suspension, SBL delisting, MMKJL lock-in, …), all TIER_1_OFFICIAL, confidence 0.9, **0 untraceable events** (every claim → evidence ref).
- collection 10.3 s; **snapshot build 0.001 s** (projection separate from collection); **peak RSS 40.5 MB**.
- chat "show NABIL" → "No official evidence found for NABIL" (no fabrication); voice concise; daily brief sectioned; documents 0 (NEPSE attachment host token-gated — surfaced, not hidden).

## Authority invariants (verified)
`ExecutionGateway.execute` = 0, Trading-Guardian trade = 0, broker = 0, portfolio writes = 0,
market_data writes = 0, orders/payments/withdrawals = 0. `intelligence.py` imports none of
gateway/TG/market_data/broker/portfolio (grep + test). Read-only, evidence-only.

## pypdf dependency audit (Phase 24)
`pypdf` appears once in `requirements.txt` (`pypdf>=6.0`), not in `pyproject.toml`/egg. It was
previously an **undeclared/optional** dependency (used lazily by `docs.py`/`tools/files.py`,
which even printed `pip install pypdf`). Now correctly declared, single spec, no conflicting
version. Ownership correct.

## Tests
`tests/test_research_intelligence_v1.py` **24 tests** (134 total across the suite): event
normalization, duplicate clustering, official/page/news authority, contradiction retention,
freshness, research priority, no-trade-score naming, evidence references, unsupported-claim
rejection, document linkage + changed/token-gated states, unified source health, snapshot,
daily brief, no-model + optional-model + ModelRouter-unavailable, portfolio relevance, Central
Command projection, chat, voice, crypto-compatible schema, zero-write-authority imports.

## Limitations
1. Delivered as the **data/projection/synthesis layer** (snapshot, brief, chat/voice answerers, CC projection) — fully tested and live-validated; the **Next.js Central Command tile + server chat/voice route wiring** is a thin consumer, deferred (same pattern as prior `status.py`).
2. NEPSE attachment documents remain token-gated (surfaced as `DOCUMENT_UNAVAILABLE_TOKEN_GATED`); document enrichment works for NRB/SEBON/issuer PDFs.
3. Portfolio relevance uses injected holdings (no direct portfolio-API read wired — deliberate, keeps zero coupling/writes).
4. Model summary hook present but not exercised with a live LLM (deterministic layer authoritative).

## Verdict
One unified, deterministic, evidence-traceable research surface — events, contradictions,
freshness, priority, daily brief, chat, voice, source health — live-proven with zero write
authority. UI/route wiring deferred, so:

**SAATHIOS_RESEARCH_INTELLIGENCE_SURFACE_CERTIFIED_WITH_LIMITATIONS.**

## Next milestone (do NOT auto-start)
`M — RESEARCH_SURFACE_UI_WIRING`: wire `central_command_projection` / `chat_answer` /
`voice_answer` / `daily_brief` into the live Next.js Central Command tile + backend chat/voice
routes (read-only). Browser-use stays DEFER.
