# SaathiOS — Tracker Market History Read-Model (v1)

**From `45166c14`; Research Surface frozen `b771d761`; Fusion `4d685383`.** Read-only
THIRD-PARTY analytics integration of NEPSE Portfolio Tracker's **public** structured REST
API — no credentials, no MCP key, no cookies, no browser, no scraping. Provides historical
OHLC, descriptive indicators, fundamentals, and dividends for charts / research / operator
analysis. Official NEPSE browser observation stays the current-market authority; tracker
data is **`THIRD_PARTY_STRUCTURED_MARKET_DATA`** and never becomes canonical MD-1 or a trade
signal.

## Package (`saathi/platform/market_data/tracker/`)
- **models.py** — `MarketPoint`, `MarketSeries`, `FundamentalSnapshot`, `DividendRecord`,
  `QuoteReconciliation`; enums `TrackerStatus`, `ReconVerdict`; tags `source=NEPSE_PORTFOLIO
  _TRACKER`, `source_authority=THIRD_PARTY_STRUCTURED_MARKET_DATA`, `data_class=THIRD_PARTY_
  HISTORICAL_SERIES`, `point_in_time_capability=HISTORICAL_KNOWLEDGE_TIME_UNSUPPORTED`. No
  fabricated `available_at`.
- **indicators.py** — pure descriptive SMA/EMA/RSI/MACD/Bollinger/ATR. `KIND=DESCRIPTIVE_
  ANALYTICS`; params exposed; warm-up positions `None`; **no** dependency on the strategy/
  signal contracts; no BUY/SELL/target/stop/position tokens (test-enforced). Defaults: SMA
  20/50, EMA 12/26, RSI 14, MACD 12/26/9, Bollinger 20/2, ATR 14.
- **provider.py** — `NepsePortfolioTrackerProvider`: governed `requests` client. Host
  allowlist `{api.nepseportfoliotracker.app, nepseportfoliotracker.app}` + `check_domain`
  SSRF guard; timeout 12 s; response cap 8 MB; ≤2 retries; concurrency semaphore (2);
  cross-host redirects rejected. TTL cache (history/fundamentals 300 s, dividends 900 s,
  bounded 256). Methods: `market_history`, `fundamentals`, `dividends`, `tracker_ltp`,
  `market_status`. Symbol resolution via existing `normalize_symbol`/`instrument_id_for`
  (unknown → `SYMBOL_UNRESOLVED`). Validation: finite OHLC, `high≥max(o,c,l)`,
  `low≤min(o,c,h)`, non-negative volume, ordered/duplicate detection — invalid rows
  **rejected, never repaired**.
- **chart.py** — `build_chart_model` (MarketChartModel dict), `reconcile_current` (official
  vs tracker, official authority), `chat_answer_tracker`, `voice_answer_tracker`,
  `catalyst_historical_context` (`is_canonical_reaction=False`).

## REST endpoints used (public, unauth, verified)
`/api/history/{symbol}?range=1D..5Y` (daily OHLC; 1D intraday), `/api/scripts/{symbol}`
(fundamentals + current price), `/api/announced-dividends` (filtered client-side),
`/api/market/status`. The MCP (`/mcp`) and `/api/quote` are key-gated and **not used**.

## Ranges / granularity (verified)
`1D`=INTRADAY; `1W/1M/3M/6M/1Y/5Y`=DAILY. Granularity preserved per range (no coercion).

## Point-in-time limitation
Tracker history exposes only `business_date` (no reliable `available_at`, no visible split/
dividend adjustment or corporate-action metadata). Marked
`HISTORICAL_KNOWLEDGE_TIME_UNSUPPORTED`. **Not** usable for look-ahead-safe backtests,
canonical Trading-Guardian historical simulation, or MD-1 promotion. Suitable for charts,
descriptive analytics, exploratory context, research.

## Cross-source reconciliation (Phase 7/24 — real)
Official NEPSE (authority) vs tracker current LTP → CONFIRMED (≤0.5% band) /
SOURCE_DISAGREEMENT / OFFICIAL_UNAVAILABLE / TRACKER_UNAVAILABLE. Never overwrites; both
values preserved. Live result (official snapshot seeded via the governed browser, market
CLOSED):
| Symbol | Official | Tracker | Diff | Verdict |
|---|---|---|---|---|
| NABIL | 552.00 | 552.00 | 0.00 | CONFIRMED |
| API | 334.70 | 334.70 | 0.00 | CONFIRMED |
| AKPL | 255.00 | 255.00 | 0.00 | CONFIRMED |
| HDL | 1192.00 | 1192.00 | 0.00 | CONFIRMED |

