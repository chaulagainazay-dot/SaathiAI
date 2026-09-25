# SHADOW-TRADING-1 — durable shadow operation & decision-quality certification

Branch `feature/nepse-completion`, from `83675600` (verified HEAD, clean, in sync).

## First decision — what already existed

Searched before implementing. Classification:

| Found | Verdict |
|---|---|
| `saathi/platform/tg/shadow_engine.py` (SHADOW-1) — decision-chain observer, no-order proof, cost model enforced, 8 tests | **ADAPT** — it is the engine |
| `tests/test_m19_2_shadow_adoption.py` | **REJECT** — unrelated (code-path adoption campaign, not trading) |
| `saathi/platform/tg/attribution_v2.py`, `portfolio_performance` | **KEEP** — separate concern |
| `ResearchDurabilityStore` (RESEARCH-3) | **ADAPT** — its schema idiom and connection |
| `paper_trading/*` | **KEEP SEPARATE** — paper simulates a broker; shadow does not |

SHADOW-1 is entirely in memory: kill the process and the session, the accounting
and the counterfactual record are gone. That gap is this milestone.

## What was built

`saathi/platform/tg/shadow_session.py` — a durable session layer, not a second
execution authority. Versioned schema on the canonical `ResearchStore` connection,
so shadow records live beside the decision journal they reference.

- **Restart safety.** Every event carries a per-session monotonic sequence with a
  UNIQUE key. Replaying a recorded event after a crash is a no-op, not a second
  fill, fee or cash movement. A *different* payload at an existing sequence is a
  hard error — that is history being rewritten.
- **Derived book.** The portfolio is rebuilt from fills rather than stored, so a
  restart cannot inherit a balance that has drifted from its own history.
- **Reconciliation fails closed.** A mismatch flips the session to
  `RECONCILIATION_REQUIRED` and blocks resume. Nothing is silently repaired, and
  the offending rows stay.
- **Counterfactual Guardian tracking.** A blocked proposal is recorded and its
  forward path measured, in both directions — positive means Guardian cost us,
  negative means it protected us. The table has zero execution authority: nothing
  reads it to place, size or unblock anything.
- **Unknown stays unknown.** NAV refuses rather than understating an unpriced
  position; metrics report `None`, never `0`.

## Findings

1. **A vacuous test, caught and replaced.** The first no-order proof scanned the
   broker *module* for `submit`/`place`/`execute` names, found none, and passed
   without asserting anything. It now drives `PaperBroker`'s real entry points and
   asserts the entry list is non-empty first.
2. **`PaperBroker.D()` silently zeroes non-numbers.** `None`, `"abc"`, `True` and
   arbitrary objects all become `Decimal 0`, which is why `reserve_for_buy`
   accepts a `ShadowOrder` and answers `0.00`. It is a pure arithmetic helper —
   it creates no order, position or ledger row, so it is NOT a shadow-to-live
   path — but a cash *reservation* that silently becomes zero is the same
   silent-zero class this codebase is otherwise built against. Pinned by a test
   documenting current behaviour so a fix is a visible change. **Recommended as
   the next fix; deliberately not patched inside this milestone.**

## Limitations

- `STRATEGY_OBSERVATION_DURATION_INSUFFICIENT` — bounded deterministic replay
  certifies the machinery. It says nothing about profitability, and no test claims
  otherwise.
- `LIVE_PUBLIC_TRANSPORT_UNCERTIFIED` — only REPLAY was exercised. The mode exists
  and is labelled; live public transport is a separate certification.
- NEPSE shadow remains `BLOCKED_EXTERNAL_LICENSE`, unchanged and not faked.
