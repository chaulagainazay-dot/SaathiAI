# T-NEXT-4 — Final Certification

## Verdict

**`T_NEXT_4_EXECUTION_INTEGRITY_CERTIFIED_WITH_LIMITATIONS`**

Scope: the **PAPER** execution integrity chain. Not shadow. Not live.

## Certification bar, item by item

| Requirement | Status | Evidence |
|---|---|---|
| Durable OMS | **MET** (pre-existing, verified) | `PaperStore` SQLite; order/intent/fill/transition/ledger tables; `F4` restart test |
| Idempotent submission | **MET** | three layers: gateway digest, intent→order identity, attempt store. `F1`, `F1b`, `F4`, `F5` |
| Deterministic fills | **MET** | event-hash dedup, versioned fee/slippage models, no overfill. `F6`, `F7`, `F20`, `F20b` |
| Ledger idempotency | **MET** (pre-existing, verified) | `post_accepted_fill` short-circuit on `fill_id`; event-sourced ledger. `F6`, `F10` |
| Reconciliation authority | **MET as a component**; **NOT wired into the submission path** | `ReconciliationAuthority`, 21 tests. See Limitations |
| Startup recovery | **MET** | `F4`; durable attempt store; `STARTUP_RECOVERY.md` |
| Failure-injection coverage | **MET for 18 of 21**; 3 unreachable by construction | `FAILURE_MATRIX.md` |
| ExecutionGateway-only path | **MET** (pre-existing, verified) | `orchestration.py` → gateway → registered tool; boundary tests |
| Trading Guardian preserved | **MET** | unchanged; server-side veto before order write; regression green |
| Approval preserved | **MET, and strengthened** | defect D2 fixed: a supplied approval is now always verified |
| Risk preserved | **MET** | `PortfolioRiskEngine` and `portfolio_risk/` unchanged; regression green |
| Zero live broker authority | **MET** | no broker SDK, no network in the integrity module, paper-safety asserts |
| Zero LLM execution authority | **MET** | no LLM import reachable from the execution path, asserted by test |

## Why "WITH LIMITATIONS" and not unqualified

Four honest reasons:

1. **`ReconciliationAuthority` and `SubmissionAttemptStore` are correct but not
   yet enforced.** They are tested libraries, not yet called by `submit_order`.
   Wiring them is a deliberate separate change requiring a decision about the
   external snapshot source and the operator experience on denial.
2. **F15 and F16 are unreachable by construction**, not tested. They become
   reachable the moment guardian evaluation leaves the write transaction.
3. **Replace semantics are not implemented** in the paper contract, so Phase 10's
   replace requirements are uncertified.
4. **The full repository suite did not complete.** A bounded run reached 84% of
   collected tests with zero failure or error markers before hitting its
   deadline; the remaining 16% is unverified. Targeted suites are real and
   green. No full-suite pass is claimed.

## What this mission actually changed

Two production files, two defects, both fail-open, both found by tests written
before the fix:

- `broker.py::validate_new_order` — reject non-positive reference price (D1)
- `service.py::submit_order` — always verify a supplied approval reference (D2)

Plus one new module (`execution_integrity.py`), four test modules (82 tests),
and this evidence set. Three further defects in the new module were found by
independent fresh-context review and fixed with regression tests.

## Explicit statements

```
NO_LIVE_TRADING
NO_REAL_BROKER
NO_WITHDRAWAL
NO_LEVERAGE
NO_LLM_EXECUTION_AUTHORITY
NO_TRADINGAGENTS_RUNTIME_DEPENDENCY
```

Each is asserted by at least one test in `test_security_authority.py`, not
merely declared here.

## Readiness for shadow execution

**Not yet.** Prerequisites, in order:

1. Wire `ReconciliationAuthority.permits_new_execution` into `submit_order` as a
   mandatory pre-submission gate.
2. Wire `SubmissionAttemptStore.may_submit` into the submission path.
3. Add a startup sweep that surfaces unresolved ambiguous attempts.
4. Implement and certify replace semantics, or explicitly declare replace
   unsupported at the adapter contract level.
5. Make F15/F16 reachable and tested, since a real venue introduces the
   concurrency that currently makes them impossible.
6. Add sequence-number-based fill ordering for a venue that provides one.
7. Certify the kill-switch scope distinction (`BLOCK_NEW_ORDERS` vs
   `BLOCK_ALL_EXECUTION_ACTIONS`).

## Can TA-1 begin afterwards?

**Yes.** TA-1 (evidence and safety contract from the TradingAgents evaluation)
touches `market_data`, `provider_descriptor`, and `research_orchestrator/sessions`.
It involves no LLM and no financial authority, and it does not intersect the
execution plane certified here. The boundary-invariance test TA-1 introduces is
complementary to this mission's authority tests.

The one ordering constraint: TA-1 must not begin before the shadow-execution
prerequisites above are at least scheduled, because a research layer proposing
into a chain whose reconciliation gate is not yet enforced would be premature.
