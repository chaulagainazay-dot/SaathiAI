# M361B — Twenty runtime readiness gap resolution

Assessment time: `2026-08-03T13:07:51Z`

Terminal verdict: `TWENTY_RUNTIME_GAPS_PARTIALLY_RESOLVED`

M361 entry decision: `M361_ENTRY_NOT_READY`

Runtime recommendation: `HOST_ARCHITECTURE_DECISION_PENDING`

Recommended next action: `RESOLVE_REMAINING_TECHNICAL_GAPS`

This is an offline, evidence-only readiness sub-checkpoint. It does not renumber
the reserved program and does not start M361.

## Authoritative owner decision

The following owner decision is recorded exactly in meaning:

```text
M361A_COMPLETE_WITH_LIMITATIONS
M361_ENTRY_NOT_READY
RUNTIME_HOST_APPROVAL_NOT_GRANTED
HOST_PURCHASE_OR_PROVISIONING_NOT_AUTHORIZED
M361_M368_NOT_STARTED
```

The owner accepts the M361A assessment and its limitations. No owner name,
signature, provider, operator, reviewer, cost owner, budget, date, region, or
approval identifier is inferred.

## Gap-resolution matrix

| Gap | Result | Resolution state | Decision |
| --- | --- | --- | --- |
| Required CI failure | `CI_GAP_REQUIRES_SEPARATE_REPAIR` | `REQUIRES_SEPARATE_REPAIR` | Reproduced and classified `PRE_EXISTING_BASELINE_FAILURE`; unchanged Twenty-unrelated scanner/test paths; required check remains red |
| Immutable image digests | `IMAGE_DIGEST_SET_PARTIAL` | `RESOLVED_WITH_LIMITATIONS` | Candidate application, PostgreSQL, Redis, and Node manifest digests captured without pulls; application source relationship and TLS component unresolved |
| Dependency pinning | `DEPENDENCY_PINNING_PARTIAL` | `RESOLVED_WITH_LIMITATIONS` | Yarn/Node/lockfile/source/base image recorded; migration compatibility and source-build bootstrap inputs remain unproven |
| ARM64 | `ARM64_COMPATIBILITY_SUPPORTED_BY_MANIFESTS` | `RESOLVED_WITH_LIMITATIONS` | Required candidate runtime images expose ARM64 and amd64 manifests; no successful runtime is claimed |
| Private webhook | `LIVE_WEBHOOK_VALIDATION_SHOULD_BE_DEFERRED` | `RESOLVED_WITH_LIMITATIONS` | Use no webhook in M361–M364; fixture security tests are not live-delivery proof; any later public relay needs a separate exception |
| Read-only enforcement | `AUTH_MODEL_READY_WITH_LIMITATIONS` | `RESOLVED_WITH_LIMITATIONS` | Core reads can be role-constrained but share mutation surfaces; provider-enforced Metadata read-only remains unknown and must fail closed |
| Owner decision package | complete fillable template | `PENDING_OWNER_DECISION` | All required fields are blank; no authority granted |

## Technical decisions

### CI

Reliability runs on the M360 closure, M361A ending SHA, and selected base all fail
the same `ops.hardening_m13_5` test. Local reproduction returns exit code 3 from
the release secret scan. The only flagged tracked files are two pre-existing
Trading Guardian security modules outside the Twenty diff. The defect therefore
requires a separate authoritative baseline repair or formal repository-policy
waiver; this branch does not weaken the gate.

### Supply chain and architecture

The proposed prebuilt stack has public multi-architecture manifest digests for
Twenty `v2.26.0`, PostgreSQL `16.14`, and Redis `7.2.15`. Server and worker share
the Twenty image. The pinned source is newer main commit `37f1fe17...`, for which
no matching official image/source identity was proven. Both ARM64 and amd64 hosts
are manifest-eligible, so host architecture remains an owner/provider choice.

### Webhooks

Upstream requires a publicly accessible webhook URL, while SaathiOS denies public
exposure. M361–M364 can proceed without webhook delivery only after the owner
explicitly approves deferral. Offline synthetic verifier tests remain useful but
prove only contract and security behavior. M365 requires a new decision.

### Read-only authority

Future Core GETs require a dedicated expiring API key assigned to a custom
view-only role. The same API families expose mutations, so negative provider-side
tests are mandatory. Metadata reads remain blocked if the pinned runtime cannot
grant them without write capability. Client allowlists never become authority.

## Remaining blockers

- Repair or formally waive the unrelated required CI baseline failure.
- Select an application source/image identity and private TLS implementation with
  a complete immutable digest relationship.
- Obtain all blank owner fields, accountable humans, dates, cost controls, and
  plan approvals from the owner.
- Prove the selected host meets capacity and private-network requirements.
- Approve either webhook deferral or a separately bounded M365 exception.
- Later, under explicit authority, prove role denials, migrations, runtime
  behavior, backup/restore, teardown, and resource bounds.

## Non-actions and authority boundary

No runtime or container engine was installed or started. No image was pulled or
built. No host, account, trial, subscription, credential, token, secret, OAuth
client, public endpoint, or cost was created. No live Twenty connection, CRM
read/write, real data, email, webhook delivery, Trading Guardian change, Approval
Center change, Execution Gateway change, deployment, tag, release, merge, or
history rewrite occurred. `docs/autonomous/LOOP_STATE.json` remains unchanged.

```text
M361_NOT_STARTED
RUNTIME_HOST_APPROVAL_STILL_REQUIRED
```
