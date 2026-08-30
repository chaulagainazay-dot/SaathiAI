# Test Report

Interpreter: `~/SaathiAI/.venv/bin/python` (CPython 3.12.13).
Worktree: `~/SaathiAI-tnext4`, branch `feature/t-next-4-execution-integrity`,
base `integration/saathios-trunk-v3` @ `4756ece`.

## Baseline before any change

```
tests/fund_ledger tests/portfolio_construction tests/portfolio_risk_engine
tests/test_m62_5_paper_broker.py tests/test_m62_6_reconciliation.py
tests/test_m200_m207_durable_paper.py tests/test_t_next_1_1_ledger_cutover.py
→ 146 passed in 4.23s
```

Taken deliberately before touching anything, so the two defect fixes could be
shown not to change existing behaviour.

## New suites added by this mission

`tests/execution_integrity/` — **82 passed**

| File | Tests | Covers |
|---|---|---|
| `test_submission_disposition.py` | 20 | Phase 4 — disposition mapping, durable attempt ledger, `may_submit` gate, reconciliation clearance, plus 2 regressions from fresh-context review |
| `test_reconciliation_authority.py` | 21 | Phase 8 — readiness verdicts, fail-closed permission, immutability, evidence, plus 2 regressions from fresh-context review |
| `test_failure_matrix.py` | 21 | Phase 14 — F1…F20 |
| `test_security_authority.py` | 19 | Phase 15 — authority boundary, LLM exclusion, TradingAgents exclusion, paper-only, determinism |

Written **before** the implementation, per Phase 16. The implementation was
then written to satisfy them.

## Final targeted regression (post-fix, post-review-fixes)

```
tests/fund_ledger tests/portfolio_construction tests/portfolio_risk_engine
tests/portfolio_performance tests/test_m62_5_paper_broker.py
tests/test_m62_6_reconciliation.py tests/test_m200_m207_durable_paper.py
tests/test_m192_m199_paper_activation.py tests/test_m288_m295_paper_simulation.py
tests/test_m166_m175_trading_guardian.py tests/test_m176_m183_paper_validation.py
tests/test_m296_m303_portfolio_risk.py tests/test_t_next_1_1_ledger_cutover.py
tests/test_execution_gateway.py tests/test_portfolio.py tests/execution_integrity
→ 340 passed, 18 warnings in 4.02s
```

258 pre-existing trading tests + 82 new. **Zero regressions** from the two
production fixes.

## Full-repository suite — PARTIAL, 84% reached, zero failures

`pytest tests` (378 test files) was attempted three times.

1. Unfiltered run — stalled at ~0.1% CPU after ~3 minutes of CPU time,
   consistent with a network- or IO-bound test blocking. Killed.
2. Second unfiltered run — same stall. Killed.
3. Bounded run with a 900 s deadline and `-k "not browser and not live and not
   network and not http_paper"`, `--ignore=tests/evaluation`. **Reached 84% of
   collected tests and was then cut by the deadline.**

Result of run 3, measured from the captured output:

```
progress reached          [ 84%]
FAILED / ERROR lines       0
F / E / s progress markers 0
```

**No failure or error marker appeared in any of the 84% that executed.** There is
no pytest summary line, so there is no final count — the run was terminated, not
completed.

**This is reported as a partial pass, not a full-suite pass.** The certification
rests on the targeted suites above (340 passed, complete runs with real numbers).
The remaining 16% is unverified, and the stall itself is an unresolved
environment issue worth a separate look — a test that hangs on network access is
a problem regardless of this mission.

## Fresh-context adversarial review (Phase 16)

A separate Claude session with no knowledge of this work reviewed
`execution_integrity.py` cold and was asked only for concrete defects. It found
**three real ones**, all in code written by this mission:

| # | Defect | Severity | Status |
|---|---|---|---|
| R1 | `may_submit` short-circuited on an empty attempt list before consulting the reconciliation table. A reconciliation row proving an order reached the venue, with no attempt row under that key, would have permitted a duplicate submission. | High | **Fixed** + regression test |
| R2 | The ambiguity check merged the OMS and external order dicts. The external entry overwrote the OMS entry for the same order id, so an OMS order in `UNKNOWN` could be masked by a healthy venue state and fall through to `RECONCILED` with execution permitted. `_IN_FLIGHT_STATES` also does not contain `UNKNOWN`, so nothing downstream caught it. | **High — the exact failure the module exists to prevent** | **Fixed** + 2 regression tests (both directions) |
| R3 | `record()` used check-then-insert on `request_id`, which races: two concurrent callers both pass the SELECT and the second raises `IntegrityError` instead of returning the existing row, contradicting its documented idempotency. | Medium | **Fixed** (`ON CONFLICT DO NOTHING` + re-read) + regression test |

It also correctly noted that the module docstring claimed "anything short of
RECONCILED denies readiness" while `allow_execution_while_pending=True` permits
`TEMPORARILY_PENDING`. The docstring was corrected to state the exception
explicitly.

R2 is the reason this phase exists. The original code passed all 78 tests written
for it; it took an independent reader to see that the dict merge silently
discarded one side's view.

## ECC harness

The hardened ECC profile is **project-scoped to `~/SaathiAI`** and therefore did
not load in the `~/SaathiAI-tnext4` worktree. ECC's disciplines were applied
manually rather than through its tooling: invariant tests before implementation,
fresh-context review after implementation, security review, and verification
before certification. No ECC configuration was changed by this mission
(`ecc@ecc` remains installed-but-disabled, 0 chrome-devtools MCP entries).
