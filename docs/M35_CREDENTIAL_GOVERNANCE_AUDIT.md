# M35 — Credential Governance Audit (pre-implementation)

**Milestone:** M35 — Governed Sandbox Credentials, Least-Privilege Account Linking, Read-Only Session Certification
**Branch:** `milestone/m7-security-engine`
**Starting HEAD:** `ff1022d1dd62da1f0b13a3c8c35f84f8276c0456` (M34 tip)
**Preflight:** branch correct · divergence `0/0` · `git diff --check` clean · worktree clean except known `docs/evidence/m25/` timestamp noise (unstaged, left untouched)

M35 **extends** the M31 credential architecture and composes it with M32–M34 provider
verification. It does **not** replace M31 and does **not** create a parallel secret,
account, approval, lease, or audit system.

---

## 1. Reusable M31 components (reuse as-is)

| Component | Location | Reused for |
|-----------|----------|-----------|
| `CredentialReference`, `CredentialType`, `CredentialStatus`, `StorageBackendKind`, `SecretLease`, `LeaseStatus`, `AuthProfile`, `FORBIDDEN_SECRET_FIELD_NAMES`, `is_prohibited_provider/scope` | `saathi/credentials/models.py` | credential-reference model, forbidden-field enforcement |
| `SecretBackend` ABC, `InMemoryTestSecretBackend`, `EnvironmentReferenceBackend`, `EncryptedLocalTestBackend`, `UnavailableSecureBackend`, `create_backend`, `APPROVED_BACKENDS` | `saathi/credentials/backends.py` | secret-source abstraction (only `in_memory_test` fully exercised) |
| `LeaseStore`, `request_fingerprint`, TTL clamps | `saathi/credentials/lease.py` | lease issuance / consume / expiry / revoke |
| `validate_requested_scopes`, `validate_granted_scopes`, `check_operation_authorized`, `ScopeDecision`, profile catalog | `saathi/credentials/scopes.py` | least-privilege scope base layer |
| `CredentialBroker` (create_reference, issue_lease, inject_secrets, rotate, revoke, quarantine, mark_expired, delete) | `saathi/credentials/broker.py` | credential control plane, events, incidents |
| `AccountLinkRegistry` | `saathi/credentials/account_links.py` | account-link governance baseline |
| `combined_connector_eligibility` | `saathi/credentials/eligibility.py` | eligibility composition base |
| `scan`, `is_clean`, `assert_clean`, `LeakDetected` | `saathi/credentials/leakscan.py` | leak-safe evidence/events |
| `write_evidence` (atomic, leak-scanned, repo-relative) | `saathi/connectors/providers/evidence.py` | deterministic evidence writer (as in M32–M34) |
| `GITHUB_META` profile (get_meta / GET / READ_ONLY / PUBLIC / environment=sandbox) | `saathi/connectors/providers/external/profiles.py` | provider capability ceiling |

## 2. Gaps M35 must add (bounded extensions, no duplication)

| # | Capability | Gap vs M31 | Extension |
|---|-----------|-----------|-----------|
| 1 | Strict environment classification | M31 `environment` is a free string | `EnvironmentClass` enum {SYNTHETIC, LOCAL_TEST, SANDBOX, PRODUCTION}; `PRODUCTION` fails closed |
| 2 | Secret-source policy | M31 has backends but no source-type policy | `SecretSourceKind` + policy: only `IN_MEMORY_TEST` retrievable; others structural-only; reject PLAINTEXT/REPOSITORY_FILE/COMMAND_LINE/LOG/EVIDENCE/CALLER_RAW; no fallback |
| 3 | Secret handle boundary | M31 returns a dict of secrets | `SecretHandle` — non-printable, non-serializable, zeroizing, use-after-close reject, session/lease/provider/account-bound |
| 4 | Secret-material fingerprint | M31 `compute_fingerprint` hashes metadata only | `m35_secret_fingerprint` — domain-separated keyed digest over secret bytes + provider + account; absent when no secret; no length/prefix/suffix leak; cannot authenticate |
| 5 | Scope classes | M31 has prohibited-scope substrings | `M35ScopeClass` allow-list {IDENTITY_READ, METADATA_READ, PUBLIC_DATA_READ, SANDBOX_RESOURCE_READ}; forbidden classes; UNKNOWN fail-closed; `ScopeVerificationState` {DECLARED, OBSERVED, VERIFIED, MISMATCHED, UNKNOWN} |
| 6 | Capability ceiling | none | `CapabilityCeiling` from provider profile ∩ credential ∩ account ∩ operator; subset check blocks broadening/substitution |
| 7 | Sandbox account registry | M31 `AccountLink` is OAuth-link-centric | `SandboxAccount` record (subject fingerprint, verified_scopes, capability_ceiling, verification_state, drift_state) + registry |
| 8 | Approval envelope | none | `ApprovalEnvelope` — explicit, provider/account/operation/scope/time/use-bounded acks |
| 9 | Session lease | M31 `SecretLease` lacks uses/session/approval binding | `SessionLease` extends lease with approved_scopes, max_uses, uses_remaining, session_id, approval_id |
| 10 | Read-only session | none | `ReadOnlySession` lifecycle REQUESTED→…→COMPLETED; offline only |
| 11 | Rotation w/ mismatch detection | M31 `broker.rotate` exists | wrap with same-secret / provider / account / env / scope / expiry checks |
| 12 | Credential & account drift | M34 drift pattern | `m35_drift` inputs → {FRESH, STALE, MISMATCHED, REVOKED, UNKNOWN} |
| 13 | Credential health | none | metadata-only `CredentialHealth` states; no secret read, no lease consume |
| 14 | Sandbox-session certification | none | states, max `SANDBOX_GOVERNANCE_VERIFIED` without a real credential/account |
| 15 | Composed eligibility | M31 `combined_connector_eligibility` | extend to include credential/account/scope/ceiling/health/lease/approval/session/provider/rollout |

