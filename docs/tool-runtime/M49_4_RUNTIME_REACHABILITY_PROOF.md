# M49.4 Runtime Reachability Proof

## Method

Reachability is proven from the live `execute_tool` / gateway paths, not from absence of source symbols.

## Entry surfaces inspected

| Surface | Execution entry | Finding |
|---|---|---|
| AgentExecutor (`saathi.agent`) | `execute_tool` | Legacy path; disposition enforced |
| agent_runtime.gateway_exec | `execute_registered_tool` | Canonical m49 tools |
| ExecutionGateway | `execute_registered_tool` → ToolExecutionService | Mandatory for registered tools |
| Compatibility bridge | allowlisted names only → gateway | No unknown fallback |
| CLI audit tools | read-only discovery | No execute |
| Scheduler | no legacy tool dispatch found for freeform | N/A |
| Dynamic import / getattr dispatch | no user-controlled registration into ToolRegistry | allow_dynamic=False |
| Plugin discovery | registry seal + trusted bootstrap only | User cannot register |

## Deferred / prohibited proofs

| Proof | Evidence |
|---|---|
| Not registered as ENABLED m49 tool | ToolRegistry has no ab_* / run_shell manifests |
| Not in LEGACY_NAME_MAP | only 11 names mapped |
| Not callable via freeform shell | FREEFORM_SHELL_BLOCKED |
| Not callable via generic connector | generic connector ABSENT |
| execute_tool negative tests | `tests/test_m49_4_legacy_retirement.py`, `audit_reachability_negative` |
| Unknown names | rejected; disposition DEPRECATED_AND_BLOCKED |

## Dynamic dispatch review

```text
rg getattr|import_module|__import__|handler_map|execute_tool saathi (non-test)
```

- `_HANDLERS` is a static dict in `saathi.tools.registry`
- ToolRegistry registration requires trusted bootstrap; dynamic plugins disabled by default
- No generic fallback for unmapped legacy names at compat layer

## Verdict

Deferred and prohibited tools are **runtime unreachable** through supported callers.
LEGACY_BOUNDED tools remain reachable by design until migrated.
