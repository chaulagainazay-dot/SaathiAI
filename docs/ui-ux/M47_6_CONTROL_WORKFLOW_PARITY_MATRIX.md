# M47.6 — Control Workflow Parity Matrix

| Workflow | Entry | Data | Action | Authority | Canonical | Status |
|---|---|---|---|---|---|---|
| Platform overview cells | `/control` | control/overview | read | none | `/command` (partial keys) | **SPLIT_ACROSS_CANONICAL_ROUTES** |
| Requires attention list | `/control` | requires_attention | navigate | none | Home + `/command` | **CANONICAL_PARITY** (shared source) |
| Global search | `/control` | control/search | read | none | none full | **KEEP_LEGACY_COMPATIBILITY** |
| Pending approvals count | `/control` | pending_approvals cell | navigate | none | `/approvals` | **CANONICAL_PARITY** |
| Security verdict | `/control` | security cell | read | none | `/security` | **SPLIT_ACROSS_CANONICAL_ROUTES** |
| Release gate | `/control` | release_readiness | read | none | `/command` partial | **KEEP_LEGACY_COMPATIBILITY** |
| Timeline | `/control` | recent_timeline | read | none | partial on command | **KEEP_LEGACY_COMPATIBILITY** |
| Computer agent | `/control/computer` | control/computer | read/ops | subsystem | keep path | **KEEP_LEGACY_COMPATIBILITY** |
| Infra health | linked | infrastructure | read | none | `/monitoring` | **CANONICAL_PARITY** |

## Redirect `/control`

```text
KEEP_COMPATIBILITY
```

Search, release gate, and full cell grid remain unique to Control. Command links to Control for deep ops.
