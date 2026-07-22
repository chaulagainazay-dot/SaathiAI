# M39.8 — Final Operator Package

**Status:** OPERATOR_PACKAGE_COMPLETE (offline).
**Series:** PRE-M40 offline readiness (`docs/PRE_M40_OFFLINE_READINESS_PLAN.md`).
**Module:** `saathi/credentials/m39_8.py` (machine-readable manifest).
**Tests:** `tests/test_m39_8_operator_package.py`.
**Evidence:** `docs/evidence/m39_8/` (deterministic; leak-clean).

This is the consolidated operator handbook for the SaathiOS M39 live-validation
surface. `m39_8.build_operator_package()` produces the machine-readable companion
to this document.

## 1. Architecture summary

M39 composes M31–M38 (SecretHandle, session leases, authorization, connector
registry, sandbox isolation, provider abstraction, M33/M34 hardened transport) to
exercise a **bounded, read-only** external provider (`github_meta`, `GET /user` +
`GET /meta`) under explicit operator control. M39.1–M39.7 add offline operator
tooling, failure simulation, the canary-readiness framework, deploy/rollback
preparation, monitoring & incident response, adversarial coverage, and
reproducibility validation. Nothing here grants live authority.

## 2. Trust boundaries

- The secret **value** never enters the CLI, evidence, events, or logs — only a
  reference (Keychain service, env var name, or approved store id).
- External network occurs **only** after preflight + `SAATHI_M39_ALLOW_LIVE_SANDBOX_VALIDATION`
  + all acknowledgements + a valid secret reference.
- The provider surface is read-only; no writes; no financial/trading provider.
- Authority (CANARY / ACTIVE / rollout / production / write) is applied out-of-band
  by the operator only, and only after live evidence exists.

## 3. Credential-reference setup & supported backends

See `docs/M39_SECRET_REFERENCE_SETUP.md`. Supported reference backends:
`OS_KEYCHAIN_REFERENCE`, `ENV_REFERENCE`, `ENCRYPTED_STORE_REFERENCE`
(operator-wired). `IN_MEMORY_TEST` is an offline fixture only. **Never** pass a raw
token; every entry point rejects token-shaped locators.

## 4. Disposable-token requirements

Disposable/revocable; sandbox account where possible; minimum read-only
permissions; revoked immediately after validation.

## 5. Permissions

- **Minimum required:** read-only identity + metadata (`GET /user`, `GET /meta`).
- **Prohibited:** repository write, org admin, billing, package/deploy/workflow
  secret write, any non-GET method, any endpoint outside `/user`,`/meta`.

## 6. Exact runtime acknowledgements (all 10 required)

```
I_CONFIRM_CREDENTIAL_IS_DISPOSABLE
I_CONFIRM_SANDBOX_ACCOUNT_WHERE_POSSIBLE
I_CONFIRM_MINIMUM_READ_ONLY_PERMISSIONS
I_CONFIRM_NO_REPOSITORY_WRITE_PERMISSION
I_CONFIRM_NO_ORG_ADMIN_PERMISSION
I_CONFIRM_NO_BILLING_PERMISSION
I_CONFIRM_NO_PACKAGE_DEPLOY_WORKFLOW_SECRET_WRITE
I_CONFIRM_REVOKE_IMMEDIATELY_AFTER_VALIDATION
I_CONFIRM_READINESS_IS_NOT_AUTHORIZATION
I_CONFIRM_NO_PRODUCTION_ROLLOUT_CANARY_ACTIVE_WRITE
```

## 7. Procedures (live steps are operator-run)

| Procedure | Reference |
|-----------|-----------|
| Secret reference setup | `docs/M39_SECRET_REFERENCE_SETUP.md` |
| Dry-run plan / preview | `m39-1-plan`, `m39-1-preview` |
| Single-session | `docs/M39_LIVE_VALIDATION_RUNBOOK.md` |
| Multi-session | `docs/M39_LIVE_VALIDATION_RUNBOOK.md` |
| Interruption / recovery | `docs/M39_INTERRUPTION_AND_RECOVERY.md` |
| Revocation | `m39-1-revocation-checklist` |
| Canary decision | `docs/M39_3_CANARY_FRAMEWORK.md` |
| Deployment | `docs/M39_4_DEPLOY_ROLLBACK.md` |
| Rollback | `m39-4-rollback-plan` |
| Incident response | `docs/M39_5_MONITORING_INCIDENT.md` |

## 8. Evidence interpretation

- `NOT_EXERCISED` = the live path was never run (fail-closed default).
- Canary verdict `BLOCKED_OPERATOR_SECRET_REQUIRED` until live evidence + explicit
  operator authorization exist.
- Deterministic fingerprints identical across runs prove reproducibility.

## 9. Known limitations

- live single-session / multi-session / external revocation / encrypted-store
  wiring: **NOT_EXERCISED**.
- Simulation covers transport faults, not real provider behavior.

## 10. Residual risks

- Operator supplies a non-disposable/over-scoped token (mitigated by acks +
  preflight).
- Operator forgets external revocation (mitigated by M39.1 checklist + M39.5 alert).
- Encrypted-store backend requires operator wiring before live use.

## 11. Final go-live checklist

1. M31–M39.7 regression green
2. offline failure gates pass
3. leak scans clean
4. deployment config validates (fail-closed)
5. operator supplies disposable secret **reference** (never a raw secret)
6. `export SAATHI_M39_ALLOW_LIVE_SANDBOX_VALIDATION=1` for the live window only
7. all 10 runtime acknowledgements provided
8. run bounded live single + multi session (`github_meta` GET `/user`,`/meta`)
9. confirm external credential revocation
10. evaluate canary ELIGIBILITY (separate explicit operator authorization required)
11. `export SAATHI_M39_KILL_SWITCH=1` to stop at any time

## Authority state

- LIVE PROVIDER CERTIFICATION: **NOT GRANTED**
- CANARY: **NOT GRANTED**
- ACTIVE: **NOT GRANTED**
- PRODUCTION DEPLOYMENT: **NOT AUTHORIZED**
- Trading Guardian: **UNENGAGED**
