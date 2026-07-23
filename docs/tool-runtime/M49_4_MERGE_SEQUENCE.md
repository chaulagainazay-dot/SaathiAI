# M49.4 Merge Sequence Recommendation

## Exact merge order (when owner authorizes)

1. PR #3 — M48 agent runtime baseline → `master`
2. PR #4 — M49.1 tool framework → post-#3 master (or retarget base)
3. PR #5 — M49.2 convergence → post-#4
4. PR #6 — M49.3 gateway completion → post-#5
5. M49.4 draft PR → post-#6 base `milestone/m49-3-gateway-completion` (or updated master)

## Pre-merge checks

- CI critical-regressions + full-suite green on each PR
- Ancestry still linear
- No secret material in diffs
- Trading Guardian still advisory-only
- Freeform shell still blocked

## Post-merge checks

- Import server / route smoke
- M49.4 closure audit PASS
- Idempotency DB path writable locally
- No live connector credentials required

## Rollback point

Immediate parent merge commit of the failed PR.

## Production boundary

```text
PRODUCTION_NOT_AUTHORIZED
LIVE_CONNECTORS_NOT_READY
PUBLIC_LAUNCH_NOT_READY
```

## Merge readiness

`MERGE_READY_WITH_LIMITATIONS` — stack is CI-green and linear, but residual LEGACY_BOUNDED
and draft PR status mean owner review still required before any merge.

M49.4 does **not** merge any PR.
