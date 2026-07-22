# M46 — Bounded Read-Only Disposable Canary (Implementation)

## Purpose

M46 is a composition-only **execution controller** for exactly one class:

```
READ_ONLY_DISPOSABLE_CANARY
```

Offline completion state (this commit):

```
M46_IMPLEMENTED_AWAITING_OPERATOR_AUTHORIZATION
```

No live provider call is performed by the offline implementation.

## Boundaries

| Layer | Meaning |
|-------|---------|
| Advisory readiness (M44/M45) | Request + snapshot well-formed |
| Operator authorization (M46 approval) | Explicit, expiring, one-shot |
| Bounded execution | Single read-only canary at ≤1% |
| Graduation | Separate; not M46 |
| Production activation | Forbidden |

## Components

| Component | Location |
|-----------|----------|
| Module | `saathi/credentials/m46.py` |
| Tests | `tests/test_m46_bounded_canary.py` |
| CLI | `m46-*` in `saathi/credentials/cli.py` |
| Approval template | `docs/m46/operator_canary_approval.template.json` |
| Evidence | `docs/evidence/m46/` |

## Reused systems

- M39 SecretHandle / live session / kill switch / allowlists
- M44 RolloutRequest validation
- M45 RuntimeAttestationSnapshot validation
- M43/M43.1 evidence fingerprints (read-only bindings)
- leakscan, HMAC fingerprint domains

## Live rule

`m46-run-canary --mode live` requires **all** of: valid approval, M44 request,
M45 snapshot, preflight pass, `--live-flag`, `SAATHI_M46_LIVE_GATE=1`, and a
secret **reference** (never a raw secret on CLI). Success stops at
`CANARY_COMPLETED_PENDING_EXTERNAL_REVOCATION`.
