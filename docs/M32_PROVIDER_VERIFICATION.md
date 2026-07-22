# M32 — Provider Verification

Modules: `fingerprint.py`, `verification.py`

## Additional eligibility layer (never a replacement)

```
platform production certification (M25)
+ connector certification (M30)
+ provider adapter verification (M32)
+ provider configuration readiness (M32)
+ account and credential readiness (M31)
+ rollout
+ approval
= execution eligibility
```

Provider verification does not replace connector certification, production
certification, rollout, or approval.

## States (`ProviderVerificationState`)

`UNVERIFIED`, `SIMULATION_VERIFIED`, `SHADOW_VERIFIED_WITH_LIMITATIONS`, `STALE`,
`REVOKED`, `FAILED`. Verified set = `{SIMULATION_VERIFIED,
SHADOW_VERIFIED_WITH_LIMITATIONS}`. Highest permitted in M32 =
`SHADOW_VERIFIED_WITH_LIMITATIONS`; the pilot achieves `SIMULATION_VERIFIED`
(local simulator → not live).

## Fingerprint (`compute_provider_fingerprint`)

Deterministic SHA-256 over: provider identity, adapter version, connector
manifest, auth profile, operation set, request/response schema surfaces,
normalization rules, retry policy, timeout policy, rate-limit policy,
side-effect + data classification, redaction surface, test corpus id, and
simulator version — plus content hashes of the provider-runtime source files.
Docs are excluded. Any material change alters the fingerprint.

## Read vs. mutate (M31 correction preserved)

- `resolve_provider_verification(...)` — **eligibility read; never mutates**. On
  drift it reports `STALE` by fingerprint mismatch but leaves the store untouched.
- `verify_provider(...)` — explicit (re)assessment; mutates the store.
- `check_provider_drift(..., mark_stale=True)` — explicit drift command; may mark stale.

Stale verification blocks future CANARY/ACTIVE eligibility and only an explicit
reassessment refreshes it. Provider drift never mutates connector certification.
