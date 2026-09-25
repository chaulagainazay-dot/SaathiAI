# SaathiOS — Automated Official NEPSE Artifact Acquisition (v1)

**From `82ee9184`; Research Surface frozen `b771d761`; Fusion `4d685383`.** Deterministic
Playwright acquisition of the OFFICIAL NEPSE Today's-Price CSV via the site's own visible
**"Download as CSV"** control. The downloaded **file** — not DOM text, XHR JSON, or scraped
cells — is the input to the existing canonical importer. No token replay, anti-bot bypass,
CAPTCHA solving, broker/TMS pages, Browser Use, or Agent Reach. One browser worker, torn down
after use. Read + download only; the sole canonical write is `owner_import.run_import`.

## Discovery (live)
`nepalstock.com/today-price` (Angular SPA) exposes an official **Download as CSV** control
(`i.fa-download` / `table__file`). Clicking it under `page.expect_download()` yields a genuine
file: `Today's Price - 2026-09-11.csv`, 53,794 B, via a `blob:https://www.nepalstock.com/…`
origin (the app assembles its own authorized export client-side). **Classification:
PUBLIC_OFFICIAL_BROWSER_DOWNLOAD** — canonical auto-ingestion permitted.

Real CSV columns: `Id, Business Date, Security Id, Symbol, Security Name, Open Price, High
Price, Low Price, Close Price, Total Traded Quantity, Total Traded Value, Previous Day Close,
52W H/L, …` — full OHLC + date + volume. The existing importer `_COL_ALIASES` already maps
these (`open`→"Open Price" via startswith, `volume`→"total traded quantity", `date`→"business
date"). **No parser change required.**

## Components
- **New** `nepse_acquire.py`: `acquire_today_price` (governed Playwright download; domain policy on seed + download origin — `blob:` accepted only from nepalstock; typed states DOWNLOAD_AVAILABLE / NOT_YET_PUBLISHED / SITE_UNAVAILABLE / ANTI_BOT_BLOCKED / DOWNLOAD_FAILED / UNEXPECTED_DOWNLOAD_ORIGIN / PLAYWRIGHT_UNAVAILABLE; playwright lazy-import), `acquire_and_import` (→ existing importer, never falls back to scraped/third-party prices), `acquisition_health`.
- **Extended** `owner_import.run_import`: `acquisition_method='OFFICIAL_BROWSER_DOWNLOAD'` is now canonical-eligible provenance (OFFICIAL_VERIFIED, `verification_method=OFFICIAL_BROWSER_DOWNLOAD`) alongside owner attestation — single code path for both `OWNER_MANUAL_OFFICIAL_DOWNLOAD` and `AUTOMATED_OFFICIAL_BROWSER_DOWNLOAD` (no duplicate logic).
- **Extended** `scheduler.py`: thin `nepse_eod_ingest()` post-session entrypoint (reuses the existing scheduler; NEPSE close time not modeled → `NEPSE_CALENDAR_LIMITED`, bounded single attempt).
- **Reused unchanged:** `MarketDataStore`/`md_bars`, `MDBar`, `normalize_symbol`, importer validation/idempotency/revision/available_at, `canonical_bar_reader`, `GovernedBrowser` domain policy (`check_domain`). No new store/schema/registry/scheduler/parser. XLSX not needed (official export is CSV) — not added.

## Live validation (real, not fixtures)
`acquire_and_import()` against the production canonical store:
- Acquisition **DOWNLOAD_AVAILABLE**, `Today's Price - 2026-09-11.csv`, blob origin nepalstock, 53,794 B, provenance `OFFICIAL_BROWSER_DOWNLOAD`.
- Import **IMPORTED**: 345 seen, **341 valid, 341 inserted**, 4 rejected (no-trade rows, not fabricated), 341 symbols resolved, trading_date **2026-09-11**, `available_at = conservative retrieval boundary`.
- Point-in-time: NABIL close 552; **0 bars visible before available_at**.
- **8.6 s, peak RSS 40.2 MB, 1 worker**; health `CANONICAL_DATA_AVAILABLE` (341 bars).

## Catalyst revalidation (honest)
13 ResearchEvents → **10 resolve to canonical bars**, 3 `SYMBOL_UNRESOLVED` (Nepali-headline
notices). All 10 → **INSUFFICIENT_HISTORY** (`before=0 after=1`): a single imported session with
`available_at=today` has no bar available BEFORE same-day event publications. Market-**data** gap
is closed; market-**reaction** accrues as daily imports build multi-session, knowledge-time-safe
history going forward.

## Retrospective vs knowledge-time (Phase 15)
- `RETROSPECTIVE_MARKET_REACTION` = **LIMITED** (needs ≥2 sessions; one imported so far).
- `HISTORICAL_KNOWLEDGE_TIME_REPLAY` = **LIMITED** (this backfill's `available_at=today`; correct going forward — each daily download stamps availability at download time).

## Security / authority (verified)
Read + download only; no password/cookie/token extraction, no token replay, no CAPTCHA bypass,
no broker/TMS navigation, no orders. Download origin restricted to nepalstock (`UNEXPECTED_DOWNLOAD_ORIGIN` otherwise). `nepse_acquire` never calls `insert_bar` or scrapes DOM cells (`query_selector`/`inner_text` absent; uses `expect_download`; writes only via `run_import`) — test-enforced. `ExecutionGateway.execute`=0, TG trade=0, broker=0, portfolio writes=0. Canonical md_bars writes ONLY via the importer; non-canonical writes=0. Browser Use DEFER; Agent-Reach non-canonical.

## Tests
`tests/test_nepse_acquire_v1.py` **10** (origin governance, acquire+import, official schema
mapping, idempotency, failure containment/no-fallback, unexpected-origin, health, no-DOM/direct-
write gate, no-authority-imports, point-in-time) + 15 owner-import + 15 market-intel + research
regression = **56 green**. Frozen baselines 0 diffs.

## Limitations
1. Single session imported so far → catalyst market-reaction `INSUFFICIENT_HISTORY` for current events; multi-session accrues via daily runs.
2. Scheduler hook added but daily multi-day cadence not yet run/proven; NEPSE trading-calendar close time not modeled (`NEPSE_CALENDAR_LIMITED`).
3. `available_at` is conservative retrieval boundary (retrospective, not historical knowledge-time for pre-download dates).
4. 3/13 events unresolved (Nepali-headline notices without a ticker). XLSX export path not implemented (official export is CSV).

## Verdict
Genuine official NEPSE artifact **automatically acquired, validated, and imported** to canonical
`md_bars` with point-in-time safety, idempotency, provenance, and zero trade authority — but
single-session coverage + un-proven daily cadence + pending catalyst reaction ⇒

**SAATHIOS_AUTOMATED_NEPSE_ACQUISITION_CERTIFIED_WITH_LIMITATIONS.** Not frozen.
Market Intelligence Fusion stays `CERTIFIED_WITH_LIMITATIONS`: the **market-data limitation is now
closed** (canonical feed exists), while **coverage/knowledge-time accrual + server-side portfolio
context remain** open.

## Exact next milestone
`M — DAILY_NEPSE_ACCRUAL_AND_CATALYST_REACTION`: run the scheduled `nepse_eod_ingest` across
multiple trading sessions to accumulate knowledge-time-safe history, then re-run catalyst
market-reaction gates (expect events to move from INSUFFICIENT_HISTORY → OK as ≥2 sessions
around an event accrue). Separately: owner-portfolio holdings import to close the Fusion
`portfolio_context` gap. Browser Use stays DEFER.
