# M61 — Final Report: Backend Workflow Persistence & Safe Mutation APIs

## 1. Overall Verdict
**M61_COMPLETE_WITH_LIMITATIONS.** Every M60 frontend-only / draft / derived /
local / blocked workflow placeholder now has a durable, server-authoritative,
permission-gated, audited, optimistic-concurrency-checked API — without changing
execution authority. The browser is thinner; the server is the source of truth.
Bounded limits remain (single-host SQLite; incremental UI adoption; production
unauthorized).

## 2. Verified Starting State
Branch `milestone/m60-guided-operator-workflows` @ `78a46a8`; clean tree except
untracked `docs/design-spec/` (preserved). FE baseline 130 tests + lint green.

## 3. Gap Matrix
| Capability | M60 | Gap | M61 target | Done |
|---|---|---|---|---|
| mission_plan | DRAFT_ONLY | no persistence | SERVER_PERSISTED | ✔ |
| notification | DERIVED | no records | SERVER_PERSISTED+AUDITED | ✔ |
| saved_view | LOCAL_ONLY | no persistence | SERVER_PERSISTED | ✔ |
| template | LOCAL_ONLY | no persistence | SERVER_PERSISTED | ✔ |
| attention ack/resolve | BLOCKED | no API | SERVER_AUTHORIZED+AUDITED | ✔ |
| search | loaded-records | client-only | SERVER_AUTHORIZED | ✔ |
| drafts | local | no persistence | SERVER_PERSISTED | ✔ (API) |
| concurrency | none | silent overwrite | OPTIMISTIC (version/409) | ✔ |

## 4. API Contracts Added
20 endpoints under `/api/v1/platform/workflow/*` (plans, notifications, saved-views,
templates, drafts, attention, search). See `M61_API_CONTRACTS.md`. Permission-gated,
audited, tenant-scoped, 409 on stale writes, 400 on secret-bearing payloads.

## 5. Mission Plan Persistence
`workflow_plans` + revisions; draft/published/archived; explicit publish; version
history. Certified: persist, reload, 409 conflict. See `M61_PLAN_PERSISTENCE.md`.

## 6. Notification Service
`notifications` table; durable, deduped, read/archive flags, audited. Derived events
synced into durable records by the Notification Center. See `M61_NOTIFICATION_SERVICE.md`.

## 7. Saved Views
`saved_views` (versioned, user+workspace); secret-field rejection; certified to
survive a fresh browser. See `M61_SAVED_VIEWS.md`.

## 8. Workflow Templates
`workflow_templates` (versioned); publish-to-server from the starter catalog. See
`M61_TEMPLATE_SERVICE.md`.

## 9. Attention Mutation APIs
`attention_states`; acknowledge/resolve/reopen; audited; runtime execution never
altered. Surfaced as a Triage panel. See `M61_ATTENTION_MUTATIONS.md`.

## 10. Server Search
`GET /workflow/search` — tenant-scoped, ranked, `SERVER_AUTHORIZED`; no cross-tenant
leak (certified). See `M61_SERVER_SEARCH.md`.

## 11. Draft Persistence
`workflow_drafts` (one per kind/user/workspace, expiring, versioned); secret-guarded.
API + tests. See `M61_DRAFT_PERSISTENCE.md`.

## 12. Concurrency Control
Integer `version` + `expected_version` → 409 STALE_STATE; never silent overwrite;
client `isConflict()` + reconciliation UI. See `M61_CONCURRENCY.md`.

## 13. Audit & Evidence
Every create/update/decision/attention mutation writes an `audit_events` row with
actor + timestamp + detail. Certified (`mutation_audited`). Evidence remains immutable.

## 14. Browser Compatibility
M60 UI interaction model unchanged; only data adapters swapped (LOCAL_ONLY →
SERVER_PERSISTED). Fresh-browser render of server data certified.

## 15. Production Browser Certification
`npm run cert:m61:build` — API contract + fresh-browser persistence gates. Verdict:
see `m61_evidence/m61_browser_cert.json`.

## 16. Accessibility Regression
No new axe-critical surfaces; M60 axe posture retained (0 critical). New controls
(Triage buttons, Save/Publish) reuse the accessible `ws-chip` + reconciliation chip.

## 17. Performance
20 endpoints are single-transaction SQLite ops; no polling added; search is bounded
(capped limit, tenant-scoped). No FE bundle regression (adapters are thin).

## 18. Security Review
All checks PASS — authorization on every mutation, tenant isolation, secret-field
rejection, audit completeness, no browser/execution authority. See `M61_SECURITY_REVIEW.md`.

## 19. Tests
Backend: `tests/test_m61_workflow_persistence.py` — 11 tests (service + HTTP +
concurrency + RBAC + isolation + audit). Existing platform tests: 53 pass (no
regression). Frontend: 130 unit + lint + build green.

## 20. Documentation
13 `docs/platform/M61_*.md` + `m61_evidence/`. ROADMAP / TECHNICAL_DEBT / Brain updated.

## 21. Remaining Limitations
Single-host SQLite; incremental UI draft adoption; client-triggered notification
synthesis; production unauthorized. See `M61_LIMITATIONS.md`.

## 22. Recommended M62
**M62 — Distributed Platform Readiness & Multi-Node Coordination (Private Alpha)**:
event streaming, durable queues, distributed scheduler, node federation, worker
coordination, observability — with execution authority still
PlatformAgentRuntime → ExecutionGateway → Registered Tool. No production expansion.
Not started in M61.

## 23. Authority Statement
See below — verified claims only.

---

```
M61_COMPLETE_WITH_LIMITATIONS
MISSION_PLAN_PERSISTENCE_ACTIVE
NOTIFICATION_SERVICE_ACTIVE
SERVER_SAVED_VIEWS_ACTIVE
SERVER_WORKFLOW_TEMPLATES_ACTIVE
ATTENTION_MUTATION_APIS_ACTIVE
SERVER_SEARCH_ACTIVE
DRAFT_PERSISTENCE_ACTIVE
OPTIMISTIC_CONCURRENCY_ACTIVE
AUDIT_EVIDENCE_AUTOMATION_ACTIVE
REAL_API_BINDING_RETAINED
PLATFORM_AGENT_RUNTIME_RETAINED_AS_CANONICAL
EXECUTION_GATEWAY_RETAINED_AS_SOLE_REGISTERED_TOOL_AUTHORITY
SERVER_OWNED_APPROVALS_RETAINED
TENANT_ISOLATION_RETAINED
SINGLE_HOST_SQLITE_PERSISTENCE
LOCALHOST_ONLY
MULTI_HOST_MODE_DISABLED
CONNECTOR_MUTATIONS_DRY_RUN_ONLY
FINANCIAL_EXECUTION_DISABLED
TRADING_EXECUTION_DISABLED
NO_PUSH_PERFORMED
NO_MERGE_PERFORMED
NO_DEPLOYMENT_PERFORMED
PRODUCTION_NOT_AUTHORIZED
```
