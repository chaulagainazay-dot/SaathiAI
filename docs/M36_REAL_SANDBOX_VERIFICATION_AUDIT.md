# M36 — Real Sandbox Verification Audit

**Milestone:** M36 — Operator-Controlled Real Sandbox Credential Verification  
**Branch:** `milestone/m7-security-engine`  
**Starting HEAD:** `233faa578a1b33fe2ede5f69f16c0801d8db4b3d` (M35 tip)  
**Date (UTC):** 2026-07-18  
**Status:** Audit complete before implementation and before any real secret retrieval or network call.

---

## 1. Mission

Prove that the M31–M35 credential, account, lease, scope, session, transport, and
evidence controls work with **one** real disposable sandbox identity on a
**bounded, operator-authorized, read-only** path — without granting rollout,
CANARY, ACTIVE, write, production, financial, or trading authority.

---

## 2. Components reused (no parallel systems)

| Layer | Exact components |
|-------|------------------|
| **M31** | `CredentialBroker`, `SecretBackend` contract, `LeaseStore` / broker leases, `scopes`, `leakscan`, `injection`, `eligibility`, `models` (`CredentialReference`, statuses) |
| **M32** | Provider adapter capability ceilings, quarantine store patterns, `write_evidence` |
| **M33** | `github_meta` profile (`saathi/connectors/providers/external/profiles.py`), `ExternalTransport`, DNS/SSRF, TLS policy, endpoint policy, request/response envelopes, schema contracts |
| **M34** | Call-budget semantics (max 3), reliability classification patterns, live env-flag pattern, latency/size buckets, non-production banners |
| **M35** | `SecretHandle`, sandbox account registry, scope classes, capability ceilings, approval envelopes, session leases, synthetic session lifecycle, certification cap, fingerprint helpers, secret-source structural validation |

**No parallel** credential broker, secret store, lease system, account registry,
approval system, session system, transport path, provider adapter, audit ledger,
or certification system is introduced. M36 is a **composition + live-session
coordinator** layered on these surfaces.

---

## 3. Approved provider and operations

| Field | Value |
|-------|--------|
| Provider | `github_meta` (sole M33 external provider) |
| Host | `api.github.com` (allowlist only) |
| Primary public operation | `get_meta` · `GET` · `/meta` · `side_effect_class=READ_ONLY` · `data_classification=PUBLIC` · `auth_profile=none` |
| Identity operation (M36 extension) | `get_authenticated_user` · `GET` · `/user` · same host allowlist · read-only · INTERNAL classification for response handling |

### Authentication reality

- **`GET /meta` does not require authentication.** Loading a credential solely to
  call `/meta` would not prove authenticated sandbox identity.
- **`GET /user` requires a valid token** and returns account identity; GitHub also
  exposes `X-OAuth-Scopes` / `X-Accepted-OAuth-Scopes` response headers for scope
  observation.
- M36 therefore splits:
  1. **Authenticated credential/session governance** → call 1: `GET /user` with
     Authorization injected only at the transport sender boundary (never stored
     on the envelope, never logged, never written to evidence).
  2. **Approved provider operation** → call 2: `GET /meta` through the same
     canonical transport (optional Authorization; not required by the endpoint).

The M33 registered profile for `get_meta` is **not rewritten**. Identity is a
**same-host, same-provider operation binding** defined in M36 and built via
`dataclasses.replace` on the approved profile (hostname allowlist, ports, TLS,
redirect, response ceilings preserved). No second provider is added.

---

## 4. Secret-source design

| Kind | M35 | M36 |
|------|-----|-----|
| `IN_MEMORY_TEST` | Retrievable offline | Used for offline tests only |
| `OS_KEYCHAIN_REFERENCE` | Structural only | Retrievable **only** under valid M36 auth + lease + session; injectable backend; never in unit tests |
| `ENV_REFERENCE` | Structural only | Retrievable **only** for **pre-declared** env var names under M36 auth; no env scanning |
| `ENCRYPTED_STORE_REFERENCE` | Structural only | Structural / DI only unless operator-approved backend injected |
| Plaintext / CLI / repo file | Prohibited | Prohibited |

CLI accepts **secret references / locators only**. Flags `--token`, `--api-key`,
`--password`, `--secret`, `--authorization-header` are rejected.

Preferred macOS path: OS Keychain reference (placeholder service name only in docs).

---

## 5. Call budget

