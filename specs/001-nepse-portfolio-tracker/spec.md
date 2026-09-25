# Feature Specification: NEPSE Portfolio Tracker

**Feature Branch**: `feature/nepse-portfolio-tracker`
**Created**: 2026-09-03
**Status**: Draft → Implemented (MVP)
**Input**: Artifact "NEPSE Tracker Teardown" (nepseportfoliotracker.app) — a nine-screen,
field-by-field teardown reframed as a build spec, delivered through the SaathiOS
Spec Kit (spec-driven delivery) system in an isolated git worktree.

## Source & Scope

The linked teardown maps nine screens of a Nepal Stock Exchange (NEPSE) portfolio
tracker. This feature builds those screens **inside SaathiOS** (`saathi-os`, Next.js
app-router) as a self-contained module at route `/nepse`, backed by a **pure,
deterministic data layer** in `lib/nepse/`.

### Constitution alignment
- **Article I (Single Execution Boundary):** the module performs **no external side
  effects** — no live brokerage connection, no network price feed, no OAuth. All
  market/broker/fundamental data is a bounded, in-repo **snapshot seed**; user data
  (portfolios, transactions, watchlist) lives in the browser's `localStorage`.
- **Article III (Secrets Never Travel):** no credentials, no `type="password"`, no
  broker login. Import is file-parsing only.
- Every screen carries an explicit boundary banner: **"SNAPSHOT / SEED DATA — NOT A
  LIVE NEPSE FEED"** so display is never mistaken for accounting or market truth.

Out of scope for the MVP (documented, not built): live price feed, real broker
disclosures ingestion, the paid "Analysis (Pro)" model, drawing-toolbar candlestick
charting, and price alerts. The scoring model is a transparent deterministic
composite, explicitly labelled as illustrative — not an "AI" black box.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Track a portfolio (Priority: P1)
A NEPSE investor creates a named portfolio and logs buy/sell transactions; the app
shows total value, total investment, and receivable, all derived from the
transaction log plus the snapshot price feed.

**Why P1:** portfolio math is the core promised value and the densest correctness
surface; it is fully testable as pure functions.

**Independent Test:** feed a transaction list + price map to `computePortfolio()` and
assert holdings, invested, current value, receivable, and P&L. Delivers value even
with every other screen absent.

**Acceptance Scenarios:**
1. **Given** an empty state, **When** the user creates a portfolio, **Then** it gets a
   name + one of 12 preset colors and becomes the active scope; add-transaction is
   blocked until a portfolio exists.
2. **Given** two BUY lots and one partial SELL of a symbol, **When** totals compute,
   **Then** remaining quantity, weighted-average cost, invested, current value (qty ×
   LTP), realized P&L, and unrealized P&L are correct.
3. **Given** a SELL that exceeds held quantity, **When** totals compute, **Then** the
   transaction is rejected (long-only, no negative holdings).

### User Story 2 — Screen all stocks (Priority: P2)
The user browses all listed instruments with LTP, % change, a 0–100 score, a
Buy/Sell/Neutral signal, valuation tag, RSI, P/E, P/B — searchable by symbol/company,
filterable by sector, sortable on any numeric column, paginated 50/page.

**Independent Test:** call `screen(stocks, {query, sector, sort, page})` and assert the
returned rows, ordering, and page window.

**Acceptance Scenarios:**
1. **Given** a sector filter, **When** applied, **Then** only that sector's stocks show.
2. **Given** a sort on "% change" desc, **When** applied, **Then** rows are ordered by
   day change descending with pagination preserved.
3. **Given** a free-text query, **When** it matches symbol or company, **Then** matches
   are returned case-insensitively.

### User Story 3 — Market overview (Priority: P2)
Exchange-wide state: NEPSE index level + day change + open/closed, turnover, volume,
market cap, an advance/decline sentiment gauge, and a per-sector performance grid.

**Independent Test:** `marketSnapshot()` returns index, breadth counts, and sector
rows; `sentiment(adv, dec)` returns a bounded 0–100 needle + mood label.

### User Story 4 — Stock detail (Priority: P3)
One page per instrument: Overview (OHLC, 52w H/L, market cap, EPS, P/E, book value,
P/B, dividend yield, dividend history) and per-stock Brokers (buy/sell qty & amount,
net, trade count).

### User Story 5 — Watchlist & Brokers (Priority: P3)
A portfolio-independent watchlist (add by symbol, custom groups, live-style columns)
and an exchange-wide broker ranking (top-3 cards + sortable table, search by name/code).

### User Story 6 — Import holdings (Priority: P3)
File-based onboarding: parse Meroshare CSV, TMS Excel-export (CSV form), and Nepal
Share CSV/TSV into transactions that land in a portfolio.

**Independent Test:** parse a fixture of each format → normalized transaction rows.

## Requirements

| ID | Requirement |
|----|-------------|
| M400-NEPSE-001 | `computePortfolio(transactions, priceMap)` returns per-symbol holdings (qty, avg cost, invested, value, unrealized/realized P&L) and portfolio totals; rejects over-selling. |
| M400-NEPSE-002 | `screen()` supports search, sector filter, multi-column sort, 50/page pagination over the full instrument set. |
| M400-NEPSE-003 | `scoreStock()` = deterministic 0–100 composite; `signalFor(score)` ∈ {Buy,Sell,Neutral}; `evaluationFor()` = valuation tag. Pure, labelled illustrative. |
| M400-NEPSE-004 | `marketSnapshot()` + `sentiment()` power the Market screen; sector taxonomy tags every stock. |
| M400-NEPSE-005 | CSV/TSV importers for Meroshare, TMS, Nepal Share normalize to the transaction schema. |
| M400-NEPSE-006 | `/nepse` routes render Portfolio, Market, All Stocks, Stock detail, Watchlist, Brokers with the shared NepseShell (ticker + tabs + boundary banner). |
| M400-NEPSE-007 | No external side effects, no password field, no broker login; every screen shows the snapshot-data banner. |
| M400-NEPSE-008 | Light + dark theme parity via CSS tokens; reduced-motion respected on the ticker. |

## Success Criteria
- `npm test` includes `lib/nepse.test.js` and passes.
- `next build` compiles the `/nepse` route tree with no errors.
- Every requirement above maps to at least one test (convergence gate).
