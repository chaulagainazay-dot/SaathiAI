# M49.3 Compatibility Retirement

| bridge | decision | notes |
|---|---|---|
| try_canonical_legacy_tool | RETAIN_CANONICAL_WRAPPER | specific LEGACY_NAME_MAP only; no generic fallback |
| freeform run_shell | BLOCK | PROHIBITED |
| freeform project_run | BLOCK | PROHIBITED |
| applescript | BLOCK | PROHIBITED |
| deferred browser/mac/deploy | DEFER_WITH_EXPIRY | not runtime executable |
| LEGACY_BOUNDED handlers | RETAIN with deprecation | temporary; prefer gateway |

Unknown tool → reject. No unknown→legacy registry fallback for execution.
