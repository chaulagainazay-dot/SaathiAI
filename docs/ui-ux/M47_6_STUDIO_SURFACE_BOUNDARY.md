# M47.6 — Studio Surface Boundary

| Surface | Responsibility | Unique workflows | Nav |
|---|---|---|---|
| `/studio` | Autonomous content **production queue** (plan, script, produce, lanes) | Queue counts, produce/script actions | Primary “Studio” |
| `/studio-os` | **StudioWorkspace** creative OS shell | Workspace-centric creative flow | Alias of Studio area; **distinct page** |
| `/studio/control-room` | Operational **control room** for studio runs | Control-room ops UI | Sub-route; alias for active nav |

## Outcome

```text
KEEP_BOTH_DISTINCT
```

| Decision | |
|---|---|
| Redirect `/studio-os` | **No** — StudioWorkspace ≠ AIStudio queue |
| Redirect control-room | **No** — sub-route preserved |
| Navigation | Single “Studio” primary label; description clarifies OS + control-room |

## Deep links

Preserve all three paths. No soft redirect.
