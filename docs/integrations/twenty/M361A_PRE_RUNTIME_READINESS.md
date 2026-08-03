# M361A — Twenty pre-runtime readiness verification

Assessment timestamp: `2026-08-03T17:46:27+05:45`

Terminal verdict: `TWENTY_RUNTIME_READINESS_INCOMPLETE`

M361 entry decision: `M361_ENTRY_NOT_READY`

This is an evidence-only decision-support checkpoint. It does not install,
start, provision, connect, authenticate, expose, or authorize a Twenty runtime.

## State invariants

- M360: `M360_COMPLETE_OWNER_ACCEPTED_WITH_LIMITATIONS`.
- Foundation: `OFFLINE_FOUNDATION_COMPLETE` and
  `OFFLINE_READ_ONLY_INTEGRATION_FOUNDATION`.
- Runtime: `TWENTY_RUNTIME_NOT_DEPLOYED`.
- Runtime decision: `RUNTIME_HOST_DECISION_DEFERRED` and
  `RUNTIME_HOST_APPROVAL_NOT_GRANTED`.
- M361–M368: `NOT_STARTED`.
- Rollout: `OFF`.
- Connectivity: `NO_LIVE_PROVIDER_CONNECTIVITY`.
- Authority: `NO_CRM_WRITE_AUTHORITY` and production `NOT_AUTHORIZED`.

## CI classification

GitHub reliability run `30809497607` for SHA `12be0aa18cc88d81c1186998454cdd1497d06fd5`
completed with failure. The only blocking manifest failure was
`ops.hardening_m13_5`: `tests/test_ops.py::test_release_gate_passes_baseline`
returned release-gate exit code 3 (1 failed, 24 passed). The Twenty branch does
not change that test or its ops implementation, and the manifest reported the
connector, webhook-security, secret-redaction, approval, execution-boundary,
trading-boundary, registry, and other listed critical checks as passed.

The failure is classified as an unrelated baseline/release-readiness failure,
not evidence of a Twenty regression. It is nevertheless a failed required check,
so CI is not acceptable for M361 entry until separately resolved or formally
waived by repository policy. This assessment does not alter implementation to
manufacture a green result.

## Proposed trust-boundary architecture

```text
OWNER (approval and scope authority)
  -> SAATHIOS (identity, tenant, policy, approval, audit authority)
    -> READ-ONLY TWENTY ADAPTER (scope checks; credential reference only)
      -> PRIVATE TWENTY RUNTIME (replaceable; no SaathiOS authority)
        -> SYNTHETIC WORKSPACE (disposable validation data only)
```

```text
PRIVATE TWENTY WEBHOOK DELIVERY (only if private routing is proven)
  -> SIGNATURE + TIMESTAMP VERIFICATION
    -> DURABLE REPLAY / IDEMPOTENCY CHECK
      -> REDACTION + TENANT ROUTING
        -> OBSERVATION RECORD
          -> NO DIRECT EXECUTION
```

Trust boundaries are owner-to-operator approval, SaathiOS-to-adapter authority,
adapter-to-private-runtime network/authentication, and runtime-to-webhook input.
Failures remain contained by deny-by-default networking, read-only role controls,
adapter scope checks, observation-only handling, and full runtime removal.

## Readiness questions

### 4.1 Repository and publication readiness

Status: `READY_WITH_LIMITATIONS`

Evidence: M360 acceptance is recorded; the branch was clean and local/remote SHA
matched; PR #15 is the only PR for the branch and remains Draft; M361–M368 is
`NOT_STARTED`; historical M360 evidence remains intact.

Risk: The required reliability workflow failed in unrelated ops hardening, so CI
cannot be marked acceptable.

Decision: Repository history and publication state are credible, but the CI entry
row remains `FAIL`.

Required action: Resolve or policy-classify the required CI failure without
changing Twenty code merely to obtain a pass.

### 4.2 Runtime-host options

Status: `READY_WITH_LIMITATIONS`

