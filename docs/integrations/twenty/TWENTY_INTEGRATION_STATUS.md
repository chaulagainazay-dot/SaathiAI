# Twenty CRM integration status

This is the canonical current-status document for the optional Twenty CRM
evaluation. Detailed evidence remains in the linked audit and specifications;
historical verdicts are preserved rather than rewritten.

## Canonical state

| Dimension | Current value |
| --- | --- |
| Implementation | `OFFLINE_FOUNDATION_COMPLETE` |
| Capability boundary | `OFFLINE_READ_ONLY_INTEGRATION_FOUNDATION` |
| Owner review | `ACCEPTED_WITH_LIMITATIONS` |
| Publication | `DRAFT_BRANCH_PUBLISHED`; Draft PR #15 is open |
| Runtime | `TWENTY_RUNTIME_NOT_DEPLOYED` |
| Runtime-host decision | `RUNTIME_HOST_DECISION_DEFERRED`; approval not granted |
| Provider connectivity | `NO_LIVE_PROVIDER_CONNECTIVITY` |
| Write authority | `NO_CRM_WRITE_AUTHORITY` |
| Rollout | `OFF` |
| Data | `SYNTHETIC_DATA_ONLY` |
| Webhooks | `VERIFIED_EVENTS_TO_OBSERVATIONS_ONLY`; `NO_DIRECT_EXECUTION` |
| Deployment boundary | `TWENTY_SEPARATE_REPLACEABLE_SERVICE` |
| Licensing boundary | `API_SDK_WEBHOOK_APP_EXTENSION_BOUNDARY`; `NO_TWENTY_CORE_EMBEDDING` |
| Production | `NOT_AUTHORIZED` |

M361A pre-runtime readiness is `TWENTY_RUNTIME_READINESS_INCOMPLETE` and
`M361_ENTRY_NOT_READY`. The source pin and architecture are ready, but the
required CI check, immutable runtime image set, host selection, operator/billing
fields, private webhook feasibility, and approvals remain unresolved. This
checkpoint does not start M361 or alter the capability state.

The owner decision is
`TWENTY_OFFLINE_FOUNDATION_OWNER_ACCEPTED_WITH_LIMITATIONS`. The current summary
verdict is `TWENTY_OFFLINE_FOUNDATION_ACCEPTED_AND_PUBLISHED_WITH_RUNTIME_PENDING`.
M360 is `M360_COMPLETE_OWNER_ACCEPTED_WITH_LIMITATIONS`. The reviewed-SHA CI
state at decision time is `FINAL_SHA_CI_PENDING`.

The historical runtime-evaluation verdict remains
`TWENTY_SETUP_BLOCKED_BY_RESOURCE_CONSTRAINTS`. That verdict means the offline
contracts, fixtures, governance composition, tests, and evidence were completed,
while local runtime validation stopped safely because Docker/Compose were absent
and the 8 GB Mac was already under substantial memory pressure. It is a bounded
safety result, not proof of a broken implementation and not proof that Twenty runs.

## What exists

- A separate upstream audit clone and separate sandbox configuration.
- A provider-neutral, injected read transport contract with deterministic fixtures.
- Read contracts for companies, people, opportunities, tasks, metadata, and schema.
- Existing connector-registry composition with READ-only declarations; current
  rollout remains `OFF`.
- Organization/workspace scope mapping, fail-closed errors, redacted audit metadata,
  write rejection, and signed-webhook verification to observations only.
- Focused and connector-regression evidence.

## What does not exist

There is no deployed Twenty runtime, concrete network transport, API token,
credential resolution, authenticated REST/GraphQL call, generated workspace-schema
validation, custom-object installation, live webhook delivery, OAuth validation,
CRM write/delete method, email delivery, public endpoint, production data, or
production authorization.

SaathiOS continues to own identity, organization/workspace scope, missions,
agents, policy, approvals, execution authority, and audit. Twenty is intended to
own only replaceable CRM storage and CRM-native behavior behind supported APIs.

## Evidence and deeper specifications

- [Repository and licence audit](TWENTY_REPOSITORY_AUDIT.md)
- [Architecture and operations](ARCHITECTURE_AND_OPERATIONS.md)
- [Webhook security](WEBHOOK_SECURITY_SPEC.md)
- [Future approval-gated writes](FUTURE_APPROVAL_GATED_WRITES.md)
- [Runtime-host decision](RUNTIME_HOST_DECISION.md)
- [Milestone numbering](MILESTONE_NUMBERING_DECISION.md)
- [Draft-publication base decision](PUBLICATION_BASE_DECISION.md)
- [Next runtime program](M361_M368_READ_ONLY_RUNTIME_VALIDATION.md)
- [Historical evaluation report](evidence/FINAL_EVALUATION_REPORT.md)
- [Machine-readable historical evidence](evidence/TWENTY_EVALUATION_EVIDENCE.json)
- [M360 owner-acceptance record](evidence/M360_OWNER_ACCEPTANCE.md)
- [Machine-readable M360 owner decision](evidence/M360_OWNER_ACCEPTANCE.json)
- [M361A pre-runtime readiness](M361A_PRE_RUNTIME_READINESS.md)
- [Machine-readable M361A audit](evidence/M361A_READINESS_AUDIT.json)

## Separate runtime decision still required

Foundation acceptance does not authorize a host purchase, deployment,
connectivity, credentials, writes, OAuth, email, public webhooks, production use,
or M361 entry. M361–M368 remain `NOT_STARTED` and
`M361_ENTRY_BLOCKED_PENDING_SEPARATE_RUNTIME_HOST_APPROVAL`. No paid resource may
be created without a later explicit owner decision containing the required host,
cost, operator, expiry, network, data, and removal terms.

## Certification invalidation

This offline certification is invalidated by any unreviewed addition of a
network transport, CRM write/delete method, raw secret, public binding, real data,
email action, direct webhook execution, copied Twenty core/enterprise source,
rollout beyond SHADOW, or change to SaathiOS approval/execution authority. A
Twenty version/configuration change also invalidates runtime-contract assumptions
until the later runtime program revalidates them.
