# SaathiOS — Live NEPSE Browser Market Data (v1)

**From `360e8ed1`; Research Surface frozen `b771d761`; Fusion `4d685383`.** SaathiOS opens
the OFFICIAL public NEPSE website with governed Playwright and reads the **currently
rendered market DOM** directly — no file downloads, no XHR/token replay, no broker/TMS.
The observation is tagged **`LIVE_BROWSER_OBSERVED`** and is kept strictly separate from
canonical historical market data.

## Two data classes (enforced in code + tests)
1. **`CANONICAL_HISTORICAL_MARKET_DATA`** — `md_bars`, written only by the point-in-time
   importer (`owner_import.run_import`, fed by `nepse_acquire`). Used for backtesting,
   historical replay, performance/risk, look-ahead-safe analysis.
2. **`LIVE_BROWSER_OBSERVED`** — this milestone. Current awareness only: current LTP,
   today OHLC, volume, turnover, index, breadth, market status. **Never** written to
   `md_bars`; **never** historical market-reaction evidence.

The download path from `360e8ed1` remains untouched as EOD fallback/evidence; it is no
longer the main operational path for current awareness.

## Live discovery (real, Phase 1)
- `nepalstock.com/` renders a NEPSE-index widget: index **2,559.49**, change **27.94 /
  1.10%**, status **MARKET CLOSED**, Total Turnover **Rs 4,360,159,487.26**, Total Traded
  Shares **12,089,709**, breadth **ADV 238 / DEC 30 / UNCH 9**, "As of Sep 11, 2026,
  3:00:00 PM".
- `nepalstock.com/today-price` renders one table: SN, Symbol, Close, Open, High, Low,
  Total Traded Quantity, Total Traded Value, Total Trades, **LTP** (`"552.00(-0.5)"` =
  ltp+point-change), Prev Close, Avg, 52wH/L, MktCap. Page-size select (10…**500**) applies
  only when the page's own **Filter** button is clicked (read-only re-render) → **345**
  securities in one page.
- The site's public JSON endpoints return **401** (anti-bot). We do **not** defeat them —
  the app renders its own authorized table and we read the **visible DOM**.
- **Acquisition class: `OFFICIAL_DOM_VISIBLE`** (page-state observation), not XHR replay.

## Components
- **New `live_observation.py`** — pure domain (offline-testable): `LiveMarketObservation`,
  `NepseLiveMarketSnapshot`, enums `MarketState`/`Freshness`/`LiveAcquisitionStatus`/
  `SymbolResolution`, numeric/LTP/as-of normalization, `compute_freshness`. Invariant tags
  `data_class=LIVE_BROWSER_OBSERVED`, `source_authority=NEPAL_STOCK_EXCHANGE`,
  `acquisition_method=OFFICIAL_LIVE_BROWSER`.
- **New `nepse_live.py`** — governed one-shot browser read (`_read_raw_dom`: chromium
  `--disable-http2 --no-sandbox`, one context/page, per-response `check_domain`
  revalidation, teardown) separated from **pure parsing** (`parse_index_widget`,
  `parse_today_rows`, `build_snapshot`) so parsing is fully testable via an injected
  `reader`. Typed failures; child-RSS metric via `getrusage`.
- **New `nepse_live_service.py`** — `NepseLiveService`: ONE bounded browser worker, cached
  last snapshot, **bounded refresh** (open 60 s / closed 1800 s; skips reads inside the
  interval — never hammers), **failure containment** (preserve last-good marked STALE;
  never fabricate, never fall back to unofficial sources). Additive tables
  `live_market_snapshot` + `live_market_observation` on the existing `MarketDataStore`
  (clearly NOT `md_bars`, NOT a second store). Read-only consumers:
  `central_command_live_projection` (no trade controls), `chat_answer_live`,
  `voice_answer_live`, `catalyst_current_context` (CURRENT_MARKET_CONTEXT only),
  `trading_guardian_live_context` (execution_authority=False). `get_default_service()`
  process singleton so server + scheduler share one worker.
- **Extended `scheduler.py`** — thin `nepse_live_refresh()` reusing the singleton (no new
  scheduler).
- **Extended `server.py`** — read-only routes `/api/v1/market/nepse/live[/full|/health|
  /chat]` (sync handlers → threadpool; sync Playwright cannot run on the asyncio loop) and
  `/market/nepse` internal panel (index/breadth/turnover/top-movers/freshness + official
  source link; **no** trade controls).
