# Test Report

Interpreter: `~/SaathiAI/.venv/bin/python` (CPython 3.12.13).
Worktree: `~/SaathiAI-tnext4`, branch `feature/t-next-4-execution-integrity`.

## Canonical offline suite

```
pytest tests -q --no-header -m "not browser and not live and not external and not network"
→ 7641 passed, 2 skipped, 12 deselected, 324 warnings in 643.76s (0:10:43)
```

| Metric | TEST-INFRA-1 | TEST-INFRA-2 |
|---|---|---|
| passed | 7630 | **7641** (+11 isolation tests) |
| failed | 0 | **0** |
| skipped | 2 | 2 |
| deselected | 12 | 12 |
| duration | 668 s | 644 s |

## Trading regression

```
tests/execution_integrity · test_t_next_4_1_reconciliation_gate · fund_ledger ·
portfolio_construction · portfolio_risk_engine · portfolio_performance ·
test_m62_5_paper_broker · test_m62_6_reconciliation · test_m166_m175_trading_guardian ·
test_execution_gateway · test_m200_m207_durable_paper · test_t_next_1_1_ledger_cutover
→ 294 passed, 0 failed, 7.02s
```

**Zero trading regression.**

## New tests

`tests/test_infra/test_state_isolation.py` — 11 tests:

- symlinked `$HOME` still protects user config (the security regression)
- `_home()` resolution is symlink-stable
- four protected surfaces stay protected under a redirected home
- HOME is redirected for the session, and is not the real user home
- `SAATHI_EVIDENCE_ROOT` is redirected, and seeded with the committed tree
- `SecurityStore()` default is isolated

The symlink test asserts the temp directory really *is* symlinked, and fails
loudly on a platform where the regression cannot be reproduced, rather than
passing vacuously.

## Working-tree invariant

After the full run:

```
git status --porcelain   → only the 7 files this milestone edited
docs/evidence/**         → clean
~/.saathi                → untouched
```

Enforced in CI by a dedicated step that fails the build if a test run mutated
tracked files.

## Failures encountered and resolved during the milestone

Recorded because both were real, and both were caused by this work:

| # | Failure | Cause | Resolution |
|---|---|---|---|
| 1 | `test_ops::test_release_gate_passes_baseline` → exit 8 | First attempt redirected each module's `ROOT`, but `ROOT` is the *repository* root used for subprocess cwd, source scanning and `relative_to` — not only evidence | Kept `ROOT` as the repo root; introduced a separate `EVIDENCE_ROOT`; conftest seeds the isolated root by copying the committed tree, because gates read it |
| 2 | **32 failures** across 8 agentdev files | HOME redirect exposed a latent production defect: `config_protection._home()` compared an unresolved home against a resolved candidate, so a symlinked `$HOME` classified `~/.claude/settings.json` as UNPROTECTED | Fixed `_home()` to resolve; added regression tests. See `SECURITY.md` |

Neither was worked around. The intermediate 32-failure state is reported here
rather than omitted.

## Fresh-context review

An independent session reviewed the isolation change cold against four
questions. It cleared three categories and found one real gap:
`saathi/inference/ops/state.py` wrote to the tracked `docs/evidence/m26` tree and
was the only module in that family without the override — a live trap, since
`InferenceOpsService()` defaults to it. Fixed, and a repo-wide sweep for other
`docs/evidence` writers was run afterwards.

## Syntax and lint

`compileall` across the repository: **exit 0, zero errors**.
`ruff`: still absent and unconfigured. `eslint`: declared in
`saathi-os/package.json`, `node_modules` not installed. Nothing installed.
