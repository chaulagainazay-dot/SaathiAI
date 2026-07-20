# M43 — Test Report

**Suite:** `tests/test_m43_machine_verified_canary.py` — **15 passed**.
**Together with M42:** 40 passed. **M39–M43 focused regression:** 282 passed.
Full-suite total recorded in `M43_FINAL_REPORT.md`.

## Coverage

| Area | Tests |
|------|-------|
| Fail-closed (no credential / kill switch / missing approval) | `test_default_no_credential_blocked`, `test_kill_switch_blocks`, `test_missing_approval_blocks` |
| Grants nothing | `test_grants_nothing_everywhere` |
| Rehearsal flow verified but SIMULATED | `test_rehearsal_flow_verified_but_simulated` |
| SIMULATED rehearsal does NOT clear AB-PROV | `test_rehearsal_record_does_not_clear_ab_prov` |
| MACHINE record clears AB-PROV → RECOMMENDED (temp only) | `test_machine_record_clears_ab_prov` |
| Failed revocation → not verified | `test_machine_record_failed_revocation_not_verified`, `test_revocation_phase_token_still_valid_fails` |
| Incomplete verification → failed | `test_validation_phase_fails_on_incomplete` |
| Determinism / leak / emit | `test_evidence_deterministic_and_clean`, `test_emit_evidence` |
| M32 prohibition / backward-compat | `test_m32_prohibition_intact`, `test_backward_compat_intact` |
| No fabrication (real repo stays NOT_RECOMMENDED) | `test_real_repo_m42_still_not_recommended` |

## Provenance guarantee

The machine record is written only on a verified live revocation run. Rehearsal
(`SIMULATED_REHEARSAL`, `machine_verified_live: false`) cannot clear AB-PROV. The M42
hook was proven only in a temporary directory; no machine record was written to the
repository without a real live run.
