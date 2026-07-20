# M42 — Security Audit

**Scope:** `saathi/credentials/m42.py` + `m42-*` CLI. Composition-only review layer.

## Authority boundary (verified)

M42 grants nothing and changes no runtime state.
- `grants_anything: false`, `alters_runtime_authority: false` in every recommendation.
- `explicitly_not_granted` always includes ACTIVE, PRODUCTION, WRITE, FULL_ROLLOUT,
  SCOPE_EXPANSION, TRADING_GUARDIAN.
- CLI `m42-review-graduation` aborts (exit 2) on any grant/authority-alter invariant.

## No side effects (verified)

- **No network**: zero network-library imports (`grep` clean); no call performed.
- **No credential**: resolves nothing; reads only committed evidence JSON.
- **No provider mutation / no runtime change**: pure read + compute.
- **No writes to `saathi-os/` or `docs/ui*`**: commits are file-scoped and verified.

## Fail-closed behavior (tested)

| Case | Result |
|------|--------|
| mandatory evidence missing | GRADUATION_BLOCKED |
| malformed / unreadable mandatory evidence | GRADUATION_BLOCKED |
| wrong provider / identity | not RECOMMENDED |
| prohibited grant (active/production/write) observed | not RECOMMENDED (AB-5) |
| Trading Guardian engaged | not RECOMMENDED (AB-11) |
| unresolved alert / rollback condition / identity drift | not RECOMMENDED |
| missing revocation proof | not RECOMMENDED |
| simulated result presented as live | not RECOMMENDED |
| operator attestation where machine proof required | not RECOMMENDED (AB-PROV) |
| BLOCKED never converts to RECOMMENDED | verified |

## Provenance integrity

Operator attestation is classified distinctly from machine proof and cannot satisfy a
machine-proof criterion. This is the decisive control on the current evidence chain.

## Preserved invariants

- M31–M41 public entry points intact (backward-compat 11/11).
- M32 `ExecutionMode.CANARY/ACTIVE` prohibition unchanged (asserted in GC-13 + test).
- M41 deny-by-default unchanged.
- Leak scanners: every evidence body leak-clean; no raw secret / auth header / PAT
  fragment / recoverable credential / fabricated live event.

## Trading Guardian

UNCHANGED / UNENGAGED.
