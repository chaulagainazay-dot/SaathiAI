# SaathiOS — Market Workspace Authenticated Browser E2E + Freeze (v1)

**From `cecbba63`; Research Surface frozen `b771d761`; Fusion `4d685383`.** Authenticated
end-to-end validation of the native `/market` workspace, plus one genuine robustness fix
found during the run. This milestone adds **no feature** — it proves the certified workspace
inside a real authenticated SaathiOS session and freezes the integration semantics.

## Auth path used (no owner password, no forged token)
The platform's established mechanisms: the deterministic stateless session token
(`_session_token()`, seeded from the stored password-hash/`SAATHI_TOKEN` — no plaintext
password) as the `baadar_session` cookie for the browser, and the configured `SAATHI_TOKEN`
service token (`x-saathi-token`) for API checks. No credentials entered, no secret printed,
no fake token injected.

## Robustness fix (genuine defect found)
Under the test setup (a second backend instance contending for the security SQLite), an
invalid **and even a valid** token could turn `_is_authed` into a **500** because
`get_registry()`/`sessions.validate()` raised on a locked DB before the cheap token checks.
Fix (server.py, minimal, no auth-semantics change):
1. Check the legacy `SAATHI_TOKEN` (cheap, no DB) **before** the registry.
2. Wrap the registry lookup and the session-store `sessions.validate()` in `try/except` so a
   store failure falls through to the deterministic token check / a clean 401 — never a 500.
Verified: good token → 200; bad token → **401 ×5 (bounded, no loop, no 500)**.

## Environment
Fresh `cecbba63` backend instance on `127.0.0.1:8801` (producer enabled → one closed
official snapshot seeded; the persistent owner daemon on :8765 was unresponsive/stale during
the run and was not disturbed). Frontend network confirmed **same-origin only**.

## Authenticated results (real data)
- **Auth gating** — no-token 401; token 200.
- **Overview** — Index **2585.04** (+25.55 / 0.99%), turnover 4,688,682,303.71, volume
  11,595,654, breadth **226/47/2**, CLOSED, observed **Sep 14, 2026 3:00:00 PM**, freshness
  MARKET_CLOSED, badge "Official NEPSE · live observed"; 1.3 s.
- **Stocks** — 588 universe; rows carry **official LTP** (`ltp_source=OFFICIAL_PAGE_OBSERVED`,
  "O" badge): NRN 1448 / LEC 250 / TAMOR 516.9 / RSML 2936, with %chg/volume/turnover/sector/
  P·E; sort works; ~1.7 s (35 ms cached).
- **Sectors** — 13, labeled **DERIVED_SECTOR_ANALYTICS**; top-by-change Finance 1.83%, Life
  Insurance 1.42%, Non-Life 1.38% with breadth/turnover; ~1.3 s (5 ms cached).
- **Compare** — NABIL/API/AKPL/HDL, date-intersection: 1M 2026-08-17→09-14, 3M 2026-06-15→
  09-14, **1Y 2025-09-18→2026-09-14**; normalized % (1Y: NABIL +14.70, API +30.72, AKPL
  +7.86, HDL −7.47); four colored lines correct; ~5.2 s (4 ms cached).
- **Chart** — NABIL 1Y native candlesticks + SMA overlay + volume panel; badge
  "NEPSE Portfolio Tracker · third-party"; PIT warning "HISTORICAL_KNOWLEDGE_TIME_UNSUPPORTED
  — descriptive only; current LTP authority: Official NEPSE"; oscillator (volume) in its own
  panel, not on the price axis; ~2.7 s.
- **Fundamentals/Dividends/Research/Catalysts panel (NABIL)** — reconciliation **CONFIRMED**
  (Official 554.00 · Tracker 554.00, official authority); EPS 28.36, P/E 19.53, P/B 2.24,
  div-yield 2.85%, mktcap 149.9B, 52wH 568 / 52wL 471, Commercial Banks; 1 dividend; research
  + catalyst PARTIAL_DATA (no seeded research → honest, isolated); Portfolio "not configured".
- **Reconciliation (4 symbols)** — NABIL 554/554, API 340/340, AKPL 256.70/256.70,
  HDL 1201/1201 → all **CONFIRMED** (diff 0.00, official authority; disagreements never
  hidden).
