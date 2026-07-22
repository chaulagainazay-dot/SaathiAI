# M44 — Security Review

## Threat model

M44 is a gating/decision-support layer. Its security goal is **fail-closed**: it
must never emit a result that could be mistaken for, or relied upon as, execution
authorization; it must never leak secrets; and it must not weaken any M31–M43
guarantee.

## Invariant checklist

| Invariant | Enforcement | Test |
|-----------|-------------|------|
| Deny-by-default | empty/partial request ⇒ `ROLLOUT_REQUEST_INCOMPLETE`; default `RuntimeSnapshot` blocks | `test_empty_request_denied_incomplete`, `test_default_runtime_snapshot_blocks` |
| Grants nothing | every output hard-codes `authorizes_execution/grants_* = false` | `test_framework_grants_nothing`, `test_valid_request_advisory_only` |
| No live execution policy | `permits_live_execution` False for all; `register_policy` rejects True | `test_all_builtin_policies_have_no_live_execution`, `test_register_policy_rejects_live_execution` |
| Tamper-evident requests | operator signature recomputed and compared | `test_tampered_field_breaks_signature`, `test_wrong_operator_signature_denied` |
| Tamper-evident ledger | hash chain with back-links | `test_ledger_tamper_detected` |
| Bounded percentage | discrete ceilings + per-policy subset | `test_percentage_*` (6 tests) |
| Provider/scope least privilege | `github_meta` + read-only scopes only | `test_wrong_provider_denied`, `test_scope_not_allowed_denied` |
| Evidence-driven | machine proof / closed credential / graduation required by policy | `test_missing_machine_proof_denied`, `test_credential_not_closed_denied`, `test_graduation_not_recommended_denied` |
| No trust of stale M42 string | live review + independent machine verify; stale file never indexed | `test_resolve_uses_live_review_not_stale_file`, `test_graduation_requires_verified_machine_record` |
| Provenance fail-closed | simulated / attested / not-live / open lifecycle / no 401 / provider-scope-identity mismatch | `test_verify_*` (M44.1) |
| Unreferenced proof ignored | request must name fingerprints; ambient on-disk proof does not auto-satisfy | `test_unreferenced_machine_record_cannot_authorize` |
| Expiration honored | not-expired + ordered timestamps | `test_expired_authorization_denied`, `test_approval_after_expiration_denied` |
| Kill switch respected | snapshot flag + `SAATHI_M39_KILL_SWITCH` env | `test_kill_switch_env_blocks` |
| No secrets emitted | `leakscan.is_clean` guards all writes | `test_no_secret_material_in_any_output`, `test_leaky_ledger_payload_refused` |
| M32 prohibition unchanged | outputs assert `m32_prohibition: UNCHANGED`; no runtime touch | `test_framework_grants_nothing` |
| Trading Guardian unengaged | outputs assert `UNCHANGED / UNENGAGED` | `test_framework_grants_nothing` |

## Secret handling

- Requests carry **references and fingerprints only** — approval fingerprints,
  evidence fingerprints, operator identity strings. No token, key, or credential
  value is a field of `RolloutRequest`.
- `to_public()` is the only projection written or fingerprinted; it is leak-scanned
  before any ledger append or CLI emission.
- The CLI rejects a request file whose public projection is not leak-clean
  (`leak_detected_in_request`).
- `load_evidence_index` reads only boolean/enum provenance markers from evidence
  files, never secret-bearing fields.

## Attack scenarios considered

1. **Forged authorization** — attacker edits a request to widen percentage/scope.
   The operator signature is computed over the canonical core; any edit invalidates
   it ⇒ `operator_signature_invalid`.
2. **Replayed expired approval** — expiration is compared to `now`; expired ⇒
   `authorization_expired`.
3. **Fabricated evidence** — evidence is resolved by fingerprint against on-disk
   provenance markers; unknown fingerprints ⇒ `evidence_chain_unresolved`; missing
   markers ⇒ `machine_proof_absent` / `credential_lifecycle_not_closed` /
   `graduation_not_recommended`.
4. **Ledger rewrite** — hash chain back-links make any historical edit detectable
   via `verify_ledger_chain`.
5. **Privilege escalation via policy** — a custom policy that permits live
   execution is rejected at registration and at validation.
6. **Secret exfiltration through evidence/audit** — all outputs are leak-scanned and
   carry `contains_secret_values: false`; audit endpoints return references only.

## Residual notes

- M44 trusts that the caller-supplied `RuntimeSnapshot` reflects reality. Through
  the CLI, no snapshot is attestable, so CLI `m44-review-rollout` is deny-by-default
  on the runtime gate — the safe outcome. A future execution milestone must supply a
  machine-attested snapshot; that milestone, not M44, would carry any execution
  authority.
- The operator signature is a deterministic HMAC (shared-domain), sufficient for
  tamper-evidence within this offline framework. It is **not** a public-key
  operator identity; a future milestone may upgrade it without changing M44's
  fail-closed contract.

## Conclusion

No authority is granted. All invariants are enforced structurally and covered by
tests. Fail-closed behavior is preserved end-to-end.
