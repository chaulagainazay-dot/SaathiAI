# STRATEGY-OBSERVATION-1 — the canonical shadow → attribution → monitoring adapter

Branch `feature/nepse-completion`, from `04e80011` (verified HEAD, clean, in sync).
Repository reality was recovered before any work: the reported SHA was checked
against `git status`/`git log`, not trusted.

The brief called this a **small convergence milestone** and forbade building
another monitoring framework. That constraint held: **38 changed lines across two
existing files**, one new adapter, one new test file. No new framework, no second
Observation type, no third performance calculator.

## Discovery — what already existed

| Component | Lines | Verdict |
|---|---|---|
| `tg/shadow_session.py` — durable sessions, fills, counterfactuals, reconciliation | 567 | **EXTEND** (PIT bound only) |
| `tg/attribution_source.py` — shadow → attribution record bridge | 118 | **EXTEND** (PIT bound only) |
| `tg/attribution_v2.py` — gross/net, cost split, turnover, drawdown, report id | 537 | **REUSE unchanged** |
| `tg/strategy_monitor.py` — `Observation`, `MonitorPolicy`, nine dimensions | 527 | **REUSE unchanged** |
| `portfolio_performance/engine.py::record_observation_from_state` | — | **REJECT** — a NAV recorder, different concern despite the name |

No existing adapter produced a monitoring `Observation`. That was the only real gap.

## The structural discovery that shaped the design

`shadow_fills` carries **only `seq`** — no timestamp. `shadow_events` carries
`observed_at`. So **seq is the session's canonical ordering** and a time cutoff
must resolve *through* events to a sequence bound. Every point-in-time path in
this milestone is built on that fact rather than on a clock.

## What was built

`tg/strategy_observation.py` — `observation_from_shadow()` returning an
`AdapterResult`: the monitor's own `Observation`, plus `status`,
`unavailable_fields`, `strategy_version` and the attribution `report_id`.

Flow, with no manual reshaping at any hop:

```
shadow session → records_from_session → performance_attribution_report
              → observation_from_shadow → evaluate_strategy_health → verdict
```

### The PIT leak that discovery exposed

The first draft bounded `fills()` and `derive_portfolio()`, then filtered
attribution records by symbol afterwards. **That was wrong.** A symbol traded both
inside and outside the window would keep its entire history, leaking later P&L
into an earlier answer. The bound was pushed down into `records_from_session` and
`counterfactuals_from_session` instead, so the portfolio state and the fills are
cut at the *same* point. This is the substantive change to existing files.

### Honesty rules enforced

- **Benchmark unavailable stays `None`.** Never `0`, which the monitor would read
  as a real measurement of a flat benchmark.
- **Zero fills produces `net_return = None`**, not `0` — "broke even" is a claim
  nobody observed.
- **Drawdown is absent without a supplied equity path.** The session persists no
  valuation series; marking open positions at cost would describe a flat equity
  curve the portfolio never had.
- **Mode is carried verbatim and never defaulted.** A session whose mode cannot be
  read is *refused*, not labelled `SHADOW`.
- **A cutoff before any recorded event observes nothing** (`-1`), not everything.
- **Closed trades are round trips**, not fills — otherwise one unclosed buy would
  make a strategy look sufficiently observed.
- **Data failure ≠ strategy failure.** Stale data and reconciliation breaks reach
  the monitor as `DATA_QUALITY_BLOCKED`, never as `DEGRADED`.

### Determinism

The adapter imports no `datetime`, `time` or `calendar`, and calls no
`now`/`utcnow`/`today`/`monotonic`. Elapsed seconds are computed by civil-date
arithmetic (Hinnant), verified against `datetime` across epoch, leap-day and
in-period samples. Both properties are pinned by **AST inspection**, not grep, so
a comment can neither satisfy nor break them.

## Verification

**26 focused tests, all 14 required scenarios**, every one driving the real chain
on a real sqlite store — no stubs, because the thing under test *is* the wiring.

| Scenario | Result |
|---|---|
| healthy · insufficient · drawdown · benchmark · cost breach · regime | pass |
| stale data · reconciliation · ambiguous provenance · zero trades | pass |
| missing benchmark · partial cost · restart · future event excluded | pass |
| mode integrity · double cutoff refused · no execution authority · no second DTO | pass |