## Real validation (Phase 28/29 — live public REST, no fixtures)
- NABIL: 1M **18 pts** (2026-08-14→09-11), 1Y **224 pts** (2025-09-18→2026-09-11), 5Y
  **1158 pts** (2021-09-14→2026-09-11), latest close 552.00; history latency ~1.3–1.5 s/range.
- Indicators on 1Y: **3 ms**; RSI(14)=58.84, SMA20=545.46 (DESCRIPTIVE_ANALYTICS).
- Chart model NABIL 1Y: **2.65 s** (incl. fundamentals+dividends) → 224 OHLC + 224 volume +
  sma20/sma50/rsi/macd + EPS 28.36 / P/E 19.46 / Commercial Banks + 1 dividend + PIT note.
- Second symbol API 1Y: 223 pts, latest 334.70.
- Peak RSS (tracker path) **54.5 MB**; REST-only, **no second Chromium**.

## Server surface (read-only)
`/api/v1/market/tracker/{history,chart,fundamentals,dividends,reconcile}` (sync handlers →
threadpool) and a native `/market/chart` panel that draws candlesticks + volume + SMA
overlay from structured data in inline SVG — **no TradingView, no tracker iframe** (iframe
is blocked anyway: X-Frame-Options SAMEORIGIN). Source badge + freshness + PIT limitation
shown; official NEPSE named as current-LTP authority.

## Source badges (Phase 16)
Current LTP → "Official NEPSE"; historical/indicators/fundamentals → "NEPSE Portfolio
Tracker · Third-party historical". Never blurred.

## Chat / Voice / Catalyst (Phases 17–19)
Current-price queries answer from official first (with tracker reconciliation); history/
indicator/fundamental/dividend queries answer from tracker with source + PIT exposed.
Catalyst enrichment = `THIRD_PARTY_HISTORICAL_CONTEXT` (`is_canonical_reaction=false`);
Fusion historical-reaction semantics unchanged.

## Portfolio MCP boundary (Phase 20)
NOT connected. No MCP key requested. Future `NepsePortfolioTrackerMCPPortfolioAdapter`
(holdings/qty/WACC/market-value/unrealized-P&L, read-only) is documented only — **DEFERRED**
pending an owner-supplied Pro MCP key + ToS review.

## Security / authority
No credentials/MCP key/cookies/browser/scraping/iframe; host-allowlisted; SSRF-guarded;
bounded timeout/size/retries; no secret logging. `insert_bar`/`insert_quote`/`md_bars`/
`md_quotes`/`ExecutionGateway`/`place_order`/`trading_guardian`/`portfolio_construction`
absent from the package (audited). tracker→md_bars=0, tracker→md_quotes=0, broker=0,
orders=0, ExecutionGateway.execute=0, TG trade=0, portfolio writes=0, withdrawals=0,
leverage=0. Browser Use not used; Playwright not used for the tracker; MCP not connected.

## Tests
`tests/test_tracker_readmodel_v1.py` **20** (host policy, parse, OHLC validation, duplicate,
invalid series, range, symbol resolution, granularity, indicator values + semantic
boundary + params, reconciliation, chart model, chat, voice, catalyst, cache, failure
states, no-canonical/authority, point-in-time). Related regression **962 passed / 0
failed**. Frozen `b771d761` + `4d685383` = **0 diffs**.

## Limitations
1. `today-prices` list is capped at 100/page; per-symbol data via `/scripts/{symbol}` +
   `/history/{symbol}` (covers any symbol).
2. Tracker history is descriptive only (no point-in-time / adjustments) — not canonical.
3. `api.` subdomain DNS was unresolvable from the sandbox; the apex `/api` mirror (same
   official host set) is used with both allowlisted.
4. Terms of Service body is SPA-gated (unread) — public API used read-only in good faith;
   review ToS before commercial use.
5. Chart panel is a minimal native SVG (candles + volume + SMA); richer overlays are
   available via the chart model but intentionally not all stacked at once.

## Verdict
Real public-REST history validated (NABIL 1M/1Y/5Y + API), MarketSeries validated,
descriptive indicators deterministic, cross-source reconciliation live (4/4 CONFIRMED,
official authority), native SaathiOS chart rendered from structured data, source
classification visible, zero canonical writes, zero authority expansion ⇒

**SAATHIOS_TRACKER_MARKET_HISTORY_READMODEL_CERTIFIED_WITH_LIMITATIONS**
(limitations: point-in-time unsupported by source; ToS body unread; today-prices pagination).

## Exact next milestone
`M — TRACKER_SECTOR_AND_MULTI_SYMBOL_ANALYTICS` — sector/market-breadth read models + a
multi-symbol compare view over the same provider (still THIRD_PARTY, descriptive-only, zero
authority); portfolio-MCP wiring remains DEFERRED pending an owner Pro MCP key + ToS review.
No trading signals.
