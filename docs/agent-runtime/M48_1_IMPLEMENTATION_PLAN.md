# M48.1 — Implementation Plan

## Selected slice

```text
canonical run contract types + fail-closed validation
(saathi/agent_runtime/contracts.py + tests)
```

## Why canonical

Reuses M10 `RunState` / `RiskClass` / transitions / RunStore / Orchestrator / ExecutionGateway without a parallel runtime.

## Why bounded

Validation-only library; no network; no credential use; no orchestrator rewrite; no trading engagement.

## Reused components

`models.py`, `policy.py`, `store.py`, `orchestrator.py`, `execution.gateway`, `model_router.py`, existing CLI.

## Files

| File | Action |
|---|---|
| `saathi/agent_runtime/contracts.py` | add |
| `tests/test_m48_1_agent_runtime_contracts.py` | add |
| `saathi/agent_runtime/cli.py` | additive `contract` command + inspect field |
| `docs/agent-runtime/M48_1_*.md` | add |
| `docs/ui-ux/M47_POST_MERGE_RELIABILITY_CONFIRMATION.md` | add |

## Tests required

Negative cases: unknown capability/authority, financial prohibited, missing/expired/revoked approval, invalid transitions, terminal restart, timeout/retry bounds, secret fields, provider unavailable ≠ success.

## Stop conditions

Do not implement full orchestration, provider calls, trading, or M48.2 wiring.
