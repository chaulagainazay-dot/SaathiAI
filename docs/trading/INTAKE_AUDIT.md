# M62.0 — Trading & Research Intake Audit (read-only, evidence-based)

Baseline: branch `milestone/m61-backend-workflow-persistence`, HEAD `cdfee54`
(verified). Method: traced actual imports, call paths, API exposure, UI, config,
and tests — not filenames or comments.

## Key structural finding

Two lineages cohabit `saathi/execution/`:
1. **M5 "Financial Intelligence" stack** — `execution/trade.py` (`ExecutionIntent`
   → broker `Connector` → `ExecutionService`, paper-first, approval-gated),
   `investment.py`, `investment_pipeline.py`, `portfolio.py`, `research.py`,
   `trade_journal.py`. Has its own tests (`test_execution.py`, `test_trade_journal.py`,
   `test_m5_explainability.py`).
2. **Platform ExecutionGateway** — `execution/gateway.py` (`ToolIntent` → validate →
   authorize → risk → approve → execute → sanitize → evidence), used by
   `PlatformAgentRuntime` (`runtime.py:799 from saathi.execution import ExecutionGateway`).

**Reachability (safety-critical):** the M5 finance stack is **NOT exposed via any
HTTP endpoint** (no `/trade`,`/order`,`/broker`,`/portfolio`,`/invest` route in
`server.py` or `platform/api.py`) and is **NOT a registered platform tool**. It is
therefore **not reachable** from the browser, an agent, or the platform API →
no alternate execution path is exposed. Gateway does not import `trade.py`.

`/trading` UI (`saathi-os/app/trading/page.jsx`) = "Trading Guardian" advisory-only
`BlockedState`: no order buttons, no broker prompts, no fake prices/positions.
`trading_guardian` config = `ADVISORY_ONLY` (config PATCH rejects any other value).

## Capability matrix (original, verified)

| Capability | State | Evidence |
|---|---|---|
| Platform trading execution path | MISSING / DISABLED | no API, guardian advisory, no registered tool |
| M5 paper execution (`execution/trade`) | PARTIAL (unwired) | exists + tested, not reachable from platform |
| M5 investment/portfolio/research | PARTIAL (unwired) | modules + tests, not platform-integrated |
| Canonical platform trading domain model | MISSING | `market_data`,`order_intent` = 0 files |
| Market-data layer (quality/replay) | MISSING | `market_data` 0 files |
| Backtesting framework | MISSING | `backtest` 0 files |
| Evidence-graded research pipeline | PARTIAL | M5 `research.py` + `deep-research` skill; not platform-integrated |
| Trading Guardian (risk-veto engine) | MISSING | only an advisory config flag + BlockedState UI |
| Broker adapters | PARTIAL | `credentials/broker.py`, binance refs; uncertified, unwired |
| Order state machine / reconciliation-for-trading | MISSING | `order_intent` 0 files |
| Approval-bound orders / paper broker (platform) | MISSING | — |

## Classification
- UNSAFE bypass exposed: **none found** (M5 stack unreachable).
- Placeholder-only: `/trading` UI (honest), `trading_guardian` flag.
- Missing foundations: market data, backtesting, canonical domain model, Guardian
  engine, paper broker, order lifecycle, reconciliation, research pipeline (platform).

## Sub-milestone plan (evidence-ordered)
- **M62.0 Intake audit — DONE (this doc).**
- **M62.1 Canonical domain models + Trading Guardian primitives — DONE** (pure,
  tested; `trading_models.py`, `trading_guardian.py`, 19 tests). No execution path.
- M62.2 Market-data quality + deterministic replay foundation — PENDING
- M62.3 Evidence-backed research pipeline — PENDING
- M62.4 Strategy versioning + deterministic backtesting — PENDING
- M62.5 Trading Guardian persistence + portfolio-risk wiring — PENDING
- M62.6 Approval-bound order-intent persistence + state machine wiring — PENDING
- M62.7 Deterministic in-process paper broker — PENDING
- M62.8 Reconciliation + recovery + circuit-breaker durability — PENDING
- M62.9 Agentic scheduling + monitoring — PENDING
- M62.10 Operator UI integration — PENDING
- M62.11 Adversarial security certification — PENDING
- M62.12 End-to-end paper-trading certification — PENDING
- M62.13 Final readiness review — PENDING
