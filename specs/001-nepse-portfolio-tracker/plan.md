# Implementation Plan: NEPSE Portfolio Tracker

**Branch:** `feature/nepse-portfolio-tracker` · **Spec:** ./spec.md

## Architecture
Thin `"use client"` pages consume a **pure data layer**. All financial truth is
computed by side-effect-free functions in `lib/nepse/`, so it is unit-testable under
`node --test` with zero DOM. Per-viewer state (portfolios, transactions, watchlist)
persists in `localStorage` only.

```
lib/nepse/
  data.js        # deterministic snapshot: ~24 stocks, sectors, market, brokers, index history
  analytics.js   # scoreStock / signalFor / evaluationFor / rsi helpers (pure)
  screener.js    # screen(): search + sector filter + sort + paginate (pure)
  portfolio.js   # computePortfolio(): holdings + totals from tx log + price map (pure)
  importers.js   # parseMeroshare / parseTMS / parseNepalShare -> transactions (pure)
  store.js       # localStorage CRUD for portfolios/tx/watchlist (client-only, guarded)
  format.js      # Rs money / number / pct formatters + market-open helper (pure)
lib/nepse.test.js  # node --test coverage for every M400-NEPSE-* requirement

components/nepse/
  NepseShell.jsx # ticker strip + tab nav + boundary banner (shared chrome)

app/nepse/
  layout.jsx            # imports nepse.css, mounts NepseShell
  nepse.css             # scoped palette (Fraunces + IBM Plex, green accent) light+dark
  page.jsx              # US1 Portfolio home (create portfolio, add tx, totals, import)
  market/page.jsx       # US3 Market overview
  stocks/page.jsx       # US2 All Stocks screener
  stocks/[symbol]/page.jsx # US4 Stock detail (Overview + Brokers tabs)
  watchlist/page.jsx    # US5 Watchlist
  brokers/page.jsx      # US5 Broker ranking
```

## Design language
Adopt the teardown's identity — Fraunces display + IBM Plex Sans/Mono, restrained
green accent (`--accent`), red for declines, gold for "Pro" — as **module-scoped CSS
variables** on `.nepse-root`, defined for both light and default(dark). This keeps the
NEPSE look self-contained without touching global SaathiOS tokens (additive, per
constitution). Reduced-motion disables the ticker animation.

## Key decisions
- **No live feed.** A single dated snapshot seed; the boundary banner states it. This
  is the honest, constitution-compliant equivalent of the real app's file-based model.
- **Scoring is transparent, not "AI".** A documented weighted composite of momentum,
  RSI mean-reversion, and valuation — labelled illustrative so it is never mistaken for
  investment advice (also honors the global "no personalized financial advice" rule).
- **Long-only, no negative holdings** mirrors the SaathiOS trading posture.
- **Client store guarded** in try/catch; every read tolerates empty/blocked storage.

## Test strategy
`lib/nepse.test.js` asserts: portfolio math (multi-lot + partial sell + over-sell
reject), screener (filter/sort/paginate/search), analytics bounds & signal mapping,
importer normalization for all three formats, and structural presence of all six route
files + boundary labels + absence of `type="password"`. Then `next build` for compile
verification. This satisfies the convergence gate (every requirement → ≥1 test).
