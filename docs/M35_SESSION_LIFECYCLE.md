# M35 — Read-Only Session Lifecycle

`run_sandbox_session` (`saathi/credentials/m35.py`) drives one bounded, read-only
synthetic session end-to-end, **offline**. No network call, no write, no rollout
change.

## States (`SessionState`)

`REQUESTED → AUTHORIZED → LEASED → READY → RUNNING → COMPLETED`, plus the terminal
failure states `EXPIRED`, `REVOKED`, `FAILED`, `ABORTED`.

## Flow

1. **environment ceiling** — `PRODUCTION` aborts.
2. **provider / method ceiling** — non-matching provider or a write method aborts.
3. **approval** — `approval_permits` must match provider/account/operation/scope.
4. **verify account** — must be `VERIFIED`/`SYNTHETIC_VERIFIED`.
5. **verify scope** — must reach `VERIFIED`.
6. **capability ceiling** — request must be a subset (`request_within_ceiling`).
7. **issue lease** — `SessionLease` bounded by approval duration/uses.
8. **retrieve secret** — via the M31 broker into a `SecretHandle`.
9. **derive fingerprint** — non-reversible `credential_fingerprint`.
10. **consume lease** — the point where a provider call *would* occur; here it is a
    no-op (`SANDBOX_READ_ONLY_SIMULATED`).
11. **release secret** — the handle is always closed/zeroized (`finally`).
12. **end + sanitized result** — leak-clean, `contains_secret_values: false`.

## Result invariants

`external_calls: 0`, `external_writes: 0`, `handle_closed: true`,
rollout OFF, `trading_guardian: UNCHANGED / UNENGAGED`. Any failure aborts fail-closed
with the secret still released. No real provider call is ever made.
