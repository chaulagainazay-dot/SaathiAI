# M49.3 Security Review

## Findings

| ID | Severity | Topic | Status |
|---|---|---|---|
| S1 | CRITICAL | Freeform shell (`shell=True` / arbitrary command) | **RESOLVED** — blocked at `run_shell`, `project_run`, `applescript`, `run_bounded` |
| S2 | CRITICAL | Financial execution reachability | **RESOLVED** — manifest PROHIBITED; adapter never invoked |
| S3 | HIGH | Generic connector executor | **RESOLVED** — absent; action-specific tool_ids only |
| S4 | HIGH | Approval scope widening | **RESOLVED** — action/target/tool_id/expiry/revocation checks |
| S5 | HIGH | Credential leakage in tool args | **RESOLVED** — secret policy + redaction |
| S6 | HIGH | Dry-run escape to live mutation | **RESOLVED** — adapters hard-code network/mutation false |
| S7 | MEDIUM | Legacy residual tools still executable | **ACCEPTED_LIMITATION** — LEGACY_BOUNDED with deprecation; deferred domains disabled |
| S8 | MEDIUM | Multi-host idempotency | **ACCEPTED_LIMITATION** — single-host durable SQLite |
| S9 | MEDIUM | Cancellation on non-subprocess tools | **RESOLVED** for supported set; UNKNOWN forbidden |
| S10 | LOW | Compatibility bridge retained | **ACCEPTED_LIMITATION** — map-specific only |

## Critical unresolved

None.

## High unresolved

None requiring block. Residual LEGACY_BOUNDED catalog is documented limitation → `M49_3_COMPLETE_WITH_LIMITATIONS`.

## Negative coverage

Covered in `tests/test_m49_3_*.py`: freeform shell, shell metacharacters, unapproved executable/cwd/env, generic connector absent, approval mismatches, credential rejection, financial prohibition, dry-run non-mutation, deferred domain disable.
