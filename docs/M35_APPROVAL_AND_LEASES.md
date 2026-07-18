# M35 — Approvals and Session Leases

## Approval envelope (`build_approval` → `ApprovalEnvelope`)

Every lease/session requires an explicit, bounded approval. Prompt authorization is
**not** runtime credential approval.

Required, fail-closed: `purpose`, `provider_id`, `account_ref_id`,
`credential_ref_id`, `operation`, `approved_scopes` (all allowed read-only classes),
`approved_duration` (>0, clamped to 900 s), `approved_uses` (>0), and **all four**
acknowledgements — `read_only_acknowledged`, `sandbox_acknowledged`,
`secret_access_acknowledged`, `non_production_acknowledged` — plus
`write_prohibited=True`. `PRODUCTION` environment fails closed.

`approval_permits(...)` re-checks provider/account/operation/scope subset and
revoked/expired status at use time.

## Session lease (`SessionLeaseStore` → `SessionLease`)

Composes M31 lease semantics and adds use-counting and session/approval binding.
The actual secret retrieval still flows through the M31 broker lease + backend.

Fields: `lease_id`, `credential_ref_id`, `account_ref_id`, `provider_id`,
`operation`, `approved_scopes`, `issued_at`, `expires_at`, `max_uses`,
`uses_remaining`, `session_id`, `approval_id`, `status`, `revocation_reason`.

Rules (test-covered):
- duration bounded, and never exceeds credential or approval expiry;
- `uses_remaining` decrements per consume; exhausted → fail closed;
- expired/revoked leases fail closed;
- provider/account/operation/session mismatch fails closed;
- scope broadening fails closed;
- no silent renewal;
- `peek()` is non-consuming (eligibility/health reads never consume a use);
- `revoke_for_credential` cascades.

Test defaults (not production policy): duration 5 min, `max_uses` 1.
