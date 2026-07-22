# M39 — Operator Acknowledgements

Runtime-only. **Do not** infer from documentation or prior milestones.

| # | Token | Meaning |
|---|--------|---------|
| 1 | `I_CONFIRM_CREDENTIAL_IS_DISPOSABLE` | Credential is disposable |
| 2 | `I_CONFIRM_SANDBOX_ACCOUNT_WHERE_POSSIBLE` | Sandbox account preferred |
| 3 | `I_CONFIRM_MINIMUM_READ_ONLY_PERMISSIONS` | Minimum read-only scopes |
| 4 | `I_CONFIRM_NO_REPOSITORY_WRITE_PERMISSION` | No repo write |
| 5 | `I_CONFIRM_NO_ORG_ADMIN_PERMISSION` | No org admin |
| 6 | `I_CONFIRM_NO_BILLING_PERMISSION` | No billing |
| 7 | `I_CONFIRM_NO_PACKAGE_DEPLOY_WORKFLOW_SECRET_WRITE` | No package/deploy/workflow/secret write |
| 8 | `I_CONFIRM_REVOKE_IMMEDIATELY_AFTER_VALIDATION` | Will revoke after validation |
| 9 | `I_CONFIRM_READINESS_IS_NOT_AUTHORIZATION` | Readiness ≠ authorization |
| 10 | `I_CONFIRM_NO_PRODUCTION_ROLLOUT_CANARY_ACTIVE_WRITE` | No prod/rollout/canary/active/write granted |

Missing any token → fail closed (`missing_acknowledgement`).

Pass via repeated `--ack TOKEN` on CLI. M36 ack set is also required when
creating composed authorization records for M36 store compatibility.
