# Repair Planning (M62.6)

Repairs are **planned, never executed**. When reconciliation finds ERROR or
CRITICAL drift it generates a `RepairPlan` — a description of what is wrong and
what a corrective action *would* be. The engine has **no code path that applies a
repair to financial state**. Correction is a deliberate, manual, out-of-band
operator action, out of scope for this subsystem.

`test_repair_plan_generated_but_never_executed` asserts:
- plans are created for ERROR/CRITICAL findings,
- every plan reports `executes_automatically: false`,
- the injected corruption is still present after reconciliation (not repaired),
- the engine exposes no `execute_repair` / `apply_repair` method.

## RepairPlan contents

| Field | Meaning |
|---|---|
| `plan_id`, `run_id`, `account_id` | identity + link to the immutable report |
| `finding_code` | which drift finding triggered the plan |
| `root_cause` | dimension + message + expected/actual |
| `corrective_action` | the *planned* remediation (replay-based, never automatic) |
| `expected_state` | recomputed-from-events state the account should hold |
| `evidence` | references (`fills`, `ledger`, `order:<id>`, `position:<sym>`, `account:<id>`) |
| `approval_scope` | `OWNER:reconciliation.repair_authorize` |
| `status` | `PROPOSED → ACKNOWLEDGED → AUTHORIZED` (or `REJECTED`) |
| `executes_automatically` | always `false` |

Corrective actions are replay-based by construction: e.g. a `cash_mismatch` plan
says "rebuild `current_cash` by replaying immutable fills from `starting_cash`; do
NOT overwrite fills; requires operator authorization and a backup snapshot." The
`paper_fills` record is always treated as authoritative and is never a repair target.

## Lifecycle (metadata only — no financial mutation)

```text
PROPOSED       created by the engine for each ERROR/CRITICAL finding
  │  acknowledge_repair_plan()   (owner: reconciliation.repair_acknowledge)
  ▼
ACKNOWLEDGED   an owner has seen and accepted the plan
  │  authorize_repair_plan()     (owner: reconciliation.repair_authorize)
  ▼
AUTHORIZED     authorized for MANUAL correction — engine performs NO repair
```

- `authorize` requires a prior `acknowledge` (`test_authorize_requires_prior_acknowledge`).
- Authorizing does **not** change financial state — the corrupt value remains until
  a human corrects it out of band (`test_repair_plan_ack_then_authorize`).
- `reject_repair_plan()` moves a plan to `REJECTED`.

## RBAC

| Action | Required permission | Role |
|---|---|---|
| view plans | `reconciliation.read` | viewer+ |
| acknowledge / reject | `reconciliation.repair_acknowledge` | owner |
| authorize | `reconciliation.repair_authorize` | owner |

Operators can run reconciliation and read plans but **cannot** acknowledge or
authorize (`test_operator_cannot_authorize_repair`). Authorization is intentionally
gated to owners because it is the human sign-off preceding any manual correction.

## Why no automatic repair

Automatic accounting repair is a foot-gun: a wrong "fix" corrupts financial state
worse than the original drift and destroys the audit trail. By halting on CRITICAL
drift and requiring explicit human authorization for a documented, replay-based
plan, the platform stays fail-closed and fully auditable. Silent repair is a
non-goal and is not implemented anywhere in the subsystem.