Evidence: [Runtime option comparison](RUNTIME_OPTION_COMPARISON.md) assesses a
private temporary host, a lightweight local runtime, and postponement.

Risk: No provider, operator, cost ceiling, or dates are selected.

Decision: A private temporary host remains the recommended future option; it is
not selected or approved.

Required action: Owner must complete the decision fields in the cost and entry
criteria records.

### 4.3 Host resource baseline

Status: `READY_WITH_LIMITATIONS`

Evidence: [Runtime resource baseline](RUNTIME_RESOURCE_BASELINE.md) decomposes
application, worker, database, cache, OS, logs, and backup allowances.

Risk: No Twenty workload was benchmarked; source builds need materially more
capacity than the proposed runtime-only envelope.

Decision: 4 vCPU, 8 GB RAM, and 40 GB encrypted SSD is a safe validation planning
floor, not a measured production or source-build minimum.

Required action: Select a host and verify capacity before approval; use the abort
thresholds during any later session.

### 4.4 Apple Silicon and image compatibility

Status: `UNKNOWN`

Evidence: The owner host is ARM64. Upstream Dockerfiles use `TARGETARCH`, but the
published Twenty, PostgreSQL, Redis, and Node image manifests were not pulled or
inspected, as required by this milestone's boundary.

Risk: An AMD64-only dependency could require emulation, increasing memory,
thermal, and latency pressure on the 8 GB Mac.

Decision: Apple Silicon compatibility is unproven; local runtime use is not ready.

Required action: Resolve architecture and immutable manifest digests during a
separately approved preparation step on the selected host.

### 4.5 Version and supply-chain readiness

Status: `NOT_READY`

Evidence: Clean upstream source is pinned at
`37f1fe17ab48269384cffb774f82f096abe3863a`; `yarn.lock`, Node/Yarn requirements,
Dockerfiles, and Compose definitions exist. Compose defaults still use tags such
as `twentycrm/twenty:${TAG:-latest}`, `postgres:16`, and `redis`.

Risk: Tags are mutable and no full runtime image set or digest has been selected.

Decision: `SOURCE_PIN_READY`; `IMAGE_DIGEST_NOT_READY`;
`DEPENDENCY_PINNING_NOT_READY` for the complete runtime stack.

Required action: Pin Twenty, PostgreSQL, Redis, and any supporting image by digest,
or approve and document a reproducible source-build alternative.

### 4.6 Architecture readiness

Status: `READY`

Evidence: The knowledge graph and source show an injected `TwentyTransport`, a
fixture-only implementation, scoped `TwentyReadService`, canonical connector
manifest composition, explicit denied write operations, and observation-only
webhook results.

Risk: A future concrete transport could violate the boundary if introduced
outside connector governance.

Decision: `TWENTY_SEPARATE_REPLACEABLE_SERVICE` is credible and contains no
duplicate mission, approval, execution, or provider registry.

Required action: Require a future transport review and authority regression scan.

### 4.7 Authentication and least privilege

Status: `READY_WITH_LIMITATIONS`

Evidence: Upstream documentation supports expiring API keys assigned to custom
roles with object/field/action permissions. The future model is defined in
[Auth and least privilege plan](AUTH_AND_LEAST_PRIVILEGE_PLAN.md).

Risk: Metadata/schema reads and every intended endpoint have not been proven with
a technically enforced no-edit/no-delete role.

Decision: `AUTH_MODEL_READY_WITH_LIMITATIONS`.

Required action: Approve the role design and prove denial of mutations before any
read validation is accepted.

### 4.8 Synthetic data plan

Status: `READY`

Evidence: [Synthetic data manifest](SYNTHETIC_DATA_MANIFEST.md) defines synthetic
workspaces, users, records, pagination, metadata, webhooks, archive/delete states,
and tenant-separation fixtures with cleanup requirements.

Risk: The manifest has not been instantiated or cleanup-tested.

Decision: The data design is complete for approval review, not runtime-proven.

Required action: Generate only from the manifest after runtime approval.

### 4.9 Network and exposure readiness

