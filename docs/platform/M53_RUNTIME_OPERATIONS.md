# M53 Runtime Operations

## Safe views

The operations service provides execution lists and detail filtered by state,
project, mission, binding, user, tool, and time. Detail includes approval status,
reconciliation records, and safe idempotency presence/reference metadata. It
does not expose arguments, results, session tokens, approval secrets,
credentials, authorization headers, or raw SQLite rows.

Lifecycle timelines combine structured runtime audit records and operator
reconciliation evidence. Metrics aggregate persisted state by lifecycle,
failure, tool, and binding, with an explicit single-host timestamp basis.

## API

- `POST/GET /api/v1/platform/agent-bindings`
- `GET/PATCH /api/v1/platform/agent-bindings/{binding_id}`
- `POST .../{binding_id}/{suspend|activate|revoke|rotate}`
- `GET /api/v1/platform/runtime/executions`
- `GET /api/v1/platform/runtime/executions/{execution_id}`
- `GET /api/v1/platform/runtime/executions/{execution_id}/timeline`
- `GET /api/v1/platform/runtime/attention`
- `GET /api/v1/platform/runtime/metrics`
- `POST /api/v1/platform/runtime/executions/{execution_id}/reconcile`
- `POST /api/v1/platform/runtime/executions/{execution_id}/cancel`

The pre-existing resume endpoint remains for compatibility and delegates to
`PlatformAgentRuntime`.

Contract hardening: the existing cancellation endpoint now requires the
inherited `runtime.operate` permission (owner/admin) instead of permitting an
execution-owning operator to cancel directly. This is an intentional
administrative-boundary correction; execution dispatch compatibility is
unchanged.

## UI

The existing `/platform` shell now displays scoped bindings, runtime summary
metrics, attention items, recent executions, and lifecycle detail. Revocation
and cancellation require confirmation. The UI does not offer financial/trading
authority or production actions.
