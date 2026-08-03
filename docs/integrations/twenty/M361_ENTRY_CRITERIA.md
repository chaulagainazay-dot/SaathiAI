# M361 entry criteria and abort controls

M361 may start only when every mandatory entry row is `PASS`. A recommendation,
document, or owner acceptance of M360 is not runtime-host approval.

## Entry matrix

| Entry criterion | State | Evidence or missing decision |
| --- | --- | --- |
| Owner acceptance of M360 | `PASS` | M360 owner decision for reviewed SHA `a0e4fa5` |
| Runtime option selected | `PENDING_OWNER_DECISION` | private temporary host is recommended, not selected |
| Runtime-host approval granted | `PENDING_OWNER_DECISION` | explicitly not granted |
| Operator assigned | `PENDING_OWNER_DECISION` | human `RUNTIME_OPERATOR` unassigned |
| Cost ceiling assigned | `PENDING_OWNER_DECISION` | value/currency absent |
| Payment responsibility assigned | `PENDING_OWNER_DECISION` | `COST_OWNER` unassigned |
| Start date assigned | `PENDING_OWNER_DECISION` | absent |
| Expiry date assigned | `PENDING_OWNER_DECISION` | absent |
| Removal deadline assigned | `PENDING_OWNER_DECISION` | absent |
| Source commit pinned | `PASS` | clean SHA `37f1fe17ab48269384cffb774f82f096abe3863a` |
| Image digest pinned | `FAIL` | Twenty/PostgreSQL/Redis immutable digest set absent |
| Synthetic-data manifest complete | `PASS` | `SYNTHETIC_DATA_MANIFEST.md` |
| Network policy approved | `PENDING_OWNER_DECISION` | design exists; host-specific rules unapproved |
| Authentication model approved | `PENDING_OWNER_DECISION` | design exists; endpoint enforcement unproven |
| Backup plan approved | `PENDING_OWNER_DECISION` | design exists; provider/operator absent |
| Removal plan approved | `PENDING_OWNER_DECISION` | deadline/operator absent |
| Abort conditions approved | `PENDING_OWNER_DECISION` | catalogue exists; roles/thresholds unapproved |
| Private host meets baseline | `UNKNOWN` | no host selected or measured |
| SaathiOS authority systems unchanged | `PASS` | readiness work is documentation/evidence only |
| PR and branch state understood | `PASS` | branch published; PR #15 only and Draft |
| Relevant CI status acceptable | `FAIL` | required reliability run failed in classified unrelated ops baseline |

Current decision: `M361_ENTRY_NOT_READY`.

## Abort controls

| Abort condition | Detection | Immediate action | Evidence | Responsible role | Recovery requirement |
| --- | --- | --- | --- | --- | --- |
| `PUBLIC_EXPOSURE_DETECTED` | firewall/port/DNS inventory | block ingress and stop runtime | rules, sockets, DNS snapshot | `SECURITY_REVIEWER` | private-only controls re-reviewed |
| `FORBIDDEN_EGRESS_DETECTED` | egress/DNS logs | isolate network | destination/time/process | `SECURITY_REVIEWER` | explicit denial and cause fixed |
| `REAL_DATA_DETECTED` | provenance/schema scan | stop tests and quarantine data | redacted detection record | `EVIDENCE_REVIEWER` | deletion verified; synthetic reset |
| `SECRET_LEAKAGE_DETECTED` | secret scan/log review | revoke, isolate, redact | fingerprint and affected locations | `SECURITY_REVIEWER` | rotate and rescan clean |
| `UNEXPECTED_WRITE_DETECTED` | denied-mutation probes/audit | revoke key and stop adapter | request fingerprint and runtime audit | `RUNTIME_OPERATOR` | technically enforced denial proven |
| `CROSS_TENANT_ACCESS_DETECTED` | tenant-canary queries | revoke and isolate | canary IDs and redacted response | `SECURITY_REVIEWER` | isolation defect resolved and retested |
| `DIRECT_WEBHOOK_EXECUTION_DETECTED` | observation/mission audit | disable webhook route | event ID and execution trace | `SECURITY_REVIEWER` | observation-only invariant restored |
| `IMAGE_DIGEST_MISMATCH` | resolved-manifest comparison | refuse startup | expected/actual digest | `RUNTIME_OPERATOR` | approved digest restored |
| `UNPINNED_DEPENDENCY_DETECTED` | manifest/lock/config scan | refuse build/start | dependency inventory | `SECURITY_REVIEWER` | immutable dependency set approved |
| `RESOURCE_PRESSURE_EXCEEDED` | CPU/RAM/swap samples | stop load, then runtime | metric series | `RUNTIME_OPERATOR` | capacity or scope re-approved |
| `DISK_RESERVE_EXCEEDED` | free-space alert | stop writes/backups | disk samples | `RUNTIME_OPERATOR` | at least 15 GB reserve restored |
| `UNCLEAR_BILLING` | billing/API discrepancy | stop billable resources | invoice/console snapshot | `COST_OWNER` | costs reconciled and re-approved |
| `COST_CEILING_EXCEEDED` | budget alert | immediate shutdown | alert and billing status | `COST_OWNER` | new explicit approval or deletion |
| `APPROVAL_EXPIRED` | clock vs approval expiry | revoke access and stop | approval/time record | `OWNER` | new approval required |
| `OPERATOR_UNAVAILABLE` | missed handoff/response | do not start; safe shutdown if running | handoff log | `OWNER` | replacement human assigned |
| `REMOVAL_PLAN_INCOMPLETE` | preflight checklist | refuse provisioning | missing-field report | `EVIDENCE_REVIEWER` | executable plan approved |
| `SCOPE_EXPANSION_REQUESTED` | diff/request review | pause milestone | request and proposed delta | `OWNER` | separate bounded approval |
| `AUTH_SCOPE_TOO_BROAD` | role export and negative tests | revoke key | role/permission snapshot | `SECURITY_REVIEWER` | least-privilege role proven |
| `RUNTIME_STATE_UNRECOVERABLE` | failed health/restart/restore | isolate and preserve logs | health/restore evidence | `RUNTIME_OPERATOR` | delete/recreate only under approval |

Every abort captures redacted evidence before cleanup when safe, but evidence
collection must never prolong public exposure, cost overrun, secret leakage, or
real-data retention.

## Exact unresolved owner package

The owner must approve or assign:

```text
provider_or_operator
runtime_option
cost_ceiling
currency
payment_responsibility
start_date
expiry_date
maximum_runtime_hours
shutdown_trigger
removal_deadline
data_restrictions
network_restrictions
RUNTIME_OPERATOR
SECURITY_REVIEWER
EVIDENCE_REVIEWER
COST_OWNER
image_and_dependency_digest_manifest
authentication_role_and_expiry
backup_retention_and_location
abort_conditions
```

Additionally, the required CI failure and private-webhook feasibility must be
resolved or bounded before their affected phases can pass entry.
