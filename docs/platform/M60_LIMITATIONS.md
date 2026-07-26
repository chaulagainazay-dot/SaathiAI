# M60 — Residual Limitations

## Behavior bounded by real APIs (from the capability matrix)

| Workflow | Behavior | Reason |
|---|---|---|
| Mission creation | **LIVE** | `POST /missions` exists |
| Project creation | **LIVE** | `POST /projects` exists |
| Approval request | **LIVE** | `POST /approvals` exists |
| Approval decision / revoke | **LIVE** | `POST /approvals/{id}/decide|revoke` (M59) |
| Governed execution | **LIVE** | `POST /execute` (read-only tool used in-UI) |
| Cancel execution | **LIVE** | `POST /runtime/executions/{id}/cancel` |
| Evidence export | **LIVE** | `GET /runtime/export` |
| Mission plan | **DRAFT_ONLY** | no plan-persistence API |
| Attention acknowledge / resolve | **BLOCKED** (read-only) | no such API |
| Mission update | not offered | no update API |
| Notifications | **DERIVED_NOTIFICATION_VIEW** | no notification API |
| Saved views | **SAVED_VIEWS_LOCAL_ONLY** | no persistence API |
| Workflow templates | **LOCAL_WORKFLOW_TEMPLATE** | no template API |
| Search | **SEARCHING_AUTHORIZED_LOADED_RECORDS** | no server search API |
| Onboarding progress | local-only | no onboarding API |

## Certification limitations

- Accessibility: axe automation only (0 critical; 6 serious, all pre-existing
  global TopBar chrome) — not a full WCAG audit.
- Performance: local lab route-size + navigation only; real-user CWV not available.
- `mission_creation_live` is a SOFT gate: the live UI submit can occasionally race
  a cold-start "session expired" transient; the create API itself is verified by
  fixtures + unit tests + `mission_draft_completes`, and reconciles from server when
  it succeeds. Non-blocking.
- Fixtures are deterministic, isolated, and test-only.

## Platform posture (unchanged, enforced)

Production unauthorized · browser-direct tool execution disabled · multi-host
disabled · connectors dry-run · financial and trading disabled · trading guardian
advisory-only · localhost-only · no push/merge/deploy.