- **Chat** — source-aware: current price → **Official NEPSE (authoritative)** (NABIL 554);
  1Y trend / RSI 61.09 (descriptive) / P·E / dividends → tracker third-party; sector →
  derived. No recommendation wording.
- **SSE** — `/api/events/stream` connected (`stream.connected`); an authed refresh (336
  securities) published **`market.nepse.snapshot`** (dept FINANCE, versioned) received on the
  stream; connecting a client triggered **no** acquisition; 1 worker.

## Browser / responsive / console (Phases 17–20)
`/market` rendered with the session cookie at **desktop 1280×1000** and **mobile 390×844**:
every tab shows real data, source badges visible, PIT warning accessible, tables/chart
legible. **0 uncaught JS errors, 0 page errors.** Browser app requests hit **only
`127.0.0.1:8801`** (same-origin); no direct backend-port or tracker calls from the browser,
no MCP key/secret in payloads (tracker REST is server-side via the governed provider).

## Failure isolation (Phase 21)
Tracker outage → overview/official survive; official outage → tracker history survives
(typed states LIVE_SOURCE_UNAVAILABLE / HISTORY_SOURCE_UNAVAILABLE / PARTIAL_DATA;
unit-tested). No white-screen.

## Resource / security / authority
No tracker Chromium (REST only; the official browser is the live-NEPSE system), no Browser
Use, REST concurrency bound 2, no uncontrolled polling. No credentials/session-token/MCP-key
logged; no iframe/scraping/arbitrary-host/private-IP. tracker→md_bars=0, tracker→md_quotes=0,
official→md_bars=0, broker=0, orders=0, ExecutionGateway.execute=0, TG trade=0, portfolio
writes=0, withdrawals=0, leverage=0.

## Voice
`workspace_voice` reuses the exact workspace read models (unit-validated: sector/compare/
symbol answers with source). Physical-microphone E2E remains environment-blocked (no mic in
this context) — not faked; backend projection validated instead.

## Tests / regression / integrity
Focused workspace + tracker suites green; broader regression **1613 passed / 0 failed**.
Frozen `b771d761` + `4d685383` = **0 diffs**.

## Freeze decision
All freeze criteria met (real data in every tab, auth stability, same-origin, official-
current authority, tracker-history boundary, native charts, compare, sectors, reconciliation,
chat, voice backend projection, SSE, desktop, mobile, console clean, outage isolation,
security, zero authority writes, regression green). **FREEZE the SaathiOS
`NATIVE_NEPSE_MARKET_INTELLIGENCE_WORKSPACE` integration semantics.**

- **Freeze SHA:** this commit.
- **Recorded:** `THIRD_PARTY_API_STABILITY_EXTERNAL_LIMITATION` — the external NEPSE Portfolio
  Tracker REST contract is NOT guaranteed/frozen; only SaathiOS's integration semantics are.
- The **official live-NEPSE market-open freeze remains SEPARATE and outstanding** (still needs
  a genuine 11:00–15:00 NPT session with OPEN/LIVE + changing fields). This milestone does not
  bypass it.

## Limitations
1. Canonical owner-password login via the :3100 Next.js UI not exercised (used the platform's
   deterministic session-token mechanism — the established safe path; owner-password login is
   owner-interactive).
2. Research/catalyst panels PARTIAL_DATA without seeded research (honest, isolated).
3. Physical-mic voice E2E environment-blocked (backend projection validated).
4. Tracker history point-in-time-unsupported (descriptive; not canonical/backtest).
5. Tracker ToS/endpoint stability = external dependency risk.

## Verdict
**SAATHIOS_MARKET_WORKSPACE_AUTHENTICATED_BROWSER_E2E_CERTIFIED** — authenticated E2E proven
across all tabs with real data, native charts, source authority preserved, SSE fan-out,
desktop+mobile, clean console, zero authority expansion; workspace integration semantics
**FROZEN** (external tracker API stability recorded as a limitation).

## Exact next milestone
`M — OFFICIAL_LIVE_NEPSE_OPEN_SESSION_FREEZE` — during a real 11:00–15:00 NPT open session,
capture genuine OPEN/LIVE snapshots with changing fields (index/LTP/volume), confirm cadence
+ single-flight under the live producer, then freeze the live-NEPSE baseline. No portfolio
MCP, no signals.
