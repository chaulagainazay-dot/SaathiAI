# M43 — Security Audit

**Scope:** `saathi/credentials/m43.py` + `m43-*` CLI + the additive M42 provenance hook.
Composition-only. Grants nothing.

## Authority boundary (verified)

- `grants_anything: false`, `activates_production: false`, `expands_scope: false`,
  `grants_active/production/write: false` in every body.
- CLI aborts (exit 2) on any grant invariant violation.
- No ACTIVE / PRODUCTION / WRITE / FULL_ROLLOUT / SCOPE_EXPANSION. Trading Guardian
  UNCHANGED / UNENGAGED. M32 `ExecutionMode.CANARY/ACTIVE` prohibition unchanged.

## No fabrication (critical)

- The machine record is written ONLY on a verified live revocation run
  (`machine_verified` + `machine_verified_live`). The SIMULATED rehearsal record is
  marked `machine_verified_live: false` and does NOT clear AB-PROV (tested).
- Without a live run, `docs/evidence/m43/machine_verified_canary_completion.json` does
  not exist and M42 remains `GRADUATION_NOT_RECOMMENDED` (tested).
- The M42 hook mechanism was proven only in a temp directory; no machine record was
  written to the repository without a real live run.

## No side effects

- No network-library imports; no network call in the offline paths.
- No credential resolved in offline paths; reference-only contract preserved from M40/M41.
- No provider mutation, no runtime authority change.
- `saathi-os/`, `docs/ui*` untouched.

## Fail-closed (tested)

no credential → BLOCKED · kill switch → BLOCKED · missing approval → BLOCKED ·
incomplete verification → FAILED · token still authenticates on revocation → FAILED.

## Preserved invariants

M31–M42 public entry points intact (backward-compat 11/11). M42 criteria/verdict
logic unchanged (only the artifact source strengthened). M41 deny-by-default and
M40 certification model unchanged. Leak scanners: every body leak-clean.