```text
total calls = 3 (hard max; fourth fails closed)
call 1 = authenticated identity (GET /user)
call 2 = approved operation (GET /meta)
call 3 = optional deterministic repeatability / bounded retry
```

Retries, redirects (as new requests), and auth retries consume budget.
No hidden telemetry, SDK discovery, pagination, OAuth refresh, silent retry, or
alternate-host fallback.

---

## 6. Operator acknowledgement gate (runtime)

All required, non-default, session-specific, time-bounded:

```text
I_CONFIRM_DISPOSABLE_SANDBOX_ACCOUNT
I_CONFIRM_READ_ONLY_SCOPE
I_CONFIRM_NO_PRODUCTION_DATA
I_CONFIRM_SECRET_REFERENCE_ONLY
I_CONFIRM_CALL_BUDGET
I_CONFIRM_NO_WRITES
I_CONFIRM_REVOCATION_PLAN
I_CONFIRM_ROLLOUT_REMAINS_OFF
```

Plus env flag `SAATHI_M36_ALLOW_LIVE_SANDBOX_VERIFICATION=1` (insufficient alone).
Prompt authorization alone is insufficient.

---

## 7. Revocation plan

Preferred:

1. Local lease revoked or expired after session.
2. Secret handle closed and zeroized.
3. External disposable token revoked **manually** by operator (GitHub → Settings →
   Developer settings → Personal access tokens → Delete).
4. Disposition recorded: `LEASE_REVOKED` + `EXTERNAL_REVOCATION_OPERATOR_ATTESTED`
   (or `CREDENTIAL_REVOKED_EXTERNALLY` when attested).

No provider write is performed solely to revoke unless separately authorized.
Silent active credentials after session completion fail certification.

---

## 8. Evidence plan

```text
docs/evidence/m36/
  offline deterministic evidence (scripts/m36_generate_evidence.py --offline)
  live sanitized evidence (only if operator-run session succeeds)
```

Leak-scanned; no secrets, raw identity, Authorization headers, or raw bodies.

---

## 9. Test plan

Focused offline suites:

- `tests/test_m36_authorization_and_security.py`
- `tests/test_m36_real_session_lifecycle.py`
- `tests/test_m36_transport_and_scope.py`
- `tests/test_m36_certification_and_evidence.py`

Then M31–M35 regressions, leak scan, critical/release/runtime gates, full suite.
Live path is operator-only and skipped when no disposable credential reference
is available.

---

## 10. Why no second provider

- Repository has exactly one approved external provider: `github_meta`.
- Same host supports both identity (`/user`) and public metadata (`/meta`).
- Adding a second provider would broaden the provider universe without
  repository-backed authorization.

---

## 11. Duplicate-architecture risks (mitigated)

| Risk | Mitigation |
|------|------------|
| Parallel secret store | Only M31 backends + optional Keychain DI |
| Parallel lease system | M35 `SessionLeaseStore` + M31 broker leases |
| Parallel transport | `ExternalTransport` only; auth via sender wrapper |
| Parallel account registry | M35 `SandboxAccountRegistry` |
| General rollout bypass | Milestone/provider/account/operation/lease/session-bound M36 exception |

---

## 12. Live-verification blockers (pre-implementation)

| Blocker | Status |
|---------|--------|
| Disposable sandbox PAT in Keychain | **Operator-supplied; may be absent** |
| Operator runtime acknowledgements | Required at run-session |
| Live env flag | Required at run-session |
| Offline tests green | Required before live |
| Manual external revocation plan | Documented; operator-attested |

If no suitable disposable sandbox credential is available after implementation and
offline validation, M36 ends with:

```text
M36 IMPLEMENTATION COMPLETE — REAL SANDBOX SESSION NOT EXERCISED
```

with the exact blocker recorded.

---

## 13. Invariants (must hold)

```text
production credentials = 0
production accounts = 0
production OAuth = 0
external writes = 0
financial/trading calls = 0
connector/provider/inference rollout = OFF
CANARY = 0, ACTIVE = 0
Trading Guardian = UNCHANGED / UNENGAGED
M37 = NOT STARTED
docs/evidence/m27/ = untouched
```

---

## 14. Audit conclusion

M36 is **authorized to implement** as a composition layer on M31–M35 and the
M33/M34 transport. Real secret retrieval and network calls remain **blocked**
until offline tests pass and the operator supplies acknowledgements + live flag +
a disposable sandbox secret reference.
