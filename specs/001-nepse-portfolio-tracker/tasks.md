# Tasks: NEPSE Portfolio Tracker

Ordered; each maps to requirement IDs. [x] on completion.

## Phase 1 — Pure data layer (testable in isolation)
- [x] T01 `lib/nepse/format.js` — Rs money/number/pct + `isMarketOpen()` — (M400-NEPSE-006)
- [x] T02 `lib/nepse/data.js` — snapshot: stocks, sectors, market, brokers, index history — (M400-NEPSE-004)
- [x] T03 `lib/nepse/analytics.js` — `rsi`, `scoreStock`, `signalFor`, `evaluationFor` — (M400-NEPSE-003)
- [x] T04 `lib/nepse/screener.js` — `screen()` search/filter/sort/paginate — (M400-NEPSE-002)
- [x] T05 `lib/nepse/portfolio.js` — `computePortfolio()` + over-sell reject — (M400-NEPSE-001)
- [x] T06 `lib/nepse/importers.js` — Meroshare/TMS/Nepal Share parsers — (M400-NEPSE-005)
- [x] T07 `lib/nepse/store.js` — localStorage CRUD (guarded) — (M400-NEPSE-001)

## Phase 2 — Tests (convergence gate)
- [x] T08 `lib/nepse.test.js` — cover T01–T06 + structural route/boundary checks — (all)
- [x] T09 register `lib/nepse.test.js` in `package.json` test script — (all)

## Phase 3 — UI
- [x] T10 `components/nepse/NepseShell.jsx` — ticker + tabs + boundary banner — (M400-NEPSE-006/007)
- [x] T11 `app/nepse/nepse.css` + `app/nepse/layout.jsx` — palette light+dark — (M400-NEPSE-008)
- [x] T12 `app/nepse/page.jsx` — Portfolio home (US1) — (M400-NEPSE-001)
- [x] T13 `app/nepse/market/page.jsx` — Market (US3) — (M400-NEPSE-004)
- [x] T14 `app/nepse/stocks/page.jsx` — screener (US2) — (M400-NEPSE-002)
- [x] T15 `app/nepse/stocks/[symbol]/page.jsx` — detail (US4) — (M400-NEPSE-003/004)
- [x] T16 `app/nepse/watchlist/page.jsx` + `app/nepse/brokers/page.jsx` (US5) — (M400-NEPSE-002)

## Phase 4 — Verify
- [x] T17 `npm test` green
- [x] T18 `npm run build` compiles `/nepse`
- [x] T19 commit + push branch