Status: `READY_WITH_LIMITATIONS`

Evidence: [Network and egress policy](NETWORK_AND_EGRESS_POLICY.md) defines private
ingress, internal data services, explicit validation paths, and denied public
exposure, email, OAuth, telemetry, and third-party integrations.

Risk: Exact provider controls, private DNS/TLS, and runtime egress inventory are
unknown until a host is selected.

Decision: Policy design is ready; deployment-specific enforcement is not.

Required action: Owner/security reviewer must approve an instantiated firewall and
egress allowlist before startup.

### 4.10 Webhook readiness

Status: `NOT_READY`

Evidence: The offline verifier covers HMAC, timestamps, allowlists, size limits,
redaction, malformed payloads, and in-process replay. Upstream documentation says
the configured webhook URL must be publicly accessible and sends all event types.

Risk: Public exposure violates the default policy, and current replay state is not
durable across process restart.

Decision: Webhook validation cannot enter M365 unless private delivery is proven
or a separate public-exposure approval is granted. No bypass is permitted.

Required action: Design durable replay storage and resolve private delivery before
approving the webhook phase.

### 4.11 Persistence, backup, restore, and removal

Status: `READY_WITH_LIMITATIONS`

Evidence: [Backup, restore, and removal plan](BACKUP_RESTORE_REMOVAL_PLAN.md)
defines `CREATE` through `VERIFY_REMOVAL`, encrypted backups, disposable restore,
and deletion evidence.

Risk: Operator, provider mechanics, deadlines, and restore/removal tests are absent.

Decision: Lifecycle design is reviewable but not executable yet.

Required action: Assign roles, dates, provider procedures, and approve the plan.

### 4.12 Cost and billing readiness

Status: `NOT_READY`

Evidence: [Cost and expiry plan](COST_AND_EXPIRY_PLAN.md) supplies a provisional,
non-vendor planning range and all required owner fields.

Risk: Provider, currency approval, payer, ceiling, dates, alerts, and tax treatment
are unresolved.

Decision: No cost may be incurred.

Required action: Owner must complete every billing field before runtime approval.

### 4.13 Operator and accountability readiness

Status: `NOT_READY`

Evidence: Required roles are defined as `OWNER`, `RUNTIME_OPERATOR`,
`SECURITY_REVIEWER`, `EVIDENCE_REVIEWER`, and `COST_OWNER`.

Risk: No human is assigned; no agent may self-assign or accept accountability.

Decision: Provisioning and deletion cannot be authorized.

Required action: Owner must name accountable humans and separation-of-duty rules.

### 4.14 Abort-condition readiness

Status: `READY_WITH_LIMITATIONS`

Evidence: [M361 entry criteria](M361_ENTRY_CRITERIA.md) includes detection, immediate
action, evidence, role, and recovery for every required abort condition.

Risk: Thresholds and responsible people are not approved or host-tested.

Decision: The abort catalogue is complete for review but not operational.

Required action: Security reviewer and owner must approve it after host selection.

### 4.15 M361 entry readiness

Status: `NOT_READY`

Evidence: The entry matrix contains `PASS`, `FAIL`, `PENDING_OWNER_DECISION`, and
`UNKNOWN` rows; not every mandatory row is `PASS`.

Risk: Starting now would bypass CI, image, host, operator, billing, auth, network,
backup, removal, and webhook gates.

Decision: `M361_ENTRY_NOT_READY`.

Required action: `RESOLVE_READINESS_GAPS`; then obtain a new explicit owner decision.

## Recommended option and next action

Recommended future option:
`PRIVATE_TEMPORARY_DEVELOPMENT_HOST_RECOMMENDED`.

It offers better isolation and resource headroom than the already pressured 8 GB
Apple Silicon Mac, and it is easier to expire and delete than a persistent local
installation. This is a recommendation, not provider selection or authorization.

Next action: `RESOLVE_READINESS_GAPS`.

```text
M361_NOT_STARTED
RUNTIME_HOST_APPROVAL_STILL_REQUIRED
```
