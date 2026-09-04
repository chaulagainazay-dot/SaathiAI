# Test Report

Interpreter: `~/SaathiAI/.venv/bin/python` (CPython 3.12.13).
Worktree: `~/SaathiAI-tnext4`, branch `feature/t-next-4-execution-integrity`.

## Before the fix

| Run | Result |
|---|---|
| `pytest tests -q` (attempt 1) | stalled at 32 %, killed |
| `pytest tests -q` (attempt 2) | stalled at 32 %, killed |
| `pytest tests -q -k "not browser and not live and not network"` | stalled, killed at deadline |
| minimal two-test pair | **deadlock, never returns** |

No summary line was ever produced.

## After the fix

### Full unfiltered suite

```
pytest tests -q --no-header --durations=15
→ 7642 passed, 2 skipped, 324 warnings in 667.63s (0:11:07)
```

### Canonical offline suite

```
pytest tests -q --no-header -m "not browser and not live and not external and not network"
→ 7630 passed, 2 skipped, 12 deselected, 324 warnings in 668.23s (0:11:08)
```

Collection: **7632 / 7644 selected, 12 deselected.**

| Metric | Value |
|---|---|
| collected | 7644 |
| selected | 7632 |
| passed | **7630** |
| failed | **0** |
| skipped | 2 |
| deselected | 12 |
| xfailed | 0 |
| warnings | 324 |
| duration | **668.23 s (11 m 08 s)** |

`OFFLINE_REGRESSION_SUITE_PASS`.

## Trading regression after the infrastructure change

| Suite | Result |
|---|---|
| T-NEXT-4 execution integrity (`tests/execution_integrity`) | **82 passed**, 0.39 s |
| T-NEXT-4.1 reconciliation gate (`tests/test_t_next_4_1_reconciliation_gate.py`) | **15 passed**, 0.24 s |
| Combined trading regression — paper broker, fund ledger, portfolio construction, portfolio risk, portfolio performance, trading guardian, paper activation, paper simulation, paper validation, ledger cutover, execution gateway, portfolio | **340 passed**, 4.24 s |

**Zero trading regression.**

## Slowest tests (unfiltered run)

| Duration | Test |
|---|---|
| 18.31 s | `test_m357_agentdev_adversarial::test_live_model_attacks_are_still_held_by_the_system` |
| 14.55 s | `test_m17_14_mission_scheduler::test_control_center_scheduler_attention_and_owner_scope` |
| 14.35 s | `test_m17_13_mission_engine::test_control_center_surfaces_failed_and_pending_missions` |
| 14.25 s | `test_m17_15_pipeline_recovery::test_control_center_recovery_attention_owner_safe` |
| 14.24 s | `test_m17_12_harness_pipeline::test_control_center_surfaces_failed_pipeline` |
| 13.68 s | `test_ops::test_release_gate_passes_baseline` |

Fifteen tests exceed 7 s. Not addressed — out of scope, recorded as an
optimisation opportunity.

## Syntax errors (Phase 13)

```
python -m compileall -q . -x "node_modules|/\.venv|/\.git"
→ exit 0, no output
```

**Zero syntax errors** across the entire repository, including paths excluded
from earlier scans. The two pre-existing syntax errors referenced in the mission
brief **do not reproduce in this worktree**. Nothing was fixed, because there was
nothing to fix. If they were real, they existed on a different branch or worktree.

## Lint availability (Phase 14)

| Tool | Status |
|---|---|
| `ruff` — project-local `.venv` | **absent** |
| `ruff` — shared `~/SaathiAI/.venv` | **absent** |
| `ruff` — global `PATH` | **absent** |
| `[tool.ruff]` in `pyproject.toml` | **not configured** |
| `eslint` — declared in `saathi-os/package.json` (`"lint": "eslint . --max-warnings 5"`, eslint ^9.39.5) | declared but `node_modules` **not installed** |

Nothing was installed. Python lint is unavailable and unconfigured; JS lint is
configured but its dependencies are absent. Neither blocks this certification.
