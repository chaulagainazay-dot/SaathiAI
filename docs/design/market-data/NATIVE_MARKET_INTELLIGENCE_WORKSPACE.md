# SaathiOS — Native NEPSE Market Intelligence Workspace (v1)

**From `93e4faa4`; Research Surface frozen `b771d761`; Fusion `4d685383`.** A native
SaathiOS workspace that **combines** the official governed-browser observation (current
authority) with the tracker third-party read model (history/analytics) plus research +
catalyst projections — without merging authority. No portfolio MCP, no trading signals,
zero execution authority, no iframe/TradingView.

## Authority model (combine, don't merge)
- CURRENT market → **Official NEPSE** (`OFFICIAL_PAGE_OBSERVED`, authority for LTP).
- HISTORY / analytics → **NEPSE Portfolio Tracker** (`THIRD_PARTY_STRUCTURED_MARKET_DATA`).
- RESEARCH / CATALYST → frozen Research Surface + Fusion (read-only projection, unmodified).
- PORTFOLIO → not connected ("Portfolio connection not configured"; MCP deferred).

## Components
- **tracker/models.py** (extended) — `StockRow`, `SectorMarketSnapshot`
  (`DERIVED_SECTOR_ANALYTICS`), `MultiSymbolComparison` + `ComparisonSeries`.
- **tracker/provider.py** (extended) — `stock_universe()` (`/today-prices?limit=600` → 588
  full universe), `sectors()` (`/market/sectors` → 13 sectors). Same governed transport +
  cache.
- **tracker/compare.py** (new) — `build_comparison` (≤4 symbols; **date-intersection**
  alignment, no forward-fill; `NORMALIZED_PERCENT` default `(close/first-1)*100` or
  `ABSOLUTE`; coverage limitations reported).
- **tracker/workspace.py** (new) — `overview`, `stock_table` (official LTP preferred where
  observed; deterministic sort/filter), `sectors`, `compare`, `symbol_panel`
  (chart+reconciliation+fundamentals+dividends+research+catalyst+portfolio-slot),
  `workspace_chat`/`workspace_voice` (source-aware routing). Failure-isolated typed states
  (AVAILABLE / PARTIAL_DATA / LIVE_SOURCE_UNAVAILABLE / HISTORY_SOURCE_UNAVAILABLE).
- **server.py** — `/api/v1/market/workspace/{overview,stocks,sectors,compare,panel,chat}`
  (auth-gated) + native `/market` page (tabs: Overview/Stocks/Compare/Sectors/Chart/
  Fundamentals-Dividends-Research; inline-SVG candles/volume/normalized-compare; source
  badges; PIT note).

## Routing bug fixed
`app.mount("/", StaticFiles, html=True)` (the SPA catch-all) matched every path, so all
market HTTP routes appended after it (this milestone **and** the earlier live-NEPSE +
tracker routes) were shadowed → 404/unreachable. Fix: an idempotent end-of-file step moves
root `Mount("/")` to the end of `app.router.routes` so explicit routes resolve first and the
SPA stays the final fallback. Verified: `/market`, `/market/chart`, `/market/nepse` → 200;
`/api/v1/market/workspace/*` → 401 (auth-gated). This also un-shadowed the prior milestones'
HTTP endpoints.

## Auth posture (Phase 8)
Market data API routes require canonical SaathiOS auth (401 without a token), consistent
with comparable internal surfaces; the frozen auth architecture is untouched. HTML panel
shells are servable; their data fetches are auth-gated.

## Real validation (Phase 29 — live, official seeded once)
- Overview 1.4 s (official idx 2559.49 + tracker), stocks **588 universe** 1.55 s (top rows
  carry **official LTP**, `ltp_source=OFFICIAL_PAGE_OBSERVED`), sectors **13** 1.33 s (top by
  change: Hydro Power 1.85%).
