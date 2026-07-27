# M62.5 Reuse & Legacy-Isolation Audit

| Component | Disposition | Notes |
|---|---|---|
| `saathi.platform.trading_models` (`OrderIntent`, `OrderSide`, `OrderType`, `TimeInForce`, `Environment`, `DataQuality`, `MarketState`, `D`) | **REUSE_DIRECTLY** | `OrderIntent` is the canonical proposal object; Guardian-compatible. |
| `saathi.platform.trading_guardian.TradingGuardian` | **REUSE_DIRECTLY** | Independent fail-closed veto invoked before every submission (`_guardian_review`). |
| `saathi.platform.market_data` (`MDQuote`, `MDBar`, `DataQuality` mapping) | **REUSE_WITH_ADAPTER** | `broker.from_quote` / `from_bar` adapt canonical M62.2 data into `MarketEvent`. |
| `saathi.platform.strategy.accounting.PortfolioAccountant` | **REUSE_WITH_ADAPTER** (conceptual) | Durable paper accounting mirrors its average-cost/invariant approach; the paper broker keeps its own durable, restart-safe ledger (no backtest run-state shared). |
| `saathi.platform.models` (RBAC, `ApprovalRecord`, `new_id`) | **REUSE_DIRECTLY** | Added 7 `PAPER_*` permissions + role wiring; reused the Approval Center. |
| `saathi.platform.context.PlatformExecutionContext` | **REUSE_DIRECTLY** | Identity + `require_permission` on every service method. |
| `saathi.execution.gateway.ExecutionGateway` (`execute_registered_tool`) | **REUSE_DIRECTLY** | Sole mutation authority; orchestration routes through it. |
| `saathi.tool_runtime` (registry, `ToolManifest`, `ToolExecutionService`, `ToolApprovalReference`) | **REUSE_DIRECTLY** | Paper tools registered via `register_paper_tools` in `bootstrap.register_builtins`. |
| `saathi.platform.store.PlatformStore` (`consume_approval_if_approved`, `append_audit`) | **REUSE_DIRECTLY** | Server-owned approval consumption + audit sink. |
| `saathi.platform.strategy.guardian_sim` | **OUT_OF_SCOPE** | Backtest-domain synthetic-intent Guardian; the paper broker uses the real Guardian against real account/market state. |
| `saathi.execution.trade` (legacy M5 financial stack) | **LEGACY_ISOLATED** | Not imported by `api.py` or `paper_trading`; remains unreachable. Not wired in. |
| `saathi.tool_runtime` `m49.financial_execution_stub` | **UNSAFE (prohibited)** | Manifest `PROHIBITED`; verified blocked (`test_financial_execution_tool_prohibited`). |

## Isolation verified

- `research/service.py` and `strategy/service.py` do **not** import `paper_trading`
  (`test_no_broker_import_in_research_or_strategy`).
- No API route calls `PaperBroker` / `PaperTradingService.submit_order` directly —
  mutations go through `orchestration` → `ExecutionGateway.execute_registered_tool`.
- No public listener, deployment config, or production authority changed.
