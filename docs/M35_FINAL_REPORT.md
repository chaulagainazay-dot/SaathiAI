# M35 — Final Report

## 1. Executive result

> **M35 IMPLEMENTATION COMPLETE — REAL SANDBOX CREDENTIAL VERIFICATION NOT EXERCISED**

M35 builds and certifies a governed sandbox credential and read-only session
lifecycle as a bounded extension of the M31 credential architecture, composed with
the M32–M34 provider-verification framework. All governance is proven **offline and
deterministically** with synthetic fixtures. No real secret source, no real sandbox
account, no OAuth, no live provider call, no write, no rollout change.

- credential governance = `SANDBOX_GOVERNANCE_VERIFIED`
- synthetic session = `VERIFIED`
- real sandbox session = **NOT EXERCISED**

## 2. Baseline and tip

| Item | Value |
|------|-------|
| Starting HEAD | `ff1022d1dd62da1f0b13a3c8c35f84f8276c0456` (M34 tip) |
| Ending HEAD | `docs(m35)` commit (this document's commit) on `milestone/m7-security-engine` |
| Branch | `milestone/m7-security-engine` |
| Worktree | clean except known `docs/evidence/m25/` timestamp noise (unstaged) |
| Remote divergence | `0 0` after push |
| `docs/evidence/m27/` | untouched and unstaged |

## 3. Architecture reused

Extends M31 (`saathi/credentials/`): `CredentialBroker` (create/lease/inject/rotate/
revoke/quarantine), `LeaseStore`, scope governance, `SecretBackend` family,
`AccountLinkRegistry`, `leakscan`, and the M32 `write_evidence` writer. The M33
`github_meta` external profile supplies the capability ceiling. One new surface
module — `saathi/credentials/m35.py` — holds the M35 governance; no parallel secret,
lease, account, or audit system was created.

## 4. Credential-reference model

- Environment classes: `SYNTHETIC`, `LOCAL_TEST`, `SANDBOX` permitted; `PRODUCTION`
  fails closed.
- Secret sources: `IN_MEMORY_TEST` retrievable; `ENV_REFERENCE`,
  `OS_KEYCHAIN_REFERENCE`, `ENCRYPTED_STORE_REFERENCE`,
  `EXTERNAL_SECRET_MANAGER_REFERENCE` structural-only; `PLAINTEXT`,
  `REPOSITORY_FILE`, `COMMAND_LINE_VALUE`, `LOG_EMBEDDED`, `EVIDENCE_EMBEDDED`,
  `CALLER_RAW_SECRET` prohibited; no fallback.
- Fingerprinting: non-reversible, domain-separated HMAC, provider/account-bound,
  fixed-width, empty when no secret, cannot authenticate.
- Secret storage: only in the M31 backend; references hold field names only.

## 5. Sandbox accounts

Metadata-only registry; subject stored only as a non-reversible fingerprint; raw
email/phone and password/token/billing/financial fields rejected; production
accounts fail closed; verification (`VERIFIED`/`SYNTHETIC_VERIFIED`/`MISMATCHED`/
`FAILED`), drift, and revocation supported.

## 6. Scope and capability ceilings

Allowed read-only classes: `IDENTITY_READ`, `METADATA_READ`, `PUBLIC_DATA_READ`,
`SANDBOX_RESOURCE_READ`. 17 forbidden classes; unknown scopes fail closed.
Capability ceiling from provider profile ∩ credential ∩ account ∩ approval ∩
connector; provider/operation/method/scope/data/side-effect/environment broadening
all fail closed.

## 7. Approvals and leases

Explicit approval envelope (provider/account/operation/scope/time/use-bounded, four
acknowledgements + write-prohibited required). Session leases: bounded duration
(≤ credential/approval expiry), counted uses, session/approval binding, no silent
renewal; eligibility/health reads never consume a use.

## 8. Secret-handle security

Non-printable, non-serializable (json/pickle blocked), zeroized on close,
use-after-close rejected, session/lease/provider/account bound, identity-only
equality. The raw value is exposed only through a session-guarded consumer callable.

## 9. Session lifecycle

`authorize → verify account → verify scope → issue lease → retrieve secret → derive
fingerprint → compose eligibility → bounded session → release secret → consume lease
→ end → evidence`. Offline; no network, no write. Secret handle always released.

## 10. Rotation, health, and drift

Rotation guard detects same-secret reuse / provider / account / environment / scope
broadening / expired / invalid replacement; old leases invalidated. Health is
metadata-only (11 states). Drift over provider/env/type/source/scope/ceiling/
account/policy inputs → `FRESH`/`STALE`/`MISMATCHED`/`REVOKED`/`UNKNOWN`.

## 11. Certification

```
sandbox_certification = SANDBOX_GOVERNANCE_VERIFIED   (max permitted offline)
real sandbox credential verification = NOT EXERCISED
real sandbox account link            = NOT EXERCISED
live provider session                = NOT EXERCISED
```
`SANDBOX_SESSION_CERTIFIED` is never claimed (capped defensively).

## 12. Evidence and leak scanning

`docs/evidence/m35/` — 22 deterministic, leak-scanned, repository-relative JSON
files (regeneration is byte-identical). M35 verification fingerprint:
`2514ded3413d48bf26156b4ddc3e1e2e7cb9e44da51a20970f7fabd6b0bb3d17`. Leak scan of
evidence, code, tests, and docs: **0 findings** — no secrets, no personal data, no
absolute paths, no real token shapes. Network calls performed: **0**.

## 13. Security invariants

```
production_certified = true
connector certifications / M32 sim / M33 profile / M34 governance = fresh
connector/provider/inference rollout = OFF
CANARY / ACTIVE providers = 0 / 0
connector/provider-adapter/direct-provider/direct-network bypasses = 0
production credentials / OAuth / account links = 0 / 0 / 0
real sandbox credentials / OAuth / account links = 0 / 0 / 0
external network calls / provider writes = 0 / 0
financial / trading provider calls = 0 / 0
raw secrets committed / in evidence / in logs / in events = 0
Trading Guardian = UNCHANGED / UNENGAGED
```

## 14. Files changed

| File | Purpose |
|------|---------|
| `saathi/credentials/m35.py` | M35 sandbox-credential governance surface (new) |
| `saathi/credentials/cli.py` | M35 CLI subcommands (extended) |
| `scripts/m35_generate_evidence.py` | deterministic offline evidence generator (new) |
| `tests/test_m35_credential_security.py` | 99 tests (new) |
| `tests/test_m35_credential_lifecycle.py` | 67 tests (new) |
| `tests/test_m35_sandbox_sessions.py` | 44 tests (new) |
| `tests/test_m35_certification_and_evidence.py` | 17 tests (new) |
| `docs/M35_*.md` | audit, reference, policies, lifecycle, ops, validation, report (new) |
| `docs/evidence/m35/*.json` | 22 evidence files (new) |

## 15. Tests and validation

| Scope | Result |
|-------|--------|
| Focused M35 (4 files) | **227 passed** |
| M31 regression | 43 passed |
| M32–M34 provider governance (8 files) | 387 passed |
| Full repository suite (`pytest -q`) | initial `59 failed, 3885 passed, 1 skipped` → after reload fix + commit: **3944 passed, 1 skipped, 370 warnings** (0 failed) |
| Critical checks / release check / runtime gate | covered by the suite — `test_m20_*` engineering readiness/control-center and `saathi/inference` runtime-gate tests pass on the committed tree |

The 59 initial failures were fully diagnosed (57 = an in-process `importlib.reload`
poisoning class identity across M35 files under full-suite order, fixed by a
subprocess import check; 2 = engineering-readiness tests reacting to the *uncommitted*
M35 file paths, resolved on commit). No test was skipped, xfailed, weakened, or
deleted. Details in `docs/M35_VALIDATION.md`.

## 16. Test-side-effect handling

- Retained: intentional M35 code, tests, docs, and deterministic M35 evidence.
- Restored/not staged: `docs/evidence/m25/` timestamp-only runtime noise.
- Confirmed: eligibility and health reads are non-mutating (test-covered);
  `docs/evidence/m27/` left untouched and unstaged.

## 17. Credentials and accounts

```
production credentials loaded      = 0
production OAuth flows             = 0
production accounts linked         = 0
real sandbox credentials loaded    = 0
real sandbox OAuth flows           = 0
real sandbox accounts linked       = 0
synthetic credentials used         = 1 (in-memory, non-functional)
credentials committed to Git       = 0
```

## 18. Commits and push

- `c975f95` — feat(m35): add governed sandbox credential lifecycle
- `9c84afe` — test(m35): certify credential and session governance
- `docs(m35)` — document and validate sandbox credential governance (this commit)

Pushed to `origin/milestone/m7-security-engine`; final divergence `0 0`.

## 19. Limitations

Synthetic credentials only; no live secret source; no Keychain retrieval; no real
sandbox account; no OAuth; no live provider session; no production credential/
account; no writes; no CANARY/ACTIVE activation; no Trading Guardian engagement.
These are the intended M35 boundaries, not defects.

## 20. Exact next action

```
READY FOR OPERATOR AUTHORIZATION TO START M36
```