## 3. Duplicate-architecture risks and how they are avoided

- **No new secret store** — all secret material flows through the M31 `CredentialBroker` + `SecretBackend`. `SecretHandle` wraps the broker's existing `inject_secrets` output; it does not fetch secrets itself.
- **No new lease system** — `SessionLease` is a thin metadata wrapper composing the M31 `LeaseStore`; expiry/revocation reuse `LeaseStore`.
- **No new audit ledger** — events/incidents reuse the broker's `_emit`/`_incident` shape and `m31.*_event.v1` schema family; evidence uses M32 `write_evidence`.
- **No new CLI package** — extends `saathi/credentials/cli.py` (`python -m saathi.credentials`), not a new `saathi.connectors.credentials` package.
- **No second provider** — the only ceiling source is the existing `github_meta` profile.

## 4. Extension points (exact)

- New surface module: `saathi/credentials/m35.py` (single cohesive milestone module, mirroring the M34 `m34.py` precedent). Holds env classes, secret-source policy, secret handle, m35 fingerprint, scope classes, capability ceiling, sandbox account registry, approvals, session leases, read-only session lifecycle, rotation guard, drift, health, certification, eligibility composition, events, evidence writer.
- CLI: add `register-reference`, `verify-reference`, `credential-health`, `credential-drift`, `register-sandbox-account`, `verify-account`, `account-drift`, `authorize-session`, `simulate-session`, `session-status`, `revoke-session`, `m35-verify`, `m35-drift`, `emit-m35-evidence` to `saathi/credentials/cli.py`. No raw secret accepted as any positional/flag.
- Evidence generator: `scripts/m35_generate_evidence.py` — offline, synthetic fixtures only, deterministic, leak-scanned, repo-relative.

## 5. Prohibited shortcuts

No production environment class; no real secret source retrieval (only in-memory synthetic); no Keychain access in tests; no arbitrary env reads; no network; no second provider; no account connect; no write-capable session; no secret bytes in evidence/ledger/logs/git; no `SANDBOX_SESSION_CERTIFIED` claim; no CANARY/ACTIVE; no Trading Guardian.

## 6. Planned test files

```
tests/test_m35_credential_security.py       (references, secret sources, secret handle, fingerprint, scope, ceiling)
tests/test_m35_credential_lifecycle.py       (approvals, leases, expiry, revocation, rotation, drift, health)
tests/test_m35_sandbox_sessions.py           (session lifecycle, eligibility composition, revocation cascade)
tests/test_m35_certification_and_evidence.py (certification states, evidence determinism, leak scan, repo invariants)
```
Target ≈180 focused tests; coverage prioritized over count.

## 7. Planned evidence files (`docs/evidence/m35/`)

`baseline.json`, `credential_reference_schema.json`, `secret_source_policy.json`,
`sandbox_account_registry.json`, `scope_policy.json`, `capability_ceiling.json`,
`approval_envelope.json`, `lease_lifecycle.json`, `session_lifecycle.json`,
`secret_handle_security.json`, `expiry_and_revocation.json`, `rotation.json`,
`credential_drift.json`, `account_drift.json`, `credential_health.json`,
`eligibility_composition.json`, `synthetic_session_result.json`,
`sandbox_certification.json`, `events.json`, `leak_scan.json`,
`validation_summary.json`, `verification_fingerprint.json`.

## 8. Decision

Proceed with M35 as a bounded extension of M31 in one new surface module plus CLI/evidence/tests/docs. Do not begin M36.