Restart reproducibility is proven by **equal attribution `report_id`** — a content
hash over the whole report body, not just the handful of asserted fields.

Regression: **272 passed** across shadow session, shadow trading, shadow engine,
attribution v2, performance attribution v2, strategy monitoring, financial
numeric, shadow adoption and this milestone.

Full suite: **8442 passed, 11 failed, 2 skipped** (15m54s). The eleven failures
are a strict subset of the pre-existing baseline — release-gate and residual-path
checks (`test_ops`, `m21_3`, `m21_4`, `m22`–`m25`, `m28`, `m336_m343`) that fail
on an unclean working tree and are unrelated to this work. **Zero new failures.**
The baseline's twelfth, `test_m17_1_live::test_live_browser_launch_and_close`,
passed this run; it is environment-dependent, not fixed by this milestone.

## Defects found and fixed during adversarial review

1. **PIT leak** in the first draft's post-hoc symbol filter (above) — the most
   serious, and the reason the bridge was extended rather than wrapped.
2. **`events()` has no `max_seq`.** The draft called it with one; it would have
   raised `TypeError` on every timestamped read. Bounded in the adapter instead.
3. **Report period didn't match the observation window.** A sequence-bounded read
   passed `period_end=None`, labelling the report with an open period it did not
   cover. The window is now settled before the report is built.
4. **`AdapterResult` carried `strategy_id` and `strategy_version` with identical
   values**, implying a distinction the session cannot support. Collapsed to one.
5. **An underivable book crashed instead of reporting.** `reconcile` catches the
   `ShadowReconciliationError` an oversell raises, but the adapter then derived
   the portfolio again — and every downstream layer derives it too. A monitoring
   caller would have taken an exception where it needed a status. The adapter now
   stops at the reconciliation verdict and returns `RECONCILIATION_REQUIRED` with
   no performance fields. The raw layer still fails loudly; the test asserts both.
6. **The DTO-identity test was over-strict.** `test_strategy_monitoring_1.py:357`
   legitimately reloads the monitor to prove restart determinism, which rebinds
   the class object. Now compared by origin (`__module__`/`__qualname__`), which
   still catches a forked type.

## Certification, with limitations

**CERTIFIED** for use as the single adapter between persisted shadow evidence and
strategy monitoring, subject to five stated limitations:

1. **The partial-cost branch is unreachable from this source.** `shadow_fills`
   stores fee, spread and slippage as non-null columns, so every record arrives
   with a complete split; zeros are a real split, not a missing one. The branch is
   retained as a defence for a future source, and the *contract it depends on*
   (`cost_decomposition` still returning `total_cost` on its DATA_INSUFFICIENT
   path) is pinned by its own test. Proven, not assumed.
2. **Drawdown requires a caller-supplied equity path.** Until a valuation series
   is persisted per session, `max_drawdown` is `None` for sessions whose caller
   supplies none — and a caller-supplied path is *not* validated for PIT safety by
   this adapter.
3. **Benchmark returns are caller-supplied.** No benchmark series is computed or
   fetched here; the adapter only refuses to invent one.
4. **The adapter is not strictly read-only.** `store.reconcile()` fails closed by
   flipping a broken session to `RECONCILIATION_REQUIRED`. That is
   SHADOW-TRADING-1 acting on its own history, not an adapter decision, and it is
   recomputed from history — repeated reads converge, pinned by test.
5. **Regime and staleness flags are caller-supplied.** The session records no
   regime label; the adapter passes through what it is given rather than deriving
   a regime it cannot observe.

### Invariants held

`NO_ADAPTER_EXECUTION_AUTHORITY` (AST-pinned: no `submit`/`place`/`execute`/
`record_fill`/`append_event`/`set_status`/`commit`), `NO_FUTURE_DATA_LEAKAGE`
(PIT bound pushed to the source; no clock, AST-pinned),
`NO_COUNTERFACTUAL_AS_ACCOUNTING_FACT` (net return reads ACCOUNTING evidence
only), `NO_DATA_FAILURE_CLASSIFIED_AS_STRATEGY_FAILURE`,
`NO_MONITOR_EXECUTION_AUTHORITY` (`authorizes_execution=False` on every path).
