# M44 — Rollback Guide

M44 executes no rollout, so it has nothing to *operationally* roll back. This guide
covers two things: (1) the deterministic **rollback contracts** the framework
defines for a future execution layer to honor, and (2) how to **reverse the M44
change itself** if required.

## 1. Rollback contracts (defined, not executed)

Every rollout request names a `rollback_owner` and an `incident_owner`
(both mandatory). The framework defines deterministic triggers; a future execution
layer must treat any fired trigger as an automatic, immediate rollback.

| Trigger (`RollbackTrigger`) | Fires when |
|-----------------------------|-----------|
| `identity_mismatch` | live subject fingerprint ≠ expected |
| `provider_changed` | provider identity drifts from `github_meta` |
| `unexpected_response` | a response outside the read-only contract |
| `error_budget_exceeded` | any error (zero-tolerance for read-only canary) |
| `policy_violation` | percentage/scope exceeds the authorized policy |
| `kill_switch` | `SAATHI_M39_KILL_SWITCH` or snapshot flag set |
| `security_alert` | an open security alert |
| `manual_operator_stop` | operator halts manually |

Evaluate deterministically:

```python
from saathi.credentials import m44
m44.evaluate_rollback({"error_budget_exceeded": True})
# {'rollback_required': True, 'triggers_fired': ['error_budget_exceeded'],
#  'deterministic': True, 'rollback_kind': 'automatic'}
```

Any fired trigger ⇒ `rollback_required: True`. No trigger ⇒ `rollback_kind: none`.
The function is pure and order-independent, so the same signals always yield the
same decision.

## 2. Recording a rollback / expiry in the ledger

The ledger records lifecycle events (framework-level, not execution). To mark a
request rolled back, aborted, or expired:

```
python -m saathi.credentials.cli m44-expire-rollout R-2026-0001 --reason kill_switch
python -m saathi.credentials.cli m44-verify-ledger   # confirm chain intact
```

`append_ledger(LedgerEvent.ROLLBACK, {...})` and `LedgerEvent.ABORTED` are available
programmatically. Entries are immutable and hash-chained; `verify_ledger_chain`
detects any tampering.

## 3. Reversing the M44 change itself

M44 adds only new, additive artifacts and one additive CLI dispatch block. To fully
revert:

```
git rm saathi/credentials/m44.py tests/test_m44_rollout_authorization.py
git rm -r docs/evidence/m44 docs/M44_*.md
# revert the additive m44 block + parsers in saathi/credentials/cli.py
git checkout -- saathi/credentials/cli.py   # if no other cli.py edits are pending
```

Because M44 is composition-only and touches no M31–M43 source, removing it restores
the exact prior behavior. No credential, provider permission, or evidence from
earlier milestones is modified by M44, so no data migration or cleanup is needed.

## 4. What rollback never has to undo

M44 never activated production, enabled writes, expanded scope, engaged the Trading
Guardian, changed provider permissions, or granted any authority. There is no live
state, lease, or credential created by M44 to revoke.
