# ReconciliationAuthority

## What it is

A deterministic function from three snapshots to one readiness verdict.

```
evaluate(oms, external, ledger, expected_cash, expected_positions,
         order_original_quantities=None, correlation_id="") -> ReconciliationVerdict
```

## What it is not

It **never authorises a trade**. It has no `approve`, `authorize`, `submit`,
`execute`, `place_order`, `cancel`, `send`, `trade`, `override`, or `force`
method — asserted by `test_reconciliation_authority_exposes_no_execution_verbs`,
which introspects the class rather than trusting the docstring. It also cannot
reach ledger mutation: `test_reconciliation_authority_cannot_mutate_a_ledger`
asserts the module never references `record_fill`, `post_accepted_fill`,
`PortfolioLedgerService`, or `record_deposit`.

Its only outputs are a readiness value, a boolean `permits_new_execution`, and a
list of findings explaining itself.

## Relationship to the pre-existing `ReconciliationEngine`

`paper_trading/reconciliation.py` (720 lines) already produces rich drift
reports, severities, and repair plans. It **reports**; it does not gate.

`ReconciliationAuthority` is the gate. It is deliberately small and separate so
that the thing deciding "may execution proceed" is auditable in one screen and
has no repair, mutation, or workflow capability. The two compose: the engine
explains drift in detail, the authority answers one yes/no.

## Snapshot contracts

| Type | Fields |
|---|---|
| `OmsSnapshot` | `orders`, `fills`, `as_of` |
| `ExternalOrderSnapshot` | `orders`, `fills`, `as_of`, `available` |
| `LedgerSnapshot` | `cash`, `positions`, `as_of` |

In PAPER mode the external snapshot is the simulated venue. A future broker
snapshot implements the **same shape**, so the authority does not change when a
real venue appears. That is the whole point of the interface.

## Evaluation order

Deliberately ordered so that "we cannot see" outranks "we disagree", and
"ambiguous" outranks both.

1. **`external.available == False`** → `DATA_INSUFFICIENT`
2. **`expected_cash` or `expected_positions` is `None`** → `DATA_INSUFFICIENT`
3. **any order in `UNKNOWN` / `RECONCILIATION_REQUIRED`** → `UNKNOWN`
4. Order-set differences, filled-quantity disagreement, **overfill**, fill-set
   differences, ledger cash drift, position drift → `MISMATCH`
5. All consistent but orders still in flight → `TEMPORARILY_PENDING`
6. Otherwise → `RECONCILED`

## Execution permission

| Readiness | Permits new execution |
|---|---|
| `RECONCILED` | yes |
| `TEMPORARILY_PENDING` | **no by default**; `allow_execution_while_pending=True` opts in |
| `MISMATCH` | never |
| `UNKNOWN` | never |
| `DATA_INSUFFICIENT` | never |

`test_no_readiness_other_than_reconciled_permits_execution` iterates the whole
enum, so adding a new readiness value without deciding its permission fails the
suite rather than defaulting to permissive.

`TEMPORARILY_PENDING` is the only configurable case, and it fails closed unless
explicitly opened.

## Verdict

`ReconciliationVerdict` is a frozen dataclass — `test_verdict_is_immutable`
asserts a verdict cannot be edited after the fact. It carries `readiness`,
`permits_new_execution`, `findings`, `evaluated_at`, `correlation_id`, and
serialises via `to_dict()` for evidence.

A `MISMATCH` verdict always carries at least one finding
(`test_verdict_carries_evidence`) — a block that cannot explain itself is a bug.

## Determinism

The clock is injectable and is used only for the evidence stamp. With a fixed
clock, identical input yields a byte-identical `to_dict()`
(`test_authority_verdict_is_deterministic_for_identical_input`). The module
contains no `random`, `uuid4`, or `secrets` usage, asserted by test.
