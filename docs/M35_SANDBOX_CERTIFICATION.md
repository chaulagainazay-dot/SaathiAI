# M35 — Sandbox Session Certification

`assess_sandbox_certification` (`saathi/credentials/m35.py`).

## States (`SandboxCertificationState`)

`UNVERIFIED`, `SYNTHETIC_VERIFIED`, `SANDBOX_GOVERNANCE_VERIFIED`,
`SANDBOX_SESSION_CERTIFIED`, `STALE`, `REVOKED`, `FAILED`.

## Maximum permitted state (offline)

```
SANDBOX_GOVERNANCE_VERIFIED
```

`M35_MAX_CERTIFICATION_STATE` caps the assessment at
`SANDBOX_GOVERNANCE_VERIFIED`. Even if the "real credential"/"real account" flags
are set, the assessment defensively returns the cap and **never** returns
`SANDBOX_SESSION_CERTIFIED`. That state requires an explicitly authorized future run
with a real disposable sandbox credential and a real sandbox account, and is not
claimed here.

## Composition and eligibility

`compose_session_eligibility` ANDs every gate: platform production certification,
connector certification, provider simulation freshness, external profile freshness,
credential validity, secret-source readiness, environment classification, account
verification, scope verification, capability ceiling, credential health, lease
validity, approval validity, provider health, quarantine, and rollout-off. Any
denial fails closed. The real sandbox session stays blocked; provider rollout stays
OFF; production execution stays blocked. Eligibility reads mutate nothing.

## Expected M35 result

```
credential governance = SANDBOX_GOVERNANCE_VERIFIED
synthetic session      = VERIFIED
real sandbox session   = NOT EXERCISED
```
