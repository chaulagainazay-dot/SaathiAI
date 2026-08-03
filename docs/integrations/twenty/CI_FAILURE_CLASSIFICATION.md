# M361B CI failure classification

Assessment time: `2026-08-03T13:07:51Z`

Required output: `CI_GAP_REQUIRES_SEPARATE_REPAIR`

Primary classification: `PRE_EXISTING_BASELINE_FAILURE`

## Evidence

| Item | Finding |
| --- | --- |
| M360 closure run | Reliability run `30809497607` at `12be0aa18cc88d81c1186998454cdd1497d06fd5` failed |
| M361A ending run | Reliability run `30812211970` at `7b7d4a422c54c40111f3755e7775445f5cd75c9f` failed |
| Selected-base run | Reliability run `30553847890` at base SHA `6639ca730ece11bce160a55a237fcaff8df3058c` failed |
| Blocking manifest item | `ops.hardening_m13_5` |
| Exact test | `tests/test_ops.py::test_release_gate_passes_baseline` |
| Exact failure | release gate returned `3`; assertion expected `0` or `1`; `1 failed, 24 passed` |
| Exit-code source | `EXIT_SECURITY = 3` in `saathi/ops/release_gate.py` |
| Local reproduction | Same assertion failed using the existing repository virtual environment |
| Local release report | Storage, config, database, and backup/restore passed; secret scan reported two strong findings |
| Flagged tracked files | `saathi/platform/tg/broker_readiness/security.py` and `saathi/platform/tg/integration_assurance/security.py`, rule `private_key_block` |
| Twenty relevance | Neither flagged file, `saathi/ops/release_gate.py`, nor `tests/test_ops.py` differs from the selected base |

The same test and manifest item failed on the selected base before the Twenty
branch changes. The Twenty diff adds its integration package, focused test,
fixtures, and documentation; it does not alter the scanner, release gate, test,
or flagged Trading Guardian files. The branch run reported the Twenty-focused
connector, webhook, scope, approval, secret-redaction, execution-boundary, and
authority checks as passing.

## Decision

This is not `TWENTY_CHANGE_CAUSED`, `BASE_BRANCH_MISMATCH`,
`STALE_GENERATED_EVIDENCE`, or evidence of nondeterminism. It is a reproducible,
pre-existing secret-scan false-positive or fixture-pattern defect in an unrelated
baseline area. Twenty publication evidence remains meaningful, but the repository
required check is still red and cannot be called resolved.

Repair belongs on the authoritative baseline/Trading Guardian maintenance path,
where the scanner rule and the two policy test strings can be reviewed together.
This branch must not suppress, skip, weaken, or relabel the test. M361 entry keeps
a `PENDING_SEPARATE_REPAIR` gate until that repair lands or repository policy
records a formal waiver.
