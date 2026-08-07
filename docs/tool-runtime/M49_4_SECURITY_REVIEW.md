# M49.4 Security Review

## Scope

Closure review of M49.1–M49.3 tool runtime — no new attack surface intentionally added
beyond audits/tests and `project_run` fail-closed tightening.

## Findings

### Critical

None.

### High

None open on canonical path.

### Accepted limitations

1. 59 LEGACY_BOUNDED handlers still execute after governance (not manifest-authority)
2. Single-host SQLite idempotency only
3. Live connectors not certified (dry-run/fixture)
4. Compatibility bridge retained for 11 names
5. Persona text may still *describe* run_shell — runtime blocks it

## Residual risk count

5 accepted limitations (above). 0 critical open.

## Secret scan posture

No credentials introduced in M49.4 code. Tests use fixtures only.

## Trading Guardian

Unengaged advisory only — financial execution PROHIBITED.
