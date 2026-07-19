# M39.4 — Deployment & Rollback Preparation

**Status:** DEPLOY_ROLLBACK_PREP_COMPLETE (offline; executes nothing).
**Series:** PRE-M40 offline readiness (`docs/PRE_M40_OFFLINE_READINESS_PLAN.md`).
**Module:** `saathi/credentials/m39_4.py`.
**Tests:** `tests/test_m39_4_deploy_rollback.py` — 11 passed.
**Evidence:** `docs/evidence/m39_4/` (deterministic; leak-clean).

## Purpose

Prepare — but never execute — everything required to enable and safely roll back
the M39 external-provider live-validation surface. No production deployment,
external write, or credential action occurs.

## Components

- **Deployment-config validator** — validates an M39-surface config against the
  fail-closed posture: live flag defaults off, rollout OFF, provider `github_meta`,
  budgets within ceilings, kill switch wired, canary/active NOT GRANTED. Rejects
  any unsafe value.
- **Release checklist** — `REL-1`…`REL-10`; REL-1..REL-8 offline-verifiable,
  REL-9/REL-10 are operator/live steps.
- **Rollback plan + script template** — ordered reversible steps (`RB-1`…`RB-6`)
  and a TEXT-ONLY bash template that unsets the live flag, trips the kill switch,
  points to external revocation, and re-runs regression. No push, no `--force`, no
  `reset --hard`. Trading Guardian untouched. Prefers `git revert`.
- **Backward-compatibility check** — proves M39.x is additive: all 11 tracked
  M31–M38/M39 public entry points still resolve (`all_present=true`).
- **Artifact integrity** — recomputes the deterministic M39 fingerprint twice and
  confirms stability (immutable-artifact verification).
- **Smoke-test definitions** — `SMK-1`…`SMK-4` offline CLI checks (preflight,
  diagnostics, simulation matrix, canary decision).
- **Post-deploy verification plan** — read-only invariant checks; live parts remain
  `OFFLINE_ONLY` until an operator supplies a disposable secret reference.

## Authority state (unchanged)

CANARY / ACTIVE / rollout / production / write = **NOT GRANTED**. No production
deployment authorized. Trading Guardian **UNENGAGED**.

## Reproduce

```bash
python -m pytest tests/test_m39_4_deploy_rollback.py -q
python -m saathi.credentials.cli m39-4-backward-compat
python -m saathi.credentials.cli m39-4-rollback-plan
python -m saathi.credentials.cli m39-4-emit-evidence   # deterministic
```
