# M16 Unified Control Center Audit

## Start state
Commit f0d38a6 (M15.3). 1314 passed. CONNECTOR STAGING READY.

## Existing surfaces (classified)
| surface | class | M16 action |
|---------|-------|-----------|
| /ceo (M14 CEO OS) | canonical | link/embed (canonical CEO APIs) |
| /connectors (M15.1) | canonical | link (Connector Observatory deep-links here) |
| /security (redteam report API M15.2) | canonical | Security Center reads release_gate + baseline |
| /studio-os, ops dashboard (M13.5) | canonical | link |
| infrastructure health endpoint | reusable | aggregated into Overview health cell |
| department dock | reusable | + CONTROL entry |
| root dashboards / mission control | reusable/embed | deep-linked, not duplicated |

## What M16 added (control/observation only — no duplicate execution)
- saathi/control_center/aggregator.py: bounded, partial-failure aggregation over
  canonical subsystems; Cell(value, source, status, observed_at, degraded_reason).
- read models: overview, attention (ranked), platform_health, security_posture,
  release_readiness, connector_metrics, recent_timeline, pending_approvals.
- search.py: federated, OWNER-SCOPED, secret-free (connectors/operations public;
  accounts/approvals/executions owner-filtered).
- actions.py: unified ActionDescriptor pointing ONLY at canonical subsystem APIs
  (approval.approve → /api/v1/connectors/approvals/{id}/decide, etc.).
- api.py: /api/v1/control/* — READ-ONLY (GET/HEAD), authenticated, owner-scoped.
- cli.py: overview/attention/health/security/release/timeline/search.
- UI: /control Overview on the real API (source+freshness, honest degraded/
  unavailable, bounded refresh paused when tab hidden), + dock entry.

## Non-negotiables honored
Control Center never executes, never writes subsystem stores, never bypasses
ExecutionGateway (test_control_api_is_read_only + test_actions_point_at_canonical_apis).
Owner scoping enforced (search isolation tests). No secrets in read models.

## Honest limits (NOT done / environment-blocked)
Interactive/authenticated browser verification (build only); real-time streaming
(bounded polling used — not called streaming); live provider/OAuth data; the full
set of deep observatories (Agent/Studio/Connector/Memory/Knowledge/Logs) and the
approval-click browser flow are deep-linked to canonical pages rather than fully
re-built here. Cost/provider centers reuse the honest live-validation matrix
(configured != healthy != live-tested) rather than fabricating actuals.
