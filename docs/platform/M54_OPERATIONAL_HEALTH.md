# M54 Operational Health & Diagnostics

`GET /api/v1/platform/runtime/diagnostics` — bounded, tenant-scoped, redacted
status for the private-alpha operator. Requires `RUNTIME_READ`.

## Reports
- **environment** — classification `LOCAL_OR_TEST`, `private_alpha: true`,
  `production_authorized: false`, private-alpha labels.
- **health** — api, frontend, database availability, platform schema version.
- **runtime** — total recent executions, queue state by execution state,
  attention count, waiting-approval / paused / recovering counts,
  reconciliation-record count.
- **bindings** — total and counts by state (ACTIVE / SUSPENDED / REVOKED).
- **safety** — connector mutations (`DRY_RUN_ONLY`), financial execution
  (`DISABLED`), trading execution (`DISABLED`), trading guardian
  (`UNENGAGED_ADVISORY_ONLY`), registered-tool authority (`ExecutionGateway`),
  canonical runtime (`PlatformAgentRuntime`).
- **certification** — latest recorded browser-certification timestamp.

## Never exposed
environment secrets, full process environment, database file contents or path,
credentials, or raw stack traces to unauthorized users. A regression test
asserts the serialized diagnostics contain no `password`, `token`, `secret`,
`db_path`, `.db`, or `authorization` substrings.

## UI surface
The `/platform` readiness panel renders the classification/labels, safety badges,
and the runtime counts, and clearly displays: PRIVATE ALPHA · LOCAL OR TEST
ENVIRONMENT · NON-PRODUCTION · CONNECTOR MUTATIONS DRY-RUN · FINANCIAL EXECUTION
DISABLED · TRADING DISABLED.
