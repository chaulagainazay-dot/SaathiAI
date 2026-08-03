# Twenty runtime cost, expiry, and accountability plan

No provider, trial, purchase, subscription, currency, payer, or budget is approved.

## Provisional planning envelope

Without a selected provider, exact pricing is unknown. For owner comparison only,
reserve a non-vendor compute range of USD 0.05–0.25 per hour, USD 0.40–2.00 for an
eight-hour session, plus provider-dependent encrypted storage, snapshots, egress,
tax, and currency conversion. These figures are not quotes and cannot authorize
spend. Promotional credit does not remove billing, expiry, or deletion controls.

## Required owner fields

| Field | Current value |
| --- | --- |
| `provider_or_operator` | `PENDING_OWNER_DECISION` |
| `runtime_option` | `PENDING_OWNER_DECISION` |
| `cost_ceiling` | `PENDING_OWNER_DECISION` |
| `currency` | `PENDING_OWNER_DECISION` |
| `payment_responsibility` | `PENDING_OWNER_DECISION` |
| `start_date` | `PENDING_OWNER_DECISION` |
| `expiry_date` | `PENDING_OWNER_DECISION` |
| `maximum_runtime_hours` | `PENDING_OWNER_DECISION` |
| `shutdown_trigger` | `PENDING_OWNER_DECISION` |
| `removal_deadline` | `PENDING_OWNER_DECISION` |
| billing-alert thresholds | `PENDING_OWNER_DECISION` |
| storage/snapshot/egress allowance | `PENDING_OWNER_DECISION` |
| tax/currency uncertainty acceptance | `PENDING_OWNER_DECISION` |

Recommended controls are alerts at 50%, 75%, and 90% of the approved ceiling;
automatic shutdown at the earlier of expiry, maximum hours, abort condition, or
100% ceiling; and deletion verification by the removal deadline. The owner must
approve actual values rather than accepting these recommendations implicitly.

## Accountability roles

| Role | Responsibility | Assigned human |
| --- | --- | --- |
| `OWNER` | scope, option, budget, dates, exceptions, expansion approval | `UNASSIGNED` |
| `RUNTIME_OPERATOR` | provision, access, credential creation/revocation, shutdown, deletion | `UNASSIGNED` |
| `SECURITY_REVIEWER` | network/auth/secret review and deletion verification | `UNASSIGNED` |
| `EVIDENCE_REVIEWER` | test/evidence integrity and final verdict | `UNASSIGNED` |
| `COST_OWNER` | payment, alerts, ceiling, billing termination | `UNASSIGNED` |

No agent may assign itself to a role, accept cost, approve expansion, or waive an
abort condition.
