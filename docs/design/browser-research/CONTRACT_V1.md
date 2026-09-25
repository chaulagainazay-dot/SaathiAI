# SaathiOS — Browser Research Contract & Isolated Acquisition (v1)

**Builds on the architecture audit (`docs/design/browser-research/` line of work) and `477e52d6`.**
Adds the missing **governed web-research contract** and proves ONE bounded, read-only
**NEPSE_DAILY_INTELLIGENCE** mission using the EXISTING `saathi.browser.GovernedBrowser` +
Playwright/HTTP tier. **browser-use is NOT installed.** No second research architecture,
no second evidence store, no second scheduler, no trade/broker/market_data-write authority.

## Package (all new, additive)
`saathi/browser_research/`
- `contract.py` — `ResearchRequest`, `ResearchResult`, `ExtractedFact`, `Citation`, `FetchedPage`, `BrowserResearchProvider` (ABC), enums (`MissionType`, `ResearchStatus`, `DataDomain`, `Provenance`, `FactGroup`), `AUTHORITY` locks. Fail-closed validation; a `BROWSER_DERIVED` fact can never be `MARKET_DATA`.
- `tiers.py` — `SourceTier` TIER_1..TIER_6; NEPSE Tier-1 allowlist (nepalstock, sebon.gov.np, nrb.org.np, cdsc, `.gov.np`). Unknown → TIER_6 (never silently authoritative).
- `freshness.py` — `Freshness` REALTIME…STALE/UNKNOWN from **publication time** vs now; retrieval time kept separately; future ts → UNKNOWN; no order-based inference.
- `provenance` — carried on every fact (`BROWSER_DERIVED`) + `DataDomain.WEB_INTELLIGENCE` (never MARKET_DATA).
- `reconciliation.py` — `arbitrate_market_value` (canonical API wins; browser value never promoted to canonical), `arbitrate_event` (TIER_1 official confirms > reputable multi-source `UNCONFIRMED_MULTI_SOURCE` > single). Never overwrites stronger with weaker.
- `provider.py` — `GovernedBrowserResearchProvider` over `GovernedBrowser` (governed READ only, `force_new`, `credentials`-free); bounds max_pages/max_runtime; `cleanup()` shuts the browser after the mission.
- `nepse.py` — `NEPSE_DAILY_INTELLIGENCE`: Tier-1-only sweep, pure `extract_facts`, grouping (OFFICIAL_NOTICES / CORPORATE_ACTIONS / REGULATORY / COMPANY_EVENTS / MARKET_CONTEXT), contradictions, freshness warnings.
- `evidence_bridge.py` — writes episode + per-fact rows into the **existing** `saathi/evidence` store (department `browser_research`); rebuilds facts with their evidence ref.
- `confidence_bridge.py` — maps facts onto **existing** `saathi/research.py` categories and calls `score_confidence`; adds source-tier coverage.
- `orchestrator.py` — bounded **runner** (not a scheduler): `MAX_BROWSER_WORKERS=1`, authority-locked, always cleans up, measures peak RSS.
- `status.py` — minimal read-only Central Command status projection (no new UI).

## Security / authority boundary
All acquisition is a governed READ through `GovernedBrowser`, which already enforces domain
policy, SSRF/loopback/metadata/private-IP blocking, dangerous-scheme + prohibited-action
(trade/payment/credentials/captcha) denial, redirect revalidation, and prompt-injection
detection (page text is data, never authority). The package imports **no** market_data store,
execution gateway, broker, or trading-guardian symbol (verified by grep + test). Browser
research invokes `gateway.submit` **only** for browser READs (family `browser`); zero
trade/execute invocations.

## Evidence
- **Tests:** `tests/test_browser_research_v1.py` — **22 passing** (covers all 23 Phase-15 checklist items + CC status): request/result validation, tiering, provenance, freshness, official-source preference, web-vs-API arbitration, contradiction, prompt-injection page, malicious-instruction-ignored, broker/withdrawal/private-IP/redirect blocked, no-trade + no-gateway-trade + no-market_data-write, evidence storage, cleanup, timeout, max-pages, NEPSE fixture E2E. Isolated execution boundary + temp evidence DB — **no real ledger touched**.
- **Live mission (Phase 16):** real fetch of `sebon.gov.np` + `nrb.org.np` (HTTP tier, no Chromium needed). Status **COMPLETE**, runtime **~1.4 s**, **peak RSS 61.9 MB**, 3 pages fetched, 2 Tier-1 sources, 47 facts (all TIER_1_OFFICIAL / BROWSER_DERIVED / WEB_INTELLIGENCE), clean shutdown; `cdsc.com.np` fail-closed (policy denied); freshness warnings surfaced.
- **Regression:** browser/gateway/execution suites **614 passed, 1 pre-existing unrelated live-Chromium lifecycle failure** (`test_m17_1_live`, code not modified here).

## Limitations
1. Extraction is heuristic line-matching over page text — precision is imperfect (some nav/footer/contact lines classified as notices). DOM/selector extraction per source is **M2** work.
2. Nepali **BS dates** (e.g. `2082-01-23`) are not converted; treated as UNKNOWN freshness (never falsely "fresh").
3. Central Command wiring is a read-only status projection only; the CC tile is deferred.
4. Live mission proven on HTTP-tier static official pages; JS-heavy `nepalstock.com` deep pages need the Playwright tier (Chromium binary) — deferred.
5. Orchestrator is a single-worker runner, not integrated into `tg/research_orchestrator`'s durable queue (deferred by design; avoids a second scheduler).

## Do-not-change (confirmed untouched)
ExecutionGateway, Trading Guardian, deterministic risk, approvals, RBAC, audit, broker
authority, paper/live state, provider governance, market-data authority (`market_data/contract.py`),
PBKDF2/auth. Zero existing files modified — additive package + one test file only.

**Verdict: SAATHIOS_BROWSER_RESEARCH_CONTRACT_AND_ISOLATED_ACQUISITION_CERTIFIED_WITH_LIMITATIONS.**
Next milestone (not started): **M — BROWSER_USE_ISOLATED_AGENTIC_ACQUISITION_EVALUATION** (browser-use in an isolated venv/subprocess behind this same contract).
