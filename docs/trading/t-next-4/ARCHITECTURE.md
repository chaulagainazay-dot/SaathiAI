# T-NEXT-4 — Execution Integrity Architecture

## What was already there, and what this mission added

The honest framing matters for certification. The paper trading chain was
already substantially built by T-NEXT-1 through T-NEXT-3. This mission audited
it, found two real defects, fixed them, and added the missing ambiguity-handling
layer.

### Pre-existing (verified by reading source, not documentation)

| Component | Location | State |
|---|---|---|
| Canonical Fund Ledger | `saathi/platform/fund_ledger/` — `service.py` (`PortfolioLedgerService`, event-sourced with `replay`/`snapshot`), `store.py`, `reducer.py`, `money.py` | Complete |
| Fill → ledger posting | `fund_ledger/posting.py` — `post_accepted_fill`, `FillPostingStore`, `retry_pending_posts` | Complete, already idempotent |
| Durable Paper OMS | `saathi/platform/paper_trading/` — `store.py` (`PaperStore`, `IdempotencyConflict`), `models.py` (`PaperOrder`, `PaperFill`, `BrokerOrderState`, `BROKER_TRANSITIONS`), `service.py` (1046 lines) | Complete |
| Paper execution adapter | `paper_trading/broker.py` (`PaperBroker`, deterministic fee/slippage models) | Complete |
| Execution boundary | `paper_trading/orchestration.py` → `saathi/execution/gateway.py` → `UniversalBoundary` → registered tool | Complete |
| Trading Guardian | `saathi/platform/trading_guardian.py`, `saathi/platform/tg/` | Complete |
| PortfolioRiskEngine | `saathi/portfolio.py`, `tg/portfolio_risk/` | Complete |
| PortfolioConstructionEngine | `saathi/platform/portfolio_construction/` | Complete |
| Reconciliation reporting | `paper_trading/reconciliation.py` (`ReconciliationEngine`, drift findings, repair plans) | Complete — but **reports**, does not gate |
| Kill switch | `tg/kill_switch.py`, account halt | Complete |

### Added by this mission

`saathi/platform/paper_trading/execution_integrity.py` — the ambiguity layer:

1. **`SubmissionOutcome` / `RetryDisposition` / `classify_submission`** — the
   rule that an ambiguous submission is never automatically retried.
2. **`SubmissionAttemptStore`** — durable, append-only, per-idempotency-key
   record of every attempt, and the fail-closed `may_submit` gate.
3. **`ReconciliationAuthority`** — a deterministic readiness verdict over OMS /
   external / ledger state that *denies* readiness but never authorises anything.

### Defects found and fixed

| ID | Defect | Fix |
|---|---|---|
| D1 | An order could be admitted against a **non-positive reference price**. `validate_new_order` checked quantity and limit price but not `ref_price`. The fill path refused a zero touch price, so no fill occurred — but the order was created and cash was reserved against a meaningless price. | `broker.py::validate_new_order` now rejects `ref_price <= 0`. |
| D2 | A **supplied-but-invalid `approval_id` was silently ignored** when the order did not independently require approval. Fail-open on a credential the caller believed was being checked. | `service.py::submit_order` now verifies any supplied approval reference, whether or not approval was required. |

Both were found by failure-injection tests written before the fix (F12b, F13).

## Chain as certified

```
PortfolioConstructionEngine        proposal only, no execution verb
        ↓
PortfolioRiskEngine                deterministic; block always blocks
        ↓
Trading Guardian                   deterministic veto, evaluated server-side
        ↓
Approval                           explicit, server-owned, consumed atomically
        ↓
ExecutionGateway                   sole external boundary (UniversalBoundary)
        ↓
Durable Paper OMS                  SQLite, immutable order identity, idempotent
        ↓
Fill Processing                    event-hash dedup, partial fills, no overfill
        ↓
Canonical Fund Ledger              event-sourced, idempotent posting
        ↓
ReconciliationAuthority            certifies consistency; denies readiness
        ↺
PortfolioRiskEngine
```

## Authority boundary

`execution_integrity.py` holds **no** execution, approval, risk-override, veto,
broker, or ledger-mutation authority. This is enforced by test, not by comment:
`test_security_authority.py` asserts the module exposes no execution verb,
imports no ledger-mutation symbol, imports no LLM surface, opens no network, and
contains no randomness.

## Determinism

No decision path in the added module reads a clock or a random source. Clocks are
injectable (`clock=` on both `SubmissionAttemptStore` and
`ReconciliationAuthority`) and are used only to stamp evidence.
`test_authority_verdict_is_deterministic_for_identical_input` pins this.

## Resource posture

SQLite and stdlib only. No Redis, Kafka, Celery, RabbitMQ, Docker, LangGraph,
Backtrader, or TradingAgents. Zero new dependencies. The added module is 1 file.
