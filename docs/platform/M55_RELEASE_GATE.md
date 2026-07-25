# M55 Release Gate

A deterministic release-candidate report. Advisory only — reports whether a
deployment WOULD be ready without changing anything or enabling production.

## Run
```
python -m saathi.platform.release_check          # human summary
python -m saathi.platform.release_check --json    # machine JSON
```
API: `POST /api/v1/platform/release/validate` (owner/admin).

The gate runs against a **fresh isolated platform**, so the structural verdict is
reproducible and never touches operator data.

## Sections
architecture, runtime, database, storage, security, approval, bindings, recovery,
diagnostics, metrics, evidence, retention, health, backup, browser, ui, tests,
documentation.

## Release-validator checks (PASS/WARNING/FAIL/UNKNOWN)
authentication, session_management, authorization, database, migrations, storage,
runtime, bindings, approval_system, tenant_isolation, evidence_export, retention,
diagnostics, health_endpoints, security_headers, no_secrets_exposed, no_debug_mode,
feature_flags, provider_configuration, production_mode.

Aggregate `readiness_score = (PASS + 0.5·WARNING) / total · 100`.

## Overall status
- **READY** — all PASS.
- **READY_WITH_LIMITATIONS** — no FAIL, but WARNING/UNKNOWN present.
- **NOT_READY** — any FAIL.

By design, `production_mode`, `feature_flags`, and `provider_configuration` are
WARNING in the private-alpha RC (production intentionally disabled), so the
expected verdict is **READY_WITH_LIMITATIONS** (score ≈ 92.5). This is **not** a
deployment authorization.

## Boundary
No production deployment, no connector mutation, no financial/trading execution.
Trading Guardian unengaged/advisory-only.
