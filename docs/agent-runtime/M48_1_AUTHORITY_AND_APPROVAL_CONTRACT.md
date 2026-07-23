# M48.1 — Authority and Approval Contract

## Authority classes

| Class | Meaning | Default approval |
|---|---|---|
| READ_ONLY | inspect/retrieve | NO_APPROVAL_REQUIRED |
| LOCAL_MUTATION | local reversible/mutating | EXPLICIT_APPROVAL_REQUIRED |
| EXTERNAL_MUTATION | email/publish/push | EXPLICIT_APPROVAL_REQUIRED |
| FINANCIAL_ADVISORY | analysis only | EXPLICIT_APPROVAL_REQUIRED |
| FINANCIAL_EXECUTION | live money movement | **PROHIBITED** |
| ADMINISTRATIVE | deploy/admin | EXPLICIT_APPROVAL_REQUIRED |
| SECURITY_SENSITIVE | secrets/auth | EXPLICIT_APPROVAL_REQUIRED |

Maps from M10 `RiskClass` via `risk_to_authority` (never maps to FINANCIAL_EXECUTION automatically).

## Approval policies

```text
NO_APPROVAL_REQUIRED
USER_CONFIRMATION_REQUIRED
EXPLICIT_APPROVAL_REQUIRED
OWNER_AUTHORIZATION_REQUIRED
PROHIBITED
```

## Required behavior (enforced in contracts + existing runtime)

| Rule | Enforcement |
|---|---|
| unknown capability fail-closed | `validate_run_request` |
| unknown authority fail-closed | `validate_run_request` |
| expired/revoked approval fail-closed | contracts + RunStore.resolve_approval |
| UI never substitutes server auth | API auth + gateway |
| no agent self-approve planner/ceo | policy.can_self_approve |
| financial execution prohibited | contracts PROHIBITED |
| failed ≠ success | terminal states + outcome honesty |

## Risk threshold (M10)

`APPROVAL_THRESHOLD = RiskClass.LOCAL_MUTATION` — risk ≥ 2 needs explicit user approval.
