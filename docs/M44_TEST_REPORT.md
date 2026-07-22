# M44 — Test Report

## Summary

```
tests/test_m44_rollout_authorization.py .......................... 77 passed
```

- **M44 suite:** 77 passed, 0 failed (`~0.19s`).
- **M44.1 additions:** evidence-precedence, provenance verification, genuine
  on-disk integration, hermetic base isolation, framework-completion.
- **Leak scan of `docs/evidence/m44/*.json`:** all clean.
- **Secret grep of new source/tests:** no real secret material.

Runner: `.venv/bin/python -m pytest`.

## Coverage by category

| Category | Tests |
|----------|-------|
| Framework readiness / advisory-only | `test_framework_state_is_ready_advisory`, `test_framework_grants_nothing` |
| Deny-by-default | `test_empty_request_denied_incomplete`, `test_each_missing_mandatory_field_denies` |
| Positive path | `test_valid_request_advisory_only`, `test_all_builtin_policies_have_no_live_execution` |
| Tampering / signature | `test_tampered_field_breaks_signature`, `test_missing_signature_denied`, `test_wrong_operator_signature_denied` |
| Expired approvals | `test_expired_authorization_denied`, `test_approval_after_expiration_denied`, `test_unparseable_timestamp_denied` |
| Wrong provider / scope / risk | `test_wrong_provider_denied`, `test_scope_not_allowed_denied`, `test_risk_level_not_allowed_by_policy` |
| Percentage guard | negative, above-policy, fractional, missing, off-step, bool (6 tests) |
| Wrong / missing evidence | `test_missing_machine_proof_denied`, `test_unresolved_evidence_denied`, `test_credential_not_closed_denied`, `test_graduation_not_recommended_denied`, `test_dryrun_needs_no_evidence_chain` |
| Runtime safety gates | `test_default_runtime_snapshot_blocks`, `test_each_unsafe_condition_blocks` (9 params), `test_kill_switch_env_blocks`, `test_validation_blocked_by_runtime_gate` |
| Rollback scenarios | `test_rollback_deterministic_no_trigger`, `test_rollback_fires_on_trigger`, `test_all_rollback_triggers_recognized` |
| Policy registry / extensibility | `test_unknown_policy_denied`, `test_register_policy_rejects_live_execution`, `test_register_valid_policy_then_use` |
| Ledger immutability | `test_ledger_append_and_chain`, `test_ledger_tamper_detected`, `test_create_and_review_persist` |
| Audit API | `test_audit_endpoints_leak_clean`, `test_audit_validation_reports_verdict` |
| Schema / serialization | `test_validation_result_serializable_and_clean`, `test_request_fingerprint_deterministic`, `test_request_fingerprint_changes_on_edit`, `test_policy_fingerprint_stable` |
| Security regression | `test_no_secret_material_in_any_output`, `test_leaky_ledger_payload_refused`, `test_simulation_is_not_live`, `test_evidence_bundle_state_advisory` |
| **M44.1 provenance** | `test_verify_genuine_machine_record`, operator-attested / simulated / not-live / lifecycle / 401 / empty / provider / identity / scope mismatch |
| **M44.1 resolution** | `test_resolve_uses_live_review_not_stale_file`, `test_resolve_genuine_chain_recommended_machine_proof`, `test_graduation_requires_verified_machine_record`, `test_stale_index_cannot_satisfy_graduation`, `test_isolated_base_does_not_use_real_repo_machine_proof` |
| **M44.1 integration** | `test_genuine_request_reaches_advisory_only`, `test_unreferenced_machine_record_cannot_authorize`, `test_request_fingerprints_must_resolve`, `test_framework_completion_advisory_only` |

## CLI verification

`m44-status` ⇒ `ROLLOUT_AUTHORIZATION_FRAMEWORK_READY` (legacy alias
`ROLL_OUT_AUTHORIZATION_FRAMEWORK_READY`), `framework_ready: true`, and
`current_graduation_state.provenance: MACHINE_PROOF` against the real post-M43.1
tree.

`m44-validate-rollout` / `m44-review-rollout` against a genuine evidence-bound
request report evidence-chain checks true, but **fail closed** on the default
`RuntimeSnapshot` (runtime attestation absent) — correct floor; CLI cannot imply
live execution readiness.

`m44-create-rollout` / `m44-list-rollouts` / `m44-show-rollout` /
`m44-expire-rollout` / `m44-verify-ledger` / `m44-simulate` / `m44-emit-evidence`
exercised; every output carries `authorizes_execution: false`.

## What the tests deliberately do NOT do

They do not perform any live network call, do not fabricate live machine proof, and
do not assert any execution authority. A `VALIDATED` verdict is asserted to still
carry `authorizes_execution: false`.
