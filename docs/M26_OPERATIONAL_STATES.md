# M26 Operational States

## Service phase

```text
STOPPED → STARTING → RUNNING ⇄ DRAINING → STOPPING → STOPPED
                ↘ RECOVERING ↗
```

## Health

| Status | Meaning |
|--------|---------|
| HEALTHY | Ops process functioning (may still be not ready for inference) |
| UNHEALTHY | State/ownership broken |
| STOPPED | Ops not running |

## Readiness

| Status | Meaning |
|--------|---------|
| READY | Safe to accept new governed request |
| DEGRADED | Partial (e.g. circuit/cooldown) |
| ENVIRONMENT_BLOCKED | Memory, disk, provider, model |
| POLICY_BLOCKED | Mode OFF/SHADOW or not certified |
| DRAINING | No new work; finishing inflight |
| UNHEALTHY | Ops unhealthy |

Every non-ready result includes `check_id:reason` blockers.

## Provider ops state (session)

```text
UNKNOWN | STARTING | READY | DEGRADED | UNAVAILABLE | COOLDOWN | DRAINING | STOPPED
```

## Rollout mode

| Mode | Accepts production work? |
|------|---------------------------|
| OFF | No |
| SHADOW | No (validation paths only) |
| CANARY | Deterministic fraction / allowlist |
| ACTIVE | Yes if certified + resources OK |
| DRAINING | No new work |

Transitions fail closed. Default after uncertain state: **OFF**.
