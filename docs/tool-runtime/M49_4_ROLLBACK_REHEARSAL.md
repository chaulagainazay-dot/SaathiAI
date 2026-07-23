# M49.4 Rollback Rehearsal

## Strategy

Deterministic Git rollback of the stacked PR chain.

## Rollback points

| Level | Action |
|---|---|
| Unmerge M49.4 only | reset/revert to `0eb1592` (M49.3 tip) |
| Unmerge M49.3 | tip `d8492a8` (M49.2) |
| Unmerge M49.2 | tip `f41e756` (M49.1) |
| Unmerge M49.1 | tip `27b3bcf` (M48) |
| Unmerge M48 | tip `67efcb3` (master) |

## Database rollback

Durable idempotency DB path: `data/tool_runtime/idempotency.db`

- Single-host SQLite; not shared multi-host
- Safe to delete/rename DB on rollback of M49.2+ if no production dependency (none authorized)
- Artifact dir `data/tool_runtime/artifacts` is local-only

## Rehearsal performed

```text
# dry check: parent of M49.4 start is M49.3
git rev-parse milestone/m49-3-gateway-completion
# = 0eb1592caa207ca61b250ec50a8fc9c6a3d1ba3c
# ancestry is-ancestor checks PASS (see chain reconstruction)
```

No force-push, no branch deletion, no production DB touch.

## State

`M49_ROLLBACK_REHEARSED`
