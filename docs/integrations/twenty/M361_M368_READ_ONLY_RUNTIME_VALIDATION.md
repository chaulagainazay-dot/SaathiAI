# M361–M368 — Twenty read-only provider connectivity and schema validation

Status: `NOT_STARTED`; blocked on explicit runtime-host owner approval.

## Objective

Validate the existing offline read contracts against one pinned, isolated Twenty
runtime containing synthetic data, without introducing CRM writes or production
authority. This program follows M360 publication and uses M361–M368 as the phases
defined in the numbering decision.

## Entry criteria

1. Owner records acceptance or rejection of the offline foundation separately.
2. Owner approves one runtime option, cost ceiling, operator, expiry, and removal plan.
3. Host satisfies the private-network baseline and recommended capacity.
4. Twenty commit/version and container image digest are pinned and reviewed.
5. Configuration contains no email, external OAuth provider, public binding, or real data.
6. SaathiOS branch is clean; existing connector, credential-reference, audit,
   tenant, approval, and Execution Gateway authorities remain canonical.

Failure of any entry criterion yields `TWENTY_RUNTIME_HOST_NOT_APPROVED` and no
runtime action.

## Scope

- M361: approve and prepare private/isolated host; no connectivity yet.
- M362: deploy pinned server, worker, PostgreSQL, Redis, storage, network, and
  synthetic workspace; prove private exposure, health, shutdown, and removal plan.
- M363: create a least-privilege read-only API token, store only its credential
  reference in SaathiOS, and validate health plus bounded REST GET operations.
- M364: inspect workspace-generated GraphQL and metadata schemas; validate
  pagination, native Company/Person/Opportunity/Task objects, object metadata,
  and approved synthetic custom objects. GraphQL is tested only if exposed by the
  pinned official runtime.
- M365: validate actual webhook delivery, HMAC/timestamp/nonce, durable replay
  protection, tenant routing, redaction, dead-letter handling, and observation-only
  behavior. No public endpoint and no direct execution.
- M366: prove restart persistence, migration status, encrypted backup/restore into
  a disposable target, clean shutdown, and bounded removal.
- M367: measure CPU/RAM/disk, timeouts/retries, rate limits, network isolation,
  forbidden egress, secret leakage, tenant/workspace isolation, and failure recovery.
- M368: capture immutable evidence and issue an accurate read-only terminal verdict.

All data is synthetic. All API calls are read-only. Retries must be bounded and
must not turn an unknown result into a write or new authority. Audit evidence is
redacted and scoped to organization/workspace.

## Explicit exclusions

No production deployment or certification; public exposure; real customer,
hospital, supplier, employee, patient, portfolio, or financial data; write/delete
method; autonomous action; email; production OAuth; live business workflow;
Trading Guardian change; approval/gateway authority change; merge to main; or
production rollout.

## Exit criteria

- Pinned runtime and private network are reproducible and removable.
- Health, REST, conditional GraphQL, pagination, metadata, native objects, and
  selected custom objects match captured schemas using synthetic fixtures.
- Tenant/workspace boundaries and least privilege fail closed.
- Timeouts, retries, unavailable runtime, malformed responses, revocation, and
  credential-reference failures are tested.
- Webhooks, if enabled, produce durable audited observations only.
- Restart/persistence, backup/restore, resource measurements, secret/network scans,
  clean shutdown, and removal evidence pass.
- Adapter remains read-only with no delete, email, or direct execution surface.

## Abort conditions

Abort and isolate the runtime on any public exposure, forbidden egress, real-data
appearance, raw-secret leak, unexpected write capability, cross-tenant access,
direct webhook execution, image/digest mismatch, unbounded resource pressure,
unrecoverable migration/backup failure, unclear billing, expired approval, or
scope expansion. Preserve evidence; do not weaken the gate to continue.

## Evidence requirements

Record host class without secrets, approval reference, pinned commit/image digest,
sanitized configuration fingerprint, container health, private bindings, network
requests, generated schemas, synthetic record checksums, API/webhook transcripts
with secrets redacted, audit records, tests, resource samples, restart/restore
results, shutdown/removal results, branch/SHA, and all limitations.

## Allowed terminal verdicts

- `TWENTY_RUNTIME_HOST_NOT_APPROVED`
- `TWENTY_RUNTIME_ENVIRONMENT_PREPARED_NO_CONNECTIVITY`
- `TWENTY_READ_ONLY_PROVIDER_CONNECTIVITY_VALIDATED_WITH_LIMITATIONS`
- `TWENTY_SCHEMA_VALIDATION_BLOCKED`
- `TWENTY_RUNTIME_VALIDATION_FAILED`
