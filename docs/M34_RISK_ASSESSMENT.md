# M34 — Pre-Live Risk Assessment

**Milestone:** M34 — Bounded Live Read-Only External Verification
**Provider:** `github_meta` · **Operation:** `get_meta` (read-only `GET`) · **Data class:** `PUBLIC`
**Live-call budget:** 3 (retries included, hard max 5)

---

## 1. Risk posture summary

M34's on-network surface is a single anonymous `GET` to public GitHub infrastructure
metadata, bounded to at most 3 calls, with every M25–M33 governance control in the path and
no rollout, credential, account link, or write authority. Residual risk is **LOW** and fully
contained by fail-closed controls. The genuine live call remains operator-only and was not
exercised in this session.

## 2. Risk register

| # | Risk | Likelihood | Impact | Mitigation | Residual |
|---|------|-----------|--------|------------|----------|
| R1 | SSRF / redirect to internal host | Low | High | DNS/SSRF revalidation blocks private, link-local, reserved, and mixed public+private resolutions; redirect limit `0` (`test_private_or_unsafe_dns_blocks`) | Very Low |
| R2 | TLS downgrade / MITM | Low | High | TLS verification required; unverified or hostname-mismatch fails closed → `NOT_QUALIFIED_SECURITY_FAILURE` (`test_tls_*_blocks`) | Very Low |
| R3 | Secret / PII leak into evidence | Low | High | No raw body/headers persisted; every payload leak-scanned before write (fail closed); redaction evidence asserts absence (`test_no_raw_body_in_result_or_evidence`) | Very Low |
| R4 | Unbounded / runaway calls | Low | Medium | Budget clamped to `[1,5]`, default 3; retries consume budget; `actual_call_count ≤ budget` (`test_actual_calls_never_exceed_budget`) | Very Low |
| R5 | Oversized / hostile response | Low | Medium | 256 KiB response ceiling; oversized response fails (`test_oversized_response_fails`) | Very Low |
| R6 | Silent write / mutation | Very Low | High | Profile is `GET`-only; write method blocked by profile validation + defence-in-depth; `external_write_calls: 0` | Negligible |
| R7 | Accidental rollout / canary activation | Very Low | High | Verification and canary assessment never mutate rollout; `provider_rollout: OFF`, `canary_providers: 0`, `active_providers: 0` (`test_qualification_does_not_activate_rollout`, `test_canary_assessment_does_not_activate`) | Negligible |
| R8 | Trading Guardian engagement | Very Low | High | M34 never touches trading; `trading_provider_calls: 0`; guardian `UNCHANGED / UNENGAGED` | Negligible |
| R9 | Schema drift breaking downstream | Low | Low | Schema-compatibility classifier; missing-required/type-change fails → `NOT_QUALIFIED_SCHEMA_FAILURE`; additive change passes with limitation | Low |
| R10 | Provider rate-limit / 429 | Medium | Low | 429 is treated as a provider condition, never success or security failure; rate-limit visibility recorded (`test_429_does_not_qualify`) | Low |
| R11 | Provider outage during verify | Medium | Low | 503/timeout classified as provider/transient failure; no qualification granted; no state falsely set | Low |
| R12 | Import-time / accidental auto network | Very Low | Medium | No network at import or in the suite; live path disabled without the env flag (`test_module_import_makes_no_call`, `test_default_disabled_without_env`) | Negligible |
| R13 | Non-deterministic / unauditable evidence | Low | Low | Deterministic offline generator; only the append-only registry differs across runs (same fingerprint) | Low |
| R14 | Provider quarantined but still verified | Very Low | Medium | Quarantine store checked before any call; quarantined provider blocks (`test_quarantined_provider_blocks`) | Negligible |

## 3. Blast radius

- **Network:** one host, `api.github.com`, TLS-verified, ≤3 GETs, ≤256 KiB each.
- **Data:** `PUBLIC` infrastructure metadata only; no user data, no credentials.
- **State:** external verification registry only (SHADOW mode); rollout untouched.
- **Financial / trading:** none — `financial_provider_calls: 0`, `trading_provider_calls: 0`.

## 4. Rollback

M34 changes nothing that requires rollback: no rollout, no schema migration, no persisted
production state. The external verification record can be revoked/recovered via the existing
`external-revoke` / `external-recover` commands. Reverting the M34 commits removes the harness
entirely with no residual effect.

## 5. Go / no-go

**GO for operator-triggered live verification** — all pre-live gates pass (offline suites
green, authorization complete, provider identity confirmed, not quarantined, read-only
ceiling held, budget bounded). **No-go conditions:** any failing offline gate, any missing
acknowledgement, provider quarantined, or budget outside `[1,5]`. In this session the live
call was **not exercised**; the go decision is recorded for the operator, not acted on.
