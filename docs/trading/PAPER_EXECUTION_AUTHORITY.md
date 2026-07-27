# Paper Broker — Execution Authority (M62.5)

The paper broker introduces **zero new execution authority**. Every mutation walks
the existing canonical chain; nothing bypasses it.

```
Agent / operator proposal
  → canonical OrderIntent (saathi.platform.trading_models.OrderIntent)
  → server authorization (PlatformExecutionContext.require_permission)
  → Trading Guardian review (independent, fail-closed veto)
  → approval verification + atomic consumption (server-owned Approval Center)
  → PlatformAgentRuntime
  → ExecutionGateway.execute_registered_tool
  → registered paper-trading tool (paper.order.submit / .cancel / .process_event)
  → PaperTradingService
  → PaperBroker (deterministic, stateless)
  → durable PaperOrder + deterministic PaperFill events
  → cash & position accounting
  → audit evidence
```

## Authority invariants

- `PlatformAgentRuntime` remains the canonical agent runtime.
- `ExecutionGateway` remains the **sole** authority for registered-tool execution.
- `TradingGuardian` remains an **independent, fail-closed** veto layer.
- `PaperBroker` operates **only** in `Environment.PAPER`.
- **No** API route, agent, browser, research module, or strategy module reaches the
  broker except through the registered tool under the Gateway.
  - API mutation endpoints (`/paper/order-intents/{id}/submit`,
    `/paper/orders/{id}/cancel`, `/paper/orders/{id}/process-event`) call
    `paper_trading.orchestration`, which calls
    `ExecutionGateway.execute_registered_tool`. They never touch `PaperBroker` or
    `PaperTradingService.submit_order` directly.
  - `saathi/platform/research/service.py` and `saathi/platform/strategy/service.py`
    do not import `paper_trading` (verified by test
    `test_no_broker_import_in_research_or_strategy`).

## Registered tools (code-owned manifests)

| tool_id | authority | side effect | approval | idempotency |
|---|---|---|---|---|
| `paper.order.submit` | `LOCAL_MUTATION` | `LOCAL_IRREVERSIBLE` | `EXPLICIT_APPROVAL_REQUIRED` | key required |
| `paper.order.cancel` | `LOCAL_MUTATION` | `LOCAL_REVERSIBLE` | `NO_APPROVAL_REQUIRED` | natural |
| `paper.order.process_event` | `LOCAL_MUTATION` | `LOCAL_IRREVERSIBLE` | `NO_APPROVAL_REQUIRED` (system, bounded) | natural |

Authority is deliberately **`LOCAL_MUTATION`**, never `FINANCIAL_EXECUTION` — a paper
fill mutates only local SQLite simulation state. `FINANCIAL_EXECUTION` remains
manifest-prohibited and unregisterable (M49.1 `validate_manifest`).

## Disabled capabilities (fail closed)

`assert_paper_safe()` refuses construction or configuration that enables any of:
`LIVE, PRODUCTION, REAL_MONEY, LIVE_BROKER, LEVERAGE, MARGIN, SHORT_SELLING, OPTIONS,
FUTURES, PERPETUALS, DERIVATIVES, BORROWING`, or any non-`PAPER` environment.

No provider API keys, no broker credential storage, no external network calls,
no dormant live-trading code. Services remain localhost-only.
