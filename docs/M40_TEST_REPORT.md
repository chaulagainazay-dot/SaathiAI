# M40 — Test Report

**Suite:** `tests/test_m40_live_certification.py` — **25 passed**.
**Regression:** M31–M40 focused **1075 passed**; full suite (post-docs) recorded in
`M40_FINAL_REPORT.md`.
**Mode:** offline / deterministic / fixtures only. No real network, no real credential.

## Coverage by requirement

| Requirement | Tests |
|-------------|-------|
| Integration (all stages wire) | `test_rehearsal_never_certifies`, `test_stage6_evidence_complete_and_clean` |
| Negative (fail-closed) | `test_no_credential_blocks`, `test_stage1_fails_closed_on_each_missing` (×4), `test_stage2_rejects_synthetic_backend` |
| Never certify without live | `test_forged_complete_config_missing_secret_blocks_not_certifies`, `test_never_grants_anything` |
| Interruption | `test_interruption_single_session_cleans_up` (SecretHandle destroyed) |
| Timeout | `test_timeout_retry_classified_not_certified` |
| Lease collision / isolation | `test_stage4_rehearsal_isolation`, `test_multi_session_distinct_correlation_ids` |
| Revocation → 401 → cleanup → classification | `test_stage5_rehearsal_revocation_401_cleanup`, `test_stage5_live_without_operator_confirmation_blocks` |
| Evidence verification | `test_stage6_evidence_complete_and_clean`, `test_evidence_deterministic_and_clean` |
| Kill switch | `test_kill_switch_blocks_certification` |
| Raw-secret rejection | `test_stage1_rejects_raw_secret_locator`, `test_no_secret_in_certification_output` |
| Determinism / replay | `test_evidence_deterministic_and_clean` |
| Authorities not granted | `test_authorities_not_granted_everywhere` |

## Deterministic replay

All evidence built via pure functions (no wall clock in bodies); double-build is
byte-identical. Fault paths use fixed fixture senders/resolvers.

## Result

Every achievable offline validation task passed. The only unexercised paths are the
real-provider live stages, which require an operator-controlled disposable credential
and are correctly reported `NOT_EXERCISED` / `SIMULATED_NOT_LIVE`.
