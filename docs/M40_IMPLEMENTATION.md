# M40 — Live Validation & Production Certification — Implementation

**Status:** LIVE-VALIDATION LAYER COMPLETE — LIVE CERTIFICATION BLOCKED (operator
disposable secret reference required).
**Module:** `saathi/credentials/m40.py` (composes M31–M39; no new subsystem).
**Tests:** `tests/test_m40_live_certification.py` — 25 passed.
**Evidence:** `docs/evidence/m40/` (deterministic; leak-clean).

## What M40 is

A controlled live-validation layer that proves the offline-certified M31–M39
security model behaves correctly against a REAL provider under explicit operator
authorization. It adds **no** product feature, provider capability, or production
deployment. It composes existing M39 runners.

## Two entry points

### `run_live_certification(config)` — real gated pipeline
Fail-closed 6-stage pipeline. Stops at the earliest failing gate.

| Stage | Function | Composes |
|-------|----------|----------|
| 1 Operator acknowledgement | `stage1_operator_acknowledgement` | `validate_acknowledgements` + authorization + environment confirmation + disposable-reference presence |
| 2 Provider preflight | `stage2_provider_preflight` | `run_live_preflight` (no remote mutation) |
| 3 Single session | `stage3_single_session` | `run_live_single_session` (lease → SecretHandle → read → evidence → release → destroy → verify) |
| 4 Multi session | `stage4_multi_session` | `run_live_multisession` (isolation, budget, cleanup) |
| 5 External revocation | `stage5_external_revocation` | `record_external_revocation` + post-revocation 401 retry |
| 6 Evidence verification | `stage6_evidence_verification` | deterministic evidence assembly + leak scan |

### `run_stage_rehearsal()` — offline mechanics proof
Fixture-driven rehearsal of every stage. Every result is `SIMULATED_NOT_LIVE`.
Explicitly **not** a certification; grants nothing.

## Certification verdicts

- `LIVE_CERTIFIED` — reachable **only** when every stage runs against a real
  provider (`live_network`) and passes.
- `LIVE_FAILED` — a stage genuinely failed during a live run.
- `LIVE_BLOCKED_OPERATOR_SECRET_REQUIRED` — no approved disposable secret reference.
- `LIVE_BLOCKED` — a gate blocked (kill switch, preflight, missing secret, simulation).

`live_certified` is `False` unless the verdict is `LIVE_CERTIFIED`.

## This session's result

No operator credential supplied → certification = **LIVE_BLOCKED_OPERATOR_SECRET_REQUIRED**.
Rehearsal proves all 6 stages wire correctly (SIMULATED_NOT_LIVE). No real network,
no real credential, no fabricated success.

## Additive-only guarantee

M31–M39 untouched. Backward-compat check (`m39-4-backward-compat`) remains 11/11.
`m40-*` CLI commands inherit the M39 forbidden-argv guard.
