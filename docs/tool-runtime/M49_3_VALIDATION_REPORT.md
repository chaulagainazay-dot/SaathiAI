# M49.3 Validation Report

## Baseline (Phase 0)

- Branch start: `milestone/m49-2-tool-convergence` @ `d8492a8993de6ea4e83c59d9aea37440e1676ee3`
- M49.1 + M49.2 baseline: **67 passed**

## Focused M49.3

```text
pytest -q tests/test_m49_3_*.py
```

Expected: gateway, legacy, shell, connector authority/approval/dry-run, cancellation, compatibility, domain, trading.

## Regression

```text
pytest -q tests/test_m49_1_*.py tests/test_m49_2_*.py tests/test_m48_*.py tests/test_tool_governance.py
```

Combined local run (M48 + M49 + governance + M49.3): **181 passed**.

## Audits (read-only CLI)

```bash
python -m saathi.agent_runtime.cli tools audit-gateway
python -m saathi.agent_runtime.cli tools audit-legacy
python -m saathi.agent_runtime.cli tools audit-connectors
python -m saathi.agent_runtime.cli tools audit-cancellation
python -m saathi.agent_runtime.cli tools audit-approvals
```

Observed:

| audit | status |
|---|---|
| gateway | PASS / TOOL_GATEWAY_ENFORCED |
| legacy | PASS |
| connectors | PASS / DRY_RUN_ONLY / generic ABSENT |
| cancellation | PASS / unknown=0 |
| approvals | PASS |

## Frontend / full suite / CI

Recorded in final report after full validation commands complete.
