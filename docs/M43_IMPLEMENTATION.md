# M43 — Machine-Verified Bounded Canary — Implementation

**Status:** LAYER COMPLETE — machine-verified live run PENDING operator disposable credential.
**Branch:** `milestone/m42-graduation-review` (M43 built on top).
**Module:** `saathi/credentials/m43.py` (composition-only; grants nothing).
**Tests:** `tests/test_m43_machine_verified_canary.py` — 15 passed.
**Evidence:** `docs/evidence/m43/` (deterministic; leak-clean).

## Purpose

Eliminate the sole M42 abort condition (`AB-PROV`) by producing a fully
machine-generated bounded-canary verification chain, replacing the operator-attested
M41 completion. Strengthens provenance only — grants nothing, activates nothing,
expands no scope.

## Composition (no parallel systems)

- M39.3 operator approval-record validation
- M40 live execution + revocation (401) framework
- M41 bounded rollout policy + CanaryController (live)
- M42 graduation re-evaluation
- existing evidence ledger + leak scanner

## Two-phase flow (a single run cannot both use and revoke a credential)

1. **Validation phase** (`run_validation_phase`) — authorize (approval + rollout +
   disposable reference), execute the bounded read-only canary **live** via the M41
   controller, then verify (machine): endpoint identity bound, bounded read-only
   completed, cleanup complete, SecretHandle destroyed, budget compliant, zero-error
   budget held, rollback state clean, no rollback triggered. →
   `MACHINE_CANARY_VALIDATED_PENDING_REVOCATION`.
2. **Revocation phase** (`run_revocation_phase`) — after the operator revokes, a live
   retry must return **HTTP 401**, proving credential destruction + SecretHandle
   cleanup. → `MACHINE_CANARY_VERIFIED`.

`assemble_machine_record` emits an M42-compatible record with **MACHINE** provenance
(`machine_verified_live: true`, `live_exercised: true`). `run_revalidation` re-runs M42.

## M42 provenance hook (additive; criteria unchanged)

M42's bounded-canary artifact prefers a machine-verified record at
`docs/evidence/m43/machine_verified_canary_completion.json` when present. This changes
the evidence **source** only; graduation criteria and verdict logic are untouched.
With a machine record present, provenance is `MACHINE_PROOF`, `AB-PROV` clears, and the
M42 verdict can reach `GRADUATION_RECOMMENDED`.

## Fail-closed

No credential → `MACHINE_CANARY_BLOCKED`. Kill switch, missing approval, incomplete
verification, token-still-valid revocation → blocked/failed. The SIMULATED rehearsal
proves the flow but does **not** clear AB-PROV. No live evidence is fabricated; the
machine record is written only on a verified live revocation run.

## Verdicts

`MACHINE_CANARY_BLOCKED` · `MACHINE_CANARY_VALIDATED_PENDING_REVOCATION` ·
`MACHINE_CANARY_VERIFIED` · `MACHINE_CANARY_FAILED`.
