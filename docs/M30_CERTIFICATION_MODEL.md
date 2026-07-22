# M30 — Certification State Model

## States

| State | Meaning |
|-------|---------|
| UNASSESSED | No valid current assessment |
| ASSESSING | Bounded assessment in progress (lease) |
| CERTIFIED | All mandatory checks passed |
| CERTIFIED_WITH_LIMITATIONS | Safety-critical passed; explicit non-critical limitations remain |
| FAILED | One or more mandatory repository-controlled checks failed |
| ENVIRONMENT_BLOCKED | Required env capability unavailable and not simulatable |
| STALE | Relevant inputs changed after certification |
| REVOKED | Explicitly invalidated for safety/policy/bypass reasons |

## Transitions

```text
UNASSESSED → ASSESSING (begin_assessment / lease)
ASSESSING → CERTIFIED | CERTIFIED_WITH_LIMITATIONS | FAILED | ENVIRONMENT_BLOCKED
CERTIFIED | CERTIFIED_WITH_LIMITATIONS → STALE (fingerprint drift)
CERTIFIED | CERTIFIED_WITH_LIMITATIONS | STALE | FAILED → REVOKED (revoke)
Interrupted ASSESSING (expired lease) → recoverable re-begin
```

## Semantics

* **No hard-coded certification** — always computed from checks + fingerprint.
* **CERTIFIED_WITH_LIMITATIONS** does not expand rollout beyond manifest/policy.
* **FAILED / STALE / REVOKED / ENVIRONMENT_BLOCKED / UNASSESSED** block ACTIVE.
* **Revocation** preserves prior evidence; appends revocation record.

## Distinct from platform production certification

```text
production certification (M25)  = platform/package safety
connector certification (M30)   = per-connector behavioral conformance
```

Both may be required for ACTIVE execution.