- **Reused:** `check_domain`, chromium flags + per-response revalidation pattern,
  `MarketDataStore`, `normalize_symbol`/`instrument_id_for`, `FreshnessPolicy` concept. No
  second browser framework / scheduler / event bus / store / symbol registry / risk engine.

## Freshness & market state
`LIVE / RECENT / STALE / UNAVAILABLE / MARKET_CLOSED / PAGE_ERROR / SCHEMA_CHANGED`. A
CLOSED market is always reported `MARKET_CLOSED` (never dressed as LIVE); an OPEN market
ages against the source "as of" time (LIVE ≤ 90 s, RECENT ≤ 15 min, else STALE). Every
UI/chat/voice answer exposes source + observed time, e.g. *"NABIL was observed at NPR
552.00 on the official NEPSE page (market is CLOSED, as of Sep 11, 2026, 3:00:00 PM)."*

## Real live validation (Phase 24)
`NepseLiveService().refresh()` against the production site:
- **345 securities** observed; NABIL ltp 552.00 (O/H/L 552/554.90/551, vol 37,182),
  SCB 648.00, HDL 1192.00 — all `RESOLVED`.
- Index 2,559.49 (+27.94 / 1.10%), turnover Rs 4,360,159,487.26, breadth 238/30/9.
- Market **CLOSED** → freshness `MARKET_CLOSED`, health `NEPSE_MARKET_CLOSED` (honest).
- Central Command projection (controls `[]`), chat (symbol/index/volume/freshness), voice
  (Nepali/English), catalyst current-context, TG read-only context all read the same
  snapshot. Latency ~21 s, **1 worker, peak child RSS ~317 MB**.
- Store audit: **md_bars=0, md_quotes=0**, live_snapshot + live_observation written.

## Catalyst / historical boundary (Phases 16–17)
Live observation feeds catalysts as `CURRENT_MARKET_CONTEXT` (`is_historical_reaction:
false`) only. Historical market-reaction still requires canonical `md_bars`. No long-period
indicators (RSI/MACD/MAs) are computed from a single live snapshot — only current-day
range/change/volume/turnover/breadth.

## Security / authority (verified)
Official-domain restriction (seed + per-response `check_domain`); no broker/TMS pages, no
owner cookie/token/password access, no XHR token replay, no CAPTCHA bypass, no order forms,
no arbitrary navigation, no `javascript:` execution, no localhost/private-IP escape, **no
file downloads** on the live path. `insert_bar`/`expect_download`/`save_as` absent from the
live modules (test-enforced). `ExecutionGateway.execute`=0, TG trade=0, broker=0, orders=0,
portfolio writes=0, withdrawals=0, leverage=0. Browser is READ-ONLY observation.

## Tests
`tests/test_nepse_live_v1.py` **18** (index/LTP/today-price parse, closed & open freshness,
schema-changed, page-unavailable, injected observe, bounded refresh, last-good preservation,
storage-not-md_bars, Central Command, chat, voice, catalyst context, TG context,
no-authority imports, no-DOM→canonical/no-download) + acquire 16 + research 10 = **44**;
full regression **892 passed / 0 failed**. Frozen `b771d761` + `4d685383` = **0 diffs**.

## Limitations
1. Validated during **market CLOSED** (Sat/holiday); open-market LIVE freshness proven by
   unit, not yet by a real open-session read.
2. Snapshot latency ~21 s/read (Angular render waits); bounded interval, not sub-second —
   we report *observed*, never *real-time*.
3. `browser_rss_mb` via `getrusage(RUSAGE_CHILDREN)` (peak child RSS), not a per-process gauge.
4. Bid/ask/market-depth not read (public today-price table has no L2); best_bid/ask = None.
5. Observation series (`BROWSER_OBSERVATION_SERIES`) accrues going forward; not tick-accurate.

## Verdict
Genuine current official NEPSE market state is **observed live from the rendered public
website** (345 securities + index + breadth), normalized, timestamped, freshness-gated,
stored as `LIVE_BROWSER_OBSERVED`, and served read-only to Central Command / chat / voice /
catalyst current-context / Trading-Guardian context — with **zero** trade authority, no
downloads, and canonical history untouched. Open-session LIVE validation still pending ⇒

**SAATHIOS_LIVE_NEPSE_BROWSER_MARKET_DATA_CERTIFIED_WITH_LIMITATIONS.** Not frozen.

## Exact next milestone
`M — OPEN_SESSION_LIVE_NEPSE_VALIDATION_AND_STREAMING`: validate a real market-OPEN read
(freshness LIVE, changing index/LTP), then push live snapshots to Central Command over the
existing SSE/event bus and prove bounded refresh cadence over a full trading session.
