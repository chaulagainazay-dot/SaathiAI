# FINANCIAL-NUMERIC-1 — fail-closed financial numeric parsing

Branch `feature/nepse-completion`, from `e7850e8c` (verified HEAD, clean, in sync).

## The defect

A numeric parser swallowed every failure and returned zero, so `"abc"`, `True`,
`object()` and a `ShadowOrder` all became `Decimal("0")` — a valid-looking amount
manufactured from garbage, indistinguishable downstream from a real zero.

## Blast radius — larger than the observed call

`PaperBroker` exposed it, but `D` is not PaperBroker's. There are **two**:

| Parser | Reached | State before |
|---|---|---|
| `trading_models.D` | market data, safety (evaluator/metrics/store/service), strategy, `tg/domain`, `tg/risk`, paper broker | permissive: invalid → 0 |
| `fund_ledger.money.D` | portfolio construction, portfolio performance, fund ledger, rebalance | already raised on invalid, but accepted `"NaN"`/`"Infinity"` |

Two further wrappers **defeated the parser entirely** by re-swallowing its errors:

- `tg/domain.coerce_decimal` — `except: return Decimal(default)`, feeding Guardian
  entry price, stop price, take-profit, stop distance and total return. A stop
  distance of zero is not a small risk; it is a risk check that cannot fail.
- `tg/historical/qualification._dec` — same pattern on qualification evidence.

Classified out of scope: `financial_mission_control.dream_progress_pct` — a
display percentage with documented clamping and explicit NaN guards, not a money
or order path. The remaining 15 `except: return 0` sites are counts, durations and
scores, not financial boundaries.

## The contract

**A parser does not create economic meaning.** It answers "is this a valid numeric
representation?". Whether ABSENCE means zero is the caller's policy, written at the
caller.

Refused: `bool` (before any numeric handling — `isinstance(True, int)` is `True` in
Python), NaN, ±Infinity, non-numeric strings, non-numeric objects, over-long input,
absurd exponents, and any syntax that is not a plain number.

Preserved: `Decimal`, `int`, plain numeric strings, **legitimate zero**, negative
values (representation is valid; whether a BUY may be negative is a domain rule),
and `None`/`""` → the caller's declared `default`.

## Corrections made along the way

- **Two existing tests pinned the defect as intended behaviour.**
  `test_m62_2_market_data` asserted `D("not-a-number") == Decimal("0")` and called
  it a "safe 0"; `test_m62_trading_models` asserted `D("garbage") == Decimal("0")`.
  Both now assert refusal.
- **I wrote a false rationale into the source and corrected it.** The first comment
  claimed a Decimal NaN "compares False against everything". It does not — Python
  raises `InvalidOperation` on ordering. The real hazard is quieter: NaN propagates
  silently through arithmetic, `== 0` misses it, and it is truthy, so it travels
  far before finally raising somewhere unrelated. Infinity does not raise at all —
  it compares, and a limit check simply returns the wrong answer.
- **`"1_000"` parsed to 1000** (PEP-515 underscores) and produced a 60,000,000
  reservation. String input now must match a plain numeric pattern.
- **`"1\n"` slipped the strict pattern** because Python's `$` also matches before a
  trailing newline. Anchored with `\Z`.
- **`reserve_for_buy` accepted `None`** and answered `0.00` — a buy admitted
  against no reserved cash. Quantity and the applicable price are now required
  explicitly, because absence is a caller policy and this caller means "refuse".

## Limitations

- `trading_models.D` still accepts a Python `float` (converted via `str`, so no
  binary contamination in the arithmetic). `fund_ledger.money.D` refuses floats
  outright. The asymmetry is deliberate — market-data and safety callers pass
  floats — and is pinned by a test so it stays deliberate rather than drifting.
