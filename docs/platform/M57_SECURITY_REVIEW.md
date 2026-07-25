# M57 Security Review

Scope: the localhost launcher, single-host heartbeat, cold-load UI, local
readiness, and the prepared macOS shortcut / LaunchAgent. No change to identity,
RBAC, approval, gateway, binding enforcement, or the execution path.

## Verified controls

| Control | Enforcement | Evidence |
|---|---|---|
| Localhost-only binding | backend 127.0.0.1:8765; never `--host 0.0.0.0`; no tunnels | `test_launcher_localhost_only_and_failclosed_guards`; browser cert `launcher_contract` |
| Safe PID ownership | recognize by signature; **stop** only PID-file-owned | launcher `_owned`/`_is_saathi`; `test_launcher_status_and_stop_are_safe_noops` |
| Unrelated processes untouched | fail-closed on unrelated listeners; never blanket-kill by port | launcher start/doctor; `refusing to kill` |
| Stale PID safety | non-matching PID treated as not owned | `test_launcher_stale_pid_is_not_treated_as_owned` |
| No agent clobber | launcher LaunchAgent label `com.saathi.local-launcher` (distinct) | `test_launcher_...guards`; existing `com.saathi.local` left as-is |
| Heartbeat grants no authority | liveness only; no lease/runtime/execution authority | `test_heartbeat_grants_no_authority` |
| No secrets in logs/readiness | logs and readiness JSON contain no tokens/paths | `test_launcher_logs_have_no_secrets`; `test_local_readiness_report_is_safe_and_advisory` |
| CORS/auth preserved | doctor CORS preflight; console auth unchanged | doctor; live verification |
| No production/connector/financial/trading/multi-host | all reported DISABLED; no enabling control | status/doctor; browser cert `no_unsafe_actions` |

## Residual risk
- A pre-existing `com.saathi.local` LaunchAgent may run a backend on `*:8765`
  (all interfaces). M57 never modifies it and fails closed around it; the operator
  should `launchctl unload` it (or bind it to 127.0.0.1) for a clean localhost-only
  setup managed by `saathi-local`.
- The macOS `⌥⌘B` binding is **prepared**, not auto-assigned (cannot safely
  enumerate all system bindings); operator assigns and verifies it.

## Not enabled by M57
Public exposure, 0.0.0.0 binding, tunnels, production mode, connector mutation,
financial/trading execution, multi-host mode, sudo, login auto-start.
