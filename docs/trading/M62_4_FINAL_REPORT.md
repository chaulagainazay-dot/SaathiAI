# M62.4 — Final Report: Deterministic Strategy Versioning & Bias-Resistant Backtesting

**Verdict: `M62_4_COMPLETE` (backend-certified; browser workspace deferred).**

## 1–4. Baseline / commits

* Starting branch: `milestone/m61-backend-workflow-persistence`
* Starting HEAD: `35587f9`
* Ending HEAD: this commit (`feat(trading): add deterministic strategy backtesting`)
* Unrelated preserved: `docs/design-spec/` — untouched, unstaged.

## 5. Reuse audit

| Component | Disposition |
|-----------|-------------|
| `trading_models.py` (M62.1) | REUSE_DIRECTLY — `Decimal`, enums, `D`, `Instrument`, `MarketState` |
| `trading_guardian.py` (M62.1) | REUSE_DIRECTLY — simulation-level veto via `guardian_sim` (never execution) |
| `market_data/` (M62.2) | REUSE_DIRECTLY — `MDBar`, `Timeframe`, `build_bars`, `dataset_hash`, `classify_series`, fixtures, replay |
| `research/` (M62.3) | REUSE_WITH_ADAPTER — read-only thesis reference |
| platform `models/context/api/store/service` | REUSE_DIRECTLY — permissions, context, audit, routing |
| M5 `investment.py`, `portfolio.py` | LEGACY_ISOLATED — not wired |
| M5 `execution/trade.py` | UNSAFE — imports broker connectors; not wired |
| `investment_pipeline.py`, `investment_learning.py` | OUT_OF_SCOPE |

## 6. Legacy strategy disposition

No legacy strategy/backtest engine existed. The M5 investment/portfolio/execution
stack is decision-support with approval-gated broker connectors and was **not** wired
in — a parallel simulation-only engine was built instead, per authority boundaries.

## 7. New modules

`saathi/platform/strategy/{models,features,signals,sizing,execution_model,accounting,
metrics,validation,walk_forward,stress,engine,store,service,guardian_sim,fixtures,__init__}.py`;
`tests/test_m62_4_strategy.py`; 6 docs + `docs/trading/m62_4_evidence/`.

## 8–15. Domain / lifecycle / interface / features / look-ahead / splits / walk-forward / execution

See `STRATEGY_AND_BACKTESTING.md`, `BACKTEST_BIAS_CONTROLS.md`, `TRANSACTION_COSTS.md`,
`WALK_FORWARD_VALIDATION.md`. Declarative strategies (no arbitrary code); structural +
runtime look-ahead guards; chronological non-overlapping splits; expanding/rolling
walk-forward; conservative next-bar fills.

## 16–20. Costs / slippage / accounting / metrics / sufficiency / sensitivity / stress

Configurable fee + slippage + volume-participation models across zero/realistic/stressed
tiers. Average-cost, long-only accounting with four reconciliation invariants (all valid
runs clean). Metrics carry value + status + required samples + warnings; zero denominators
return `UNDEFINED`, never `inf`. Sufficiency + bias outcomes. Sensitivity cliff detection.
Stress across ten M62.2 regimes.

## 21. Broken-strategy detection

All ten certification fixtures fail for the expected reason — see
`docs/trading/m62_4_evidence/broken_strategy_matrix.json`:
LOOK_AHEAD (runtime reject), FUTURE_RETURN_FEATURE / UNBOUNDED_POSITION_SIZE /
EXCESSIVE_LEVERAGE_REQUEST (structural reject), DUPLICATE_ORDER (deduped to one entry),
ZERO_COST_DEPENDENT (cost_sensitive), SINGLE_TRADE_OVERFIT (FAILED_BIAS_CHECK),
TEST_SET_TUNED (per-fold flag), MISSING_DATA_IGNORER (gap surfaced), INVALID_PRICE_ACCEPTOR
(data-quality reject).

## 22. Research integration

Strategies reference M62.3 theses read-only; `_resolve_thesis` records version +
publication state and marks `authoritative` only when PUBLISHED and not expired.
Unpublished/expired ⇒ non-authoritative context. Research never becomes market data and
cannot define strategy logic.

## 23. Guardian integration

`guardian_sim.simulate_guardian_review` runs the fail-closed Trading Guardian against a
SIMULATION-environment synthetic intent for risk review only. Result is tagged
`SIMULATION_ONLY`, `is_trade_approval=False`. Never calls ExecutionGateway.

## 24. Persistence

SQLite, tenant-scoped by `org_id`; optimistic concurrency on the mutable definition and
run; immutable strategy versions and completed run manifests; bounded pagination;
restart recovery proven.

## 25. APIs & permissions

`POST/GET/PATCH /strategies`, `/strategies/{id}/versions`, `/strategies/{id}/backtests`,
`/backtests run|cancel`, and evidence GETs (metrics/trades/equity/validation/stress/
sensitivity/manifest). No order/broker endpoints. Permissions: `STRATEGY_READ`,
`STRATEGY_CREATE`, `STRATEGY_EDIT`, `BACKTEST_RUN`, `BACKTEST_REVIEW`,
`STRATEGY_VALIDATE` (owner+; no self-certification).

## 26. Determinism evidence

3× identical `result_hash` — `docs/trading/m62_4_evidence/determinism_proof.json`.
Canonical manifest: strategy hash, dataset hash, engine/feature version, cost + slippage
models, calendar, seed, split, parameters, result hash.

## 27–35. Tests

`tests/test_m62_4_strategy.py`: **47 passed** (unit, persistence, integration,
adversarial, HTTP). Regression: **113 passed** combined (M62.4 + M62.3 + M62.2 + M62.1 +
M61 + M50); platform `-k` sweep 95 passed. See `regression_summary.json`.

## 36. Browser scope

`BACKEND_CERTIFIED` · `BROWSER_WORKSPACE_DEFERRED` (Option A). No UI shipped this
milestone.

## 37–40. Regression / security / limitations / working tree

Security scan CLEAN — `security_scan.json` (no ExecutionGateway/broker/order-submission/
eval/exec/subprocess/network/dynamic-import in code). Limitations: deterministic fixtures
only, bar-based simulation, single-host SQLite, no external provider, no optimizer, no
profitability proof. Working tree: only M62.4 additions + additive edits to
`api.py`/`models.py`; `docs/design-spec/` untouched.

## 41. Push/merge/deploy

None. No push, merge, or deployment performed or authorized.

## 42. Recommended M62.5 scope

Minimal read-only Strategy Lab browser workspace (list/definition/versions/run
status/metrics/equity/validation/stress/sensitivity/manifest, labelled SIMULATION ONLY,
no buy/sell); optional bounded parameter optimizer with overfit penalties; portfolio-of-
strategies allocation simulation (still no execution).

## 43. Final authority statement

```
PlatformAgentRuntime remains the canonical agent runtime.
ExecutionGateway remains the sole authority for registered tool execution.
Trading Guardian remains an independent fail-closed veto layer.
M62.4 evaluates versioned strategies through deterministic simulation only.
Backtest results do not constitute trading approval, investment advice, profitability
proof, or authorization to allocate capital.
No paper order, broker access, live trading, leverage, margin, short-selling,
derivatives, production deployment, or autonomous capital use is authorized.
Services remain localhost-only.
No push, merge, deployment, or external rollout authority is granted.
```
