# MD-1 — Canonical Point-in-Time Market Data Contract

`saathi/platform/market_data/contract.py`

## The defect this closes

SaathiOS was `as_of`-only. `grep -rn available_at saathi/ tests/` returned one
hit before this milestone, and it was a comment.

A research or backtest filter written `as_of <= decision_time` admits a
quarterly result **the moment the quarter ends** — weeks before anyone could
have read it. That is the look-ahead defect recorded in
`docs/evaluations/tradingagents/LOOKAHEAD_AUDIT.md` (upstream scored 6/10 on
exactly this), noted there as a thing to avoid, and unfixed here until now.

## Four timestamps

| Field | Meaning |
|---|---|
| `event_timestamp` | when the underlying market event occurred |
| `as_of` | the economic period the observation represents |
| **`available_at`** | the earliest instant SaathiOS could *legitimately* have known it — publication, filing, release |
| `received_at` | when SaathiOS actually took delivery |

For a live quote all four collapse to roughly one instant. They diverge sharply
for anything published on a lag: fundamentals, indices, corporate actions,
revised series.

**The only correct look-ahead filter is `available_at <= decision_time`.**

## The invariant, and the test that pins it

```
quarter ends   2026-03-31   (as_of)
published      2026-05-15   (available_at)
decision       2026-04-10
```

`as_of < decision_time`, so an `as_of` filter admits it. `visible_at()` refuses
it. `test_as_of_alone_would_have_admitted_it_and_that_is_the_bug` asserts both
answers side by side so the difference cannot be edited away by accident.

## Ordering constraints enforced at construction

- `available_at >= as_of` — an observation cannot be knowable before the period
  it describes has ended
- `received_at >= available_at` — SaathiOS cannot receive data before publication
- every timestamp must be timezone-aware; a naive datetime compares wrongly
  across timezones and would silently corrupt point-in-time filtering

## Types

`AssetClass` · `MarketStatus` (incl. `UNKNOWN`, the safe default) ·
`DataAvailability` · `PointInTime` · `ProviderReference` · `MarketDataEvent` ·
`CanonicalQuote` · `CanonicalTrade` · `CanonicalBar` · `MarketDataSnapshot` ·
`visible_at()`

`MarketDataSnapshot` keeps `withheld_events` alongside `visible_events`, so a
decision can prove not just what it saw but what it was correctly denied.

## Convergence, not a fifth enum

Four `AssetClass` enums exist in this tree:

| Location | Members |
|---|---|
| `platform/trading_models.py` | EQUITY, ETF, CRYPTO, CASH |
| `tg/broker_sandbox/models.py` | EQUITY, CRYPTO, FUTURES, OPTIONS, FX, OTHER |
| `tg/market_data/models.py` | equity, etf, index, crypto, fx, futures, macro, fundamental, mixed |
| `investment.py` | crypto, stock, real_estate, saas, ai_startup, … |

The first three are instrument asset classes with different casing and members.
The fourth is a **different domain** — personal investment categories — and is
deliberately left alone; converging it would be wrong.

`asset_class_from_legacy()` adapts the first three. The legacy enums are **not
deleted**: they have consumers this milestone has no mandate to break. An
unmappable value **raises** rather than defaulting — silently defaulting an
unknown asset class to EQUITY would misclassify the instrument in concentration
limits, construction, and risk.

## Two defects found by fresh-context review

An independent session reviewed the module cold and found the same root cause
twice: `Decimal("0")` as a field default conflates *absent* with *legitimately
zero*.

| # | Defect | Consequence |
|---|---|---|
| R1 | Crossed-quote check required `bid > 0 and ask > 0`, so `bid=100, ask=0` passed construction | `spread` returned **-100**, `mid` returned **50** — computed from one real side and one absent |
| R2 | OHLC ordering checks were satisfied by `open=low=close=0, high=100` | a bar describing a session that traded up to 100 with a low of zero |

Fixed: `is_two_sided` gates `spread`/`mid`, which now raise rather than return
a meaningless number; a bar must be fully priced or fully empty (a genuine
no-trade session stays representable). Both have regression tests.

## Authority

Data only. No execution, approval, risk, or ledger authority. No network I/O.
An AST test asserts the module imports nothing from `fund_ledger` or the
execution plane.

## Not done in MD-1

No provider adapter, no network call, no migration of existing consumers onto
the canonical types. Adapters from `MDQuote` / `trading_models.Quote` are
deliberately deferred to the milestone that first needs them, so the contract
lands without touching 7,600 passing tests.
