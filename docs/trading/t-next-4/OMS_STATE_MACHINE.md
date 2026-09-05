# OMS State Machine

## Separation of concerns (Phase 2)

SaathiOS deliberately does **not** put every state in one enum. States live on
the layer that owns them:

| Layer | States | Owner |
|---|---|---|
| Intent / proposal | `PROPOSED`, `RISK_CHECKED`, `APPROVAL_REQUIRED`, `APPROVED`, `REJECTED` | `OrderState` on the intent record (`paper_trading/service.py`, `store.create_intent/update_intent`) |
| Broker / execution | `PENDING_VALIDATION`, `ACCEPTED`, `OPEN`, `PARTIALLY_FILLED`, `FILLED`, `CANCEL_PENDING`, `CANCELLED`, `REJECTED`, `EXPIRED`, `FAILED` | `BrokerOrderState` (`paper_trading/models.py`) |
| Submission attempt | `ACKNOWLEDGED`, `REJECTED`, `TIMEOUT_BEFORE_SEND`, `TIMEOUT_AFTER_SEND`, `CONNECTION_LOST`, `UNKNOWN` | `SubmissionOutcome` (`execution_integrity.py`) — **added by this mission** |
| Readiness | `RECONCILED`, `TEMPORARILY_PENDING`, `MISMATCH`, `UNKNOWN`, `DATA_INSUFFICIENT` | `ExecutionReadiness` (`execution_integrity.py`) — **added by this mission** |
| Account | `ACTIVE`, `HALTED`, … | `AccountStatus` |

This is the right factoring: an order's *broker* state and the *ambiguity of one
submission attempt* are different facts. Collapsing them into one enum is how
`UNKNOWN` ends up meaning three different things.

`UNKNOWN` and `RECONCILIATION_REQUIRED` are first-class in the layers that can
actually observe them — the submission attempt and the readiness verdict — and
they always deny action.

## Broker transitions (pre-existing, verified)

```
PENDING_VALIDATION → ACCEPTED | REJECTED | FAILED
ACCEPTED           → OPEN | PARTIALLY_FILLED | FILLED | CANCEL_PENDING | REJECTED | EXPIRED | FAILED
OPEN               → PARTIALLY_FILLED | FILLED | CANCEL_PENDING | CANCELLED | EXPIRED | FAILED
PARTIALLY_FILLED   → PARTIALLY_FILLED | FILLED | CANCEL_PENDING | CANCELLED | EXPIRED | FAILED
CANCEL_PENDING     → CANCELLED | FILLED | PARTIALLY_FILLED | FAILED
FILLED / CANCELLED / REJECTED / EXPIRED / FAILED → ∅   (terminal sinks)
```

`can_broker_transition(cur, tgt)` is the single gate. Anything not in the table
is refused — the model fails closed by construction, since an unlisted target is
simply absent from the frozenset.

### Forbidden transitions asserted by test (`F9`)

| From | To | Why forbidden |
|---|---|---|
| `FILLED` | `ACCEPTED` / `OPEN` | a filled order cannot re-open |
| `CANCELLED` | `ACCEPTED` / `PARTIALLY_FILLED` | a cancelled order cannot resurrect |
| `REJECTED` | `FILLED` | a rejected order cannot fill |
| `EXPIRED` | `FILLED` | an expired order cannot fill |

`CANCEL_PENDING → FILLED` is deliberately **allowed**: a cancel racing a fill is
a real venue behaviour, and modelling it as illegal would force the system to
lie about what happened. The fill wins; the cancel becomes a no-op.

## Transition evidence

Every broker transition is written through `PaperStore._write_transition`, which
records `org_id`, `order_id`, `from`, `to`, `reason`, and `correlation_id`, and
is readable via `store.list_transitions(org_id, order_id)`. Order identity is
immutable (`PaperOrder.id`), and `order_state_hash()` gives a deterministic
digest of `(id, state, filled, remaining, version)` for evidence.

`PaperOrder.version` provides optimistic concurrency; account updates take
`expected_version` explicitly.
