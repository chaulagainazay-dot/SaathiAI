# M40 — Security Audit

**Scope:** `saathi/credentials/m40.py` + `m40-*` CLI. Composition-only layer over
M31–M39. No architecture change.

## Invariants preserved (verified by tests)

| Invariant | Mechanism | Test |
|-----------|-----------|------|
| Fail-closed | Stage 1 blocks on any missing ack/auth/env/reference | `test_stage1_fails_closed_on_each_missing` |
| Reference-only secrets | `_secret_reference_supplied` rejects raw/token-shaped locators and `IN_MEMORY_TEST` | `test_stage1_rejects_raw_secret_locator` |
| No raw-secret logging/persistence/serialization | outputs carry `contains_secret_values:false`; locator fingerprinted, never echoed | `test_no_secret_in_certification_output` |
| SecretHandle destruction | stage 3/5 assert `handle_closed` even on interruption/401 | `test_interruption_single_session_cleans_up`, `test_stage5_rehearsal_revocation_401_cleanup` |
| Lease isolation | stage 4 requires distinct session + correlation ids + result isolation | `test_stage4_rehearsal_isolation` |
| Budget limits | stage 3 asserts `call_budget_used <= max` | `test_stage3_rehearsal_cleanup_and_simulated` |
| Kill switch | active env forces `LIVE_BLOCKED` | `test_kill_switch_blocks_certification` |
| Allowlist / least privilege | provider `github_meta`, read-only `/user`,`/meta`; preflight rejects synthetic backend | `test_stage2_rejects_synthetic_backend` |
| Deny-by-default | verdict defaults to BLOCKED; certification never inferred | `test_no_credential_blocks` |
| No canary/active/write | all `grants_*` hardcoded false | `test_never_grants_anything` |

## Threat cases

- **Forged "complete" config, no real secret** → stage 3 `BLOCKED` (secret_ref_missing);
  no network reached; verdict `LIVE_BLOCKED`; not certified.
  (`test_forged_complete_config_missing_secret_blocks_not_certifies`)
- **Raw token as locator** → rejected before any use (argv guard + `_secret_reference_supplied`).
- **Certified-without-live** → CLI aborts (exit 2) if `live_certified` true while
  `live_exercised` false. Code path cannot set `live_certified` without `live_network`.
- **Kill switch** → immediate `LIVE_BLOCKED`.

## Production-safety confirmations

M40 does not push git, merge, deploy, enable production/canary/active, modify or
create/destroy infrastructure, rotate secrets, or store credentials. The revocation
stage records operator confirmation only — SaathiOS has no token-delete authority
(`saathios_has_token_delete_authority:false`).

## Residual risk

Live certification cannot be completed offline. The single residual dependency is
operator-controlled: supply a disposable, read-only sandbox secret reference and run
the live window. Until then, `LIVE_BLOCKED` is the correct, honest state.

## Trading Guardian

UNCHANGED / UNENGAGED. No provider receives write authority.
