# M55 Browser Certification

Harness: `saathi-os/scripts/m55_browser_cert.mjs` (`npm run cert:m55`).
Evidence: `docs/platform/m55_evidence/m55_browser_cert.json` + `screenshots/`.
Result: **`M55_BROWSER_CERTIFIED`** — all hard gates green.

## Lifecycle
clean ports → isolated `SAATHI_PLATFORM_DB` → start BFF (`saathi.server:app`,
CORS scoped to the managed UI origin) → seed owner + binding + governed execution
via API → start UI (Next.js dev by default; `M55_BUILD=1` for prod) → inject the
session token and drive the authenticated `/platform/ops` operator console in
headless Chromium → screenshots + evidence JSON → teardown (kill UI/BFF, remove
the disposable database).

Exit 0 only when every hard gate passes. Never fabricates network success, never
marks a PR ready, never enables connectors, financial, or trading execution.

## Gates

**API contract (server-to-server):** auth (anonymous denied),
safety_boundaries, export_redaction, retention_dry_run, release_validation
(READY/READY_WITH_LIMITATIONS, no FAIL, production not authorized), health,
metrics, backup_simulation (simulation only, non-destructive),
recovery_certification (PASS/WARNING, no_replay invariant), logout.

**Operator console (real Chromium):** ops_console (non-production banner +
labels), ops_health (runtime ok, production authorized false), ops_metrics,
ops_release (READY/READY_WITH_LIMITATIONS, FAIL 0), ops_recovery
(PASS/WARNING, scenarios listed), ops_backup (SIMULATION_ONLY, non-destructive),
no_unsafe_actions.

## Surfaces validated
Operator Console, Health, Metrics, Release Gate, Recovery Status, Backup
Validation, Diagnostics/Approvals/Bindings (via the M54-certified platform
surface), Evidence Export, Retention Preview.

## CI status
Certified **locally** (managed BFF+UI+Chromium). The reliability CI full-suite
runs the deterministic backend contract tests (`tests/test_m55_release.py`) as
the CI-side guarantee; the full browser run is kept local (resource/stability)
and is not falsely claimed as CI-certified.
