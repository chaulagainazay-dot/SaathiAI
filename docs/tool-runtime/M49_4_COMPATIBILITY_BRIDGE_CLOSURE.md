# M49.4 Compatibility Bridge Closure

## Bridge under review

- `saathi.tool_runtime.compat.try_canonical_legacy_tool`
- `saathi.tools.registry.execute_tool` disposition gate
- `LEGACY_NAME_MAP` (11 names)

## Decision

| Bridge | Decision |
|---|---|
| `try_canonical_legacy_tool` | **RETAIN_TEMPORARILY** |
| `execute_tool` legacy dispatcher | **RETAIN_TEMPORARILY** (AgentExecutor dependency) |
| Unmapped legacy fallback | **REMOVE** (already absent — returns unknown/block) |

## Restrictions (enforced)

- specific allowlisted names only (`LEGACY_NAME_MAP`)
- no unknown fallback (None → caller blocks)
- no authority inference from caller args
- no direct adapter call from bridge
- no credential pass-through
- no generic connector execution
- all mapped execution via `ExecutionGateway.execute_registered_tool`
- `manage_tasks` / `my_files` list-only
- `send_email` requires explicit approval reference

## Caller inventory

| Caller | Uses bridge |
|---|---|
| `execute_tool` after governance | yes for mapped |
| Direct `try_canonical_legacy_tool` | tests + execute_tool |

## Removal criterion

Remove when AgentExecutor (and any remaining callers) invoke only
`ExecutionGateway.execute_registered_tool` for those capabilities.

## Removal milestone

M50 tool surface cleanup (not authorized in M49.4).

## Negative tests

- `tests/test_m49_4_closure_audits.py::test_compatibility_bridge_allowlist_only`
- `tests/test_m49_4_legacy_retirement.py::test_unknown_name_rejected_no_generic_fallback`
