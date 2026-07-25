# M54 Security Review

Scope: the readiness layer (diagnostics, export, retention) and the operator
browser surface. No change to identity, RBAC, approval, gateway, or binding
enforcement.

## Verified controls

| Control | Enforcement | Evidence |
|---|---|---|
| No browser-controlled role/authority | Role and permissions derive from the session token; client fields are never trusted | `isProductionAuthorized` fails closed; API derives ctx from token |
| Session revocation | Logout revokes the session; revoked token is rejected | browser-cert `logout` gate; `test_api_readiness_routes` anon 401/403 |
| Tenancy enforcement | Every readiness query scoped by org/workspace | `test_cross_tenant_export_and_diagnostics_are_isolated` |
| Binding lifecycle & stale version | M53 enforcement retained | M53 suite (regression) |
| Approval single-use / terminal immutability | M52/M53 retained | M53 suite |
| Uncertain-dispatch non-replay | `RESUME` rejected when `dispatch_started` | `test_restart_after_recorded_dispatch_cannot_replay` |
| Safe redaction | `_safe_text` + allowlist + forbidden-key scrub | `test_export_scrub_drops_forbidden_keys_and_redacts_secret_text` |
| Export redaction | No password/token/args/result/authorization in output | `test_export_execution_summary_is_redacted_and_hashed`, browser-cert `export_redaction` |
| Diagnostics redaction | No secrets/env/db path | `test_diagnostics_never_exposes_secrets_or_environment` |
| Retention permission | Owner/admin only (`ORG_MANAGE`) | `test_retention_requires_owner_authority` |
| No adapter / ToolExecutionService / ToolRegistry exposure | Readiness never imports them | code review |
| No connector mutation enablement | `connectors.mutations` stays `DRY_RUN_ONLY` | diagnostics assertion |
| No financial/trading enablement | Reported `DISABLED`; no enabling control | browser-cert `no_unsafe_actions`, `safety_boundaries` |

## Residual risk
- Single-host SQLite; no distributed authorization or telemetry.
- Retention purge is dry-run; real deletion deferred.
- Browser certification is local; not run against a hardened deployment.

## Not enabled by M54
OAuth, production credentials, live email, live connector mutation, financial
execution, trading execution, Trading Guardian engagement.
