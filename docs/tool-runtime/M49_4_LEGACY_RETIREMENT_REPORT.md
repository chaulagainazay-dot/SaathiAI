# M49.4 Legacy Retirement Report

## Target

`LEGACY_RUNTIME_ELIMINATED` — **not achieved**.

## Achieved

`LEGACY_RUNTIME_BOUNDED` with zero UNKNOWN residual classifications.

## Actions taken in M49.4

| Action | Detail |
|---|---|
| Hardened `project_run` | Always returns freeform_shell_blocked before project resolution |
| Closure census | All 120 handlers classified with explicit policy sets |
| Negative reachability tests | Deferred/prohibited proven blocked |
| Compatibility bridge audit | 11 allowlisted names; unknown → None |

## Handlers retired (executable removal)

None bulk-deleted. Freeform shell handlers remain source-visible but **non-executable**.

## Handlers converted to canonical wrappers

No new migrations in M49.4 (already 11 from M49.2/M49.3).

## Handlers hard-disabled

47 DEFERRED_DISABLED + 3 PROHIBITED freeform + financial PROHIBITED set (7 names, may be unregistered).

## Handlers retained (59 LEGACY_BOUNDED)

Retained because:

1. No canonical m49 adapter equivalent exists yet
2. Agent still depends on `execute_tool` for content/research/local tools
3. Deleting without migration would break AgentExecutor
4. Governance still gates them; freeform/deferred already blocked

### Retention reason (summary)

Local/content/research tools with governance gate; planned removal when each has a
manifest + adapter and AgentExecutor routes via gateway only.

### Future removal milestone

**M50+** incremental migration waves — not part of M49.4 closure.

## Why not LEGACY_RUNTIME_ELIMINATED

Executable residual handlers remain (59). Claiming elimination would be false.
