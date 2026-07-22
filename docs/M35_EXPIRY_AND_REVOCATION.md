# M35 — Expiry and Revocation

Expiry is deterministic and clock-injectable throughout (`SessionLeaseStore`,
`SandboxAccountRegistry`, `credential_health` all accept an injected clock/now).

## Revocation targets and effects

| Target | Effect |
|--------|--------|
| Credential (M31 `broker.revoke`) | new leases blocked; existing leases revoked (`revoke_for_credential`); retrieval denied |
| Account (`registry.revoke`) | `REVOKED`; re-verification blocked; sessions blocked |
| Lease (`SessionLeaseStore.revoke`) | fail-closed on consume |
| Session | secret handle closed/zeroized; session ends `REVOKED`/`ABORTED` |
| Approval | `status=REVOKED` → `approval_permits` denies |
| Provider / operation | eligibility denied via ceiling / quarantine gates |

## Guarantees

- Expired leases and revoked credentials/accounts/approvals fail closed.
- Unrelated credentials and accounts are unchanged by a revocation.
- Revocation never deletes audit evidence, never mutates production certification,
  never changes rollout, and never engages the Trading Guardian.