- Compare NABIL/API/AKPL/HDL: 1M common 2026-08-14→09-11 (18 pts), 3M 62 pts, 1Y 223 pts
  (**1 non-overlapping date/symbol excluded, reported**); normalized % e.g. 1Y NABIL +14.29,
  API +28.68, AKPL +7.14, HDL −8.17; ~5.3–5.5 s (4 uncached histories).
- Symbol panel NABIL 2.7 s: chart available, reconciliation **CONFIRMED**, EPS 28.36, 1
  dividend, research/catalyst PARTIAL_DATA (no seeded research → isolated, honest),
  portfolio not connected.
- Peak RSS 62.9 MB; **no new Chromium** for the tracker path.

## Browser validation (Phase 30)
`/market` rendered via Playwright at **desktop 1000×900** and **mobile 390×844**: title +
6 tabs render; source badges (Official NEPSE / Tracker third-party) visible; **0 uncaught
JS errors / pageerrors**. The 14 console entries are all expected `401` network logs (data
routes auth-gated; the headless browser has no session token). Live-authenticated data
render is owner-interactive (requires SaathiOS login) → recorded as a limitation.

## No trading semantics / authority (Phases 26/27)
No BUY/SELL/target/stop/position/expected-return (test-enforced). tracker→md_bars=0,
tracker→md_quotes=0, official→md_bars=0, broker=0, orders=0, ExecutionGateway.execute=0,
TG trade=0, portfolio writes=0, withdrawals=0, leverage=0. No portfolio MCP, no Browser
Use, no tracker Playwright, no iframe, no TradingView.

## Resource (Phase 23) — M2/8 GB
REST-only tracker; concurrency bound 2 (unchanged); bounded TTL cache (compare reuses it).
Single-symbol chart ~1.3–2.7 s, 4-symbol compare ~5.4 s (cached thereafter), sector ~1.3 s,
indicators ~3 ms, RSS ~63 MB, no background polling added.

## Tests
`tests/test_market_workspace_v1.py` **22** (overview combine + outage, stock table official-
preference/sort/filter, sector aggregation/ranking, compare normalized/absolute/
intersection/missing-date/cap, chat sector/turnover/compare/reconcile/delegate, voice,
tracker+official outage isolation, symbol panel, cache, no-trading-semantics, zero
authority, concurrency bound) + tracker read-model 20 = 42; related regression **1017
passed / 0 failed**. Frozen `b771d761` + `4d685383` = **0 diffs**.

## Limitations
1. Live-authenticated browser data render is owner-interactive (auth-gated); unauthenticated
   shell renders clean.
2. Research/catalyst panels are PARTIAL_DATA without seeded research (isolated, honest).
3. Tracker history remains descriptive/point-in-time-unsupported (not canonical/backtest).
4. Tracker ToS/endpoint stability is an external dependency risk (public endpoints only,
   read-only, verified in prior milestone; review ToS before commercial use).
5. Portfolio MCP deferred (no key).

## Verdict
Native workspace combining official (current authority) + tracker (third-party history) +
research/catalyst projections; sector analytics, 4-symbol comparison, native charts,
fundamentals, dividends, source reconciliation, chat/voice, outage isolation, M2/8 GB fit,
zero canonical contamination and zero authority expansion — all validated live + by test;
browser shell rendered clean on desktop + mobile ⇒

**SAATHIOS_NATIVE_NEPSE_MARKET_INTELLIGENCE_WORKSPACE_CERTIFIED_WITH_LIMITATIONS**
(limitations: authenticated in-browser data render owner-interactive; research/catalyst
depend on seeded data; tracker ToS external risk). Not frozen.

## Exact next milestone
`M — MARKET_WORKSPACE_AUTHENTICATED_BROWSER_E2E` — owner-interactive authenticated render of
`/market` (real data in every tab: overview/stocks/sectors/compare/chart/panel) with console
+ responsive evidence, then freeze the workspace integration semantics (recording tracker
endpoint stability as an external limitation). No portfolio MCP, no signals.
