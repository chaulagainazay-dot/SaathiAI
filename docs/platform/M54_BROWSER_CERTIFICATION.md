# M54 Browser Certification

Harness: `saathi-os/scripts/m54_browser_cert.mjs` (`npm run cert:m54`).
Evidence: `docs/platform/m54_evidence/m54_browser_cert.json` + `screenshots/`.

## Lifecycle
clean ports → isolated `SAATHI_PLATFORM_DB` → start BFF (uvicorn
`saathi.server:app`, CORS scoped to the managed UI origin) → seed owner + binding
+ governed read-only execution via API → start UI (Next.js dev by default; build
with `M54_BUILD=1`) → inject the session token and drive the authenticated
`/platform` operator surface in headless Chromium → screenshots + evidence JSON →
teardown (kill UI/BFF, remove the disposable database).

Exit 0 only when every hard gate passes. `--allow-limitations` downgrades to a
soft verdict. The harness never fabricates network success, never marks a PR
ready, and never enables connectors, financial execution, or trading.

## Gates

**API contract (server-to-server):**
`auth` (anonymous diagnostics denied), `safety_boundaries` (production not
authorized; financial/trading DISABLED; connectors DRY_RUN_ONLY; canonical
runtime + sole gateway), `export_redaction` (no password/args/result/token/
authorization; `production_data: false`), `retention_dry_run` (DRY_RUN, not
executed), `logout` (revoked token rejected).

**Browser UI (real Chromium against the operator surface):**
`ui_readiness` (readiness panel + safety badges + LOCAL_OR_TEST), `ui_binding_admin`
(seeded binding listed), `ui_export` (export manifest with `sha256:` hash and
`production_data false`), `no_unsafe_actions` (no live trade/withdraw/connector
controls), `ui_logout` (authenticated surface cleared).

Soft gate: `ui_retention` (dry-run retention plan visible).

## Flows exercised
Authentication & tenancy, binding administration, governed execution, approval
handling, runtime attention, safe reconciliation (non-replay verified in
backend), audit/lifecycle evidence, evidence export, logout & post-logout
protection.

## CI status
See `M54_TEST_REPORT.md` and `M54_LIMITATIONS.md`. The browser certification is
certified **locally**. The reliability CI workflow runs the deterministic backend
contract tests (`tests/test_m54_readiness.py`) as the CI-side guarantee; the full
managed BFF+UI+Chromium run is kept local (resource/stability) unless explicitly
enabled, and is not falsely claimed as CI-certified.

## Result
The recorded verdict and per-gate results for the current run are in
`docs/platform/m54_evidence/m54_browser_cert.json`.
