# ExecutionGateway Contract

## The path

```
caller (API / agent runtime / UI)
  → paper_trading/orchestration.py   submit_via_gateway / cancel_via_gateway / process_event_via_gateway
    → saathi/execution/gateway.py    ExecutionGateway.execute_registered_tool
      → saathi/execution/universal.py UniversalBoundary._submit_locked
        → registered tool            paper.order.submit / .cancel / .process_event
          → paper_trading/execution_tool.py  submit_adapter
            → PaperTradingService
              → PaperBroker
```

The gateway was **not replaced**. It was audited and found adequate; the mission
brief said not to replace it unless objectively necessary, and it was not.

## Pre-submission verification (where each check actually lives)

| Required check | Where enforced | Verified by |
|---|---|---|
| Proposal (intent) exists | `service.submit_order` → `store.get_intent`, raises if absent | `F14` |
| Account exists and is `ACTIVE` | `_account_or_404`, `broker.validate_new_order` | pre-existing suite |
| Environment is PAPER | `validate_new_order` (`environment not PAPER`) | `test_paper_safety_rejects_live_configuration` |
| Trading Guardian allows | `_guardian_review` server-side, **before** the order write | pre-existing `test_guardian_veto_*` |
| Risk / reservation sufficient | `validate_new_order` cash and long-only checks | pre-existing |
| Approval valid, not revoked | `_verify_approval` + atomic `consume_cb` | `F13` — **fixed in this mission** |
| Idempotency | gateway digest + intent→order identity + attempt store | `F1`, `F1b` |
| Market data fresh | `validate_new_order` / fill path reject non-`VALID` quality | `F12` |
| Price sanity | `ref_price > 0` — **added in this mission** | `F12b` |
| Quantity valid | `qty > 0`; limit orders need positive limit price | pre-existing |
| Kill switch / halt not active | `halt_account` → `status != ACTIVE` refuses submission | `F17` |
| Reconciliation state acceptable | `ReconciliationAuthority.permits_new_execution` | `F11`, `F18`, `F19`, `F20` |

## Changes made by this mission

Exactly two, both in the pre-submission path, both minimal:

**1. `broker.py::validate_new_order`** — reject a non-positive reference price.

```python
if ref_price is None or D(ref_price) <= 0:
    return ValidationResult(False, "reference price must be positive")
```

Previously an order could be created and cash reserved against a zero price. The
fill path already refused a zero touch price, so no fill could occur, but the
order and its reservation were real.

**2. `service.py::submit_order`** — always verify a supplied approval reference.

```python
elif approval_id:
    self._verify_approval(ctx, approval_id, account_id=acct.id, est_notional=est_notional)
    consume_cb = self._make_consume_cb(ctx, approval_id)
```

Previously, if an order did not independently require approval, a supplied
`approval_id` was ignored entirely — including an unknown, expired, or revoked
one. A caller passing a bogus approval got a successful submission and no error.
That is fail-open on a credential the caller believed was being checked.

Neither change altered any existing test expectation: the full trading
regression (258 tests) passes unchanged after both.

## Bypass prohibition

No strategy, LLM, UI, analyst, agent, or portfolio component may reach
`PaperTradingService` except through the gateway. Enforced structurally by the
tool-runtime registration (`execution_tool.register_paper_tools`) and asserted by
the pre-existing gateway-boundary tests plus this mission's
`test_no_llm_inference_import_in_paper_trading_execution_path`, which fails if
any LLM surface becomes importable from the paper trading execution path.
