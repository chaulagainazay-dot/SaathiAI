# M46 — Operator Guide

Bounded **read-only disposable canary** controller. Success grants **nothing**:
no production, deployment, write, trading, autonomous execution, or rollout expansion.

## Security invariants (summary)

| Rule | Requirement |
|------|-------------|
| Endpoint (Model A) | `IDENTITY_READ` ⇒ `allowed_endpoint` **exactly** `user`; live request **`GET /user`** |
| Call ceiling | **1** provider network call; retries and fallback endpoints forbidden |
| Secrets | Only `OS_KEYCHAIN_REFERENCE` (or approved reference kinds); never raw PAT on CLI |
| Replay | Durable consume ledger: `ATTEMPTED` before provider, `CONSUMED_SUCCESS` / `ATTEMPTED_FAILED` after |
| Revocation cleanup | Keychain delete **only** after conclusive **HTTP 401** |
| Evidence | `live_canary_occurred: true` **or** policy schema v1/v2 success fields; **absent ≠ true** |

## States (operator-facing)

| State | Meaning |
|-------|---------|
| `M46_FRESH_POLICY_CANARY_VALIDATED_PENDING_EXTERNAL_REVOCATION` | Policy canary succeeded; revoke disposable PAT next |
| `M46_FRESH_CREDENTIAL_IDENTIFIED_AWAITING_CORRECT_REVOCATION` | Local classification of Keychain secret family (e.g. fine-grained PAT) |
| `M46_FRESH_REVOCATION_NOT_EFFECTIVE` | Verification still HTTP 200 / not 401; **do not** delete Keychain |
| `M46_LIFECYCLE_CLOSED_POLICY_CONFORMANT` | 401 proven + exact Keychain item deleted; **still grants nothing** |
| `M46_ENDPOINT_BINDING_EXCEPTION` | Historical canary (meta vs `/user`); not certification for policy path |
| `M46_REPOSITORY_REPAIRS_COMPLETE_AWAITING_CORRECT_FG_PAT_REVOCATION` | Code/docs fixed; operator must revoke fine-grained PAT then re-verify |

## CLI

```bash
python -m saathi.credentials.cli m46-status
python -m saathi.credentials.cli m46-simulate
python -m saathi.credentials.cli m46-validate-approval --approval-file docs/m46/....local.json
python -m saathi.credentials.cli m46-create-plan --approval-file ... --request-file ... --snapshot-file ...
python -m saathi.credentials.cli m46-preflight --approval-file ... --request-file ... --snapshot-file ...
python -m saathi.credentials.cli m46-run-canary --mode simulate
```

### Live canary (one-shot)

```bash
export SAATHI_M46_LIVE_GATE=1
python -m saathi.credentials.cli m46-run-canary --mode live --live-flag \
  --approval-file docs/m46/operator_canary_approval_policy.local.json \
  --request-file docs/m46/m44_rollout_request_policy.local.json \
  --snapshot-file docs/m46/m45_runtime_snapshot_policy.local.json \
  --secret-source-kind OS_KEYCHAIN_REFERENCE \
  --secret-locator $'saathi_m46_final\x1fgithub_meta' \
  --expected-subject-fp c7cd7f4d6bee55c2847614692022af73
unset SAATHI_M46_LIVE_GATE
```

### Revocation verification + conditional cleanup

Evidence file must pass `validate_live_canary_evidence` (explicit `live_canary_occurred: true`
**or** policy schema with complete success fields). Prefer **v2** evidence that always
includes `live_canary_occurred: true`.

```bash
export SAATHI_M46_LIVE_GATE=1
python -m saathi.credentials.cli m46-run-revocation \
  --mode live --live-flag \
  --secret-source-kind OS_KEYCHAIN_REFERENCE \
  --secret-locator $'saathi_m46_final\x1fgithub_meta' \
  --live-canary-evidence-file docs/m46/fresh_policy_canary_result.local.json \
  --cleanup-after-401
unset SAATHI_M46_LIVE_GATE
```

- **One** provider request maximum.
- `--cleanup-after-401` deletes Keychain **only** if HTTP 401 confirmed; **no second GitHub call**.
- HTTP 200 / IDENTITY_OK ⇒ **no delete**.

## Credential types

| Family | Where to revoke |
|--------|-----------------|
| Fine-grained PAT | Settings → Developer settings → Personal access tokens → **Fine-grained tokens** |
| Classic PAT | … → **Tokens (classic)** |
| OAuth / App token | Settings → Applications → Authorized OAuth / GitHub Apps |

Local classification may identify family **without** printing the secret. Never paste PATs into chat.

## Operator lifecycle (policy-conformant)

1. Provision disposable **fine-grained** (or other) **read-only** PAT; store only in Keychain (new service name per canary).
2. Fresh approval: `allowed_endpoint=user`, `IDENTITY_READ`, max_calls=1, subject FP bound, short expiry; `sign_approval`.
3. Fresh M45 snapshot + M44 request + M46 plan; preflight must pass.
4. One live canary → durable `ATTEMPTED` then `CONSUMED_SUCCESS`.
5. Operator revokes PAT in GitHub UI (correct list).
6. One `m46-run-revocation` with evidence file; expect **401** then optional cleanup.
7. Stop at lifecycle closed for **credential path only** — still no production authority.

## Prohibited

- Reusing consumed approvals/plans
- Replacing Keychain value with a “known-revoked” token to fake 401
- Treating historical meta/`/user` canary as policy certification
- Force-push, deploy, production activation, trading, weakening M32

## Local paths (gitignored)

- `docs/m46/*.local.json` — approvals, snapshots, evidence
- `docs/evidence/m46/consumed_authorization.local.jsonl` — durable one-shot ledger

Do not commit these files.
