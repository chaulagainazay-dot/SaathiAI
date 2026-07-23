# M48.2 — Legacy Runtime Boundary

## May bypass start_agent_run (documented)

| Path | Why allowed | Privilege risk |
|---|---|---|
| `RunStore.create_run` in unit tests | store-level tests | low (test only) |
| `create_run(..., skip_contract=True)` | explicit low-level | **must not** be used by API |
| M8 `run_agent` | single chat agent, gateway chat path | not multi-agent orchestrator |
| IELTS `saathi.agents` | domain product | isolated; not general runtime |
| Finance `ExecutionService` | separate trade stack | must stay paper/advisory for TG |

## Bypasses blocked

- HTTP `/api/v1/agents/runs` cannot skip contracts.
- Chat multi-agent orchestration cannot skip contracts.
- `Orchestrator.create_run` validates by default.

## Removal prerequisites (future)

Migrate M8 multi-agent usage, retire skip_contract from production code paths, wrap IELTS if generalized.
