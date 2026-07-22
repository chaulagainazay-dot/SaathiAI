# M39.3 — Canary-Readiness Framework

**Status:** CANARY_FRAMEWORK_COMPLETE — **CANARY NOT GRANTED** (offline).
**Series:** PRE-M40 offline readiness (`docs/PRE_M40_OFFLINE_READINESS_PLAN.md`).
**Module:** `saathi/credentials/m39_3.py` (composes `m39.evaluate_canary_eligibility`).
**Tests:** `tests/test_m39_3_canary_framework.py` — 16 passed.
**Evidence:** `docs/evidence/m39_3/` (deterministic; leak-clean).

## Purpose

Complete the *operational* canary framework around the existing read-only
eligibility evaluator: immutable prerequisites, operator-approval-record
format + validator, rollback triggers, circuit breakers, rollout bounds, and exit
criteria. The framework prepares every decision input **without ever granting
authority**.

## Hard invariant

`evaluate_canary_decision` **always** returns `CANARY_NOT_GRANTED` with every
`grants_*` field `false` — even when all 13 prerequisites are marked met and a
structurally valid operator approval record is supplied — because live M39
evidence is `NOT_EXERCISED` in this series. A valid approval record is a *necessary
operator input*, never a grant. Authority is applied out-of-band by the operator
after live evidence exists. The CLI additionally aborts (exit 2) if any code path
ever produced `grants_canary != false`.

## Components

- **Immutable prerequisites** (`PRQ-1`…`PRQ-13`): regression, offline gates, live
  single/multi PASSED, identity/scope qualification, budget compliance, cleanup,
  external revocation, leak scans, no terminal failures, evidence complete, valid
  operator approval record. Deny-by-default (unknown = unmet).
- **Rollback triggers** (`RBK-1`…`RBK-7`): error-budget breach, auth-denial spike,
  budget exhaustion, kill switch, leak detected, circuit-breaker open, write attempt.
- **Circuit breakers** (`CBK-1`…`CBK-3`): consecutive-failure, rate-limit, secret-resolution.
- **Rollout bounds**: canary 1–5% ceiling (ACTIVE/full rollout is a separate authority).
- **Allowlist**: provider `github_meta`; endpoints `user`,`meta`; method `GET` — canary may not widen.
- **Exit criteria**: `graduate_requires_all` / `abort_if_any`.
- **Operator approval record schema + validator**: 10 required fields, 5 required
  acknowledgements, deny-by-default.

## Authority state (unchanged)

CANARY / ACTIVE / rollout / production / write = **NOT GRANTED**. Trading Guardian
**UNENGAGED**.

## Reproduce

```bash
python -m pytest tests/test_m39_3_canary_framework.py -q
python -m saathi.credentials.cli m39-3-canary-decision
python -m saathi.credentials.cli m39-3-framework
python -m saathi.credentials.cli m39-3-emit-evidence   # deterministic
```
