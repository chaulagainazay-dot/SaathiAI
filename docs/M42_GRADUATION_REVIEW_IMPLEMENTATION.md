# M42 — Graduation Review — Implementation

**Status:** COMPLETE — recommendation `GRADUATION_NOT_RECOMMENDED`.
**Branch:** `milestone/m42-graduation-review`.
**Module:** `saathi/credentials/m42.py` (composition-only; grants nothing).
**Tests:** `tests/test_m42_graduation_review.py` — 25 passed.
**Evidence:** `docs/evidence/m42/` (deterministic; leak-clean).

## What M42 is

An evidence-review / decision-support layer. It reads the M40 live-certification
evidence and the M41 canary + closure evidence, reuses the M39.3 graduation criteria
and M39.5 alert contracts, checks provenance and consistency, and emits one
deterministic recommendation. It performs **no** network call, resolves **no**
credential, mutates **no** provider, and alters **no** runtime authority, flag,
policy, or execution mode.

## Responsibilities (all composition-only)

1. **Evidence inventory** (`build_inventory`) — classifies each required artifact
   `PRESENT_VALID` / `PRESENT_INVALID` / `MISSING` / `INCONSISTENT` / `NOT_APPLICABLE`,
   with observed provenance. Mandatory missing/invalid → fail closed.
2. **Consistency** (`check_consistency`) — cross-checks provider, read-only, identity,
   authority state, Trading Guardian, verdicts, and the M32 prohibition declaration.
3. **Criteria evaluator** (`evaluate_criteria`) — GC-1..GC-14, reusing M39.3
   `graduate_requires_all`. Each criterion carries id/description/source/observed/
   expected/status/severity/rationale + provenance + machine-proof-required flag.
4. **Abort evaluator** (`evaluate_abort`) — AB-1..AB-11 + **AB-PROV** (operator
   attestation where machine proof is required).
5. **Recommendation** (`build_recommendation`) — deterministic verdict + digest +
   maximum-future-authority + explicitly-not-granted + residual-risks + operator actions.

## Verdict logic (fail-closed)

- mandatory evidence missing/invalid/unreviewable → `GRADUATION_BLOCKED`
- any abort present, any criterion fail/block, or inconsistency → `GRADUATION_NOT_RECOMMENDED`
- all criteria pass + no abort + consistent → `GRADUATION_RECOMMENDED`

`BLOCKED` never converts to `RECOMMENDED`. The recommendation is advisory only:
`grants_anything: false`, `alters_runtime_authority: false`.

## Provenance

Operator attestation (`OPERATOR_ATTESTED`) is never accepted where `MACHINE_PROOF`
is required. The M40 chain is machine-proven; the M41 bounded-canary completion is
operator-attested → AB-PROV fires → `GRADUATION_NOT_RECOMMENDED`.

## CLI

`m42-evidence-inventory`, `m42-evaluate-criteria`, `m42-review-graduation`,
`m42-emit-evidence` — inherit the forbidden-argv guard; no network/credential;
`m42-review-graduation` aborts on any grant/authority-alter invariant.
