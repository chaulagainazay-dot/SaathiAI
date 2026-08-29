# Current State — SaathiOS at Evaluation Time

Evaluation date: 2026-08-29
Mission: T-EVAL-TRADINGAGENTS (qualification only, no integration)

## Repository

| Field | Value |
|---|---|
| Path | `/Users/macbookpro/SaathiAI` |
| Branch | `milestone/m312-m319-connectivity-governance` |
| HEAD at start | `954daa45a33635ae9995f0d96bc37dc5658848b4` |
| Working tree | 31 pre-existing dirty paths, all unrelated to this mission, all preserved |
| Last commit | `954daa4 chore(agent-dev): integrate and harden ECC engineering harness` |

## Trading branches present

`feature/t-next-1-canonical-paper-ledger`, `feature/t-next-1-1-paper-ledger-cutover`,
`feature/t-next-2-independent-risk-engine`, `feature/t-next-3-portfolio-construction`,
`feature/t-next-4-performance-attribution`, plus
`milestone/m166-m175-trading-guardian-foundation`,
`milestone/m176-m183-trading-guardian-paper-validation`,
`milestone/m184-m191-trading-guardian-historical-research`.

No PR was opened, merged, or altered by this mission.

## ECC harness status (unchanged by this mission)

`ecc@ecc` 2.2.0, project scope, **disabled** (pinned vendor source). 0 chrome-devtools
MCP entries. ~7.5k always-on tokens. GateGuard and config-protection active.

## Canonical implementations — verified in the repository, not from memory

| Authority / capability | Verified location | Size |
|---|---|---|
| ExecutionGateway | `saathi/execution/gateway.py` (`class ExecutionGateway`) | 453 lines |
| Execution subsystem | `saathi/execution/` — `adapters/`, `orchestrators/`, `queue/`, `state.py`, `store.py`, `record.py`, `results.py` | — |
| Trading Guardian | `saathi/platform/trading_guardian.py` + `saathi/platform/tg/` (`service.py`, `domain.py`, `policy.py`, `kill_switch.py`, `risk.py`) | 166 lines + package |
| PortfolioRiskEngine | `saathi/portfolio.py` (`class PortfolioRiskEngine`) | 403 lines |
| Portfolio risk subsystem | `saathi/platform/tg/portfolio_risk/` — `analytics.py`, `attribution.py`, `limits.py`, `optimiser_v2.py`, `scenarios.py`, `sizing.py`, `committee_v2.py`, `certification.py` | — |
| Portfolio construction | `saathi/platform/tg/intelligence/portfolio_engine.py`, `research_lab/portfolio_builder.py`, `research_lab/allocation.py`; **`PortfolioConstructionEngine` proper lives on `feature/t-next-3-portfolio-construction`** | — |
| Fund / paper ledger | `saathi/platform/tg/paper_simulation/ledger.py`, `journal.py`, `exchange.py`, `matching.py`, `corporate_actions.py` | — |
| Paper trading | `saathi/platform/paper_trading/` — `broker.py`, `execution_tool.py`, `orchestration.py`, `reconciliation.py`, `store.py` | — |
| Market observation | `saathi/platform/tg/market_observation/` — `observation.py`, `certification.py`, `storage.py` | — |
| Market data | `saathi/platform/market_data/` and `saathi/platform/tg/market_data/` — `bias_controls.py`, `provenance.py`, `corporate_actions.py`, `adjustments.py`, `dataset_split.py`, `signal_validation.py`, `licensing.py`, `quality.py`, `reconciliation.py`, `normalization.py`, `calendar.py`, `feature_store.py`, `replay.py` | — |
| Historical / backtesting | `saathi/platform/tg/historical/` (`research.py`, `monte_carlo.py`, `qualification.py`, `normalize.py`, `calendars.py`), `tg/walk_forward.py`, `tg/intelligence/walk_forward_v2.py`, `tg/intelligence/backtest_v2.py`, `tg/stress_lab.py` | — |
| Research lab | `saathi/platform/tg/research_lab/` — `experiment_registry.py`, `experiment_runner.py`, `multiple_testing.py`, `robustness.py`, `regime_validation.py`, `stress_testing.py`, `certification.py`, `lineage.py`, `ensemble.py`, `optimisation.py`, `comparison.py`, `candidate_promotion.py`, `strategy_universe.py` | — |
| Research orchestration | `saathi/platform/tg/research_orchestrator/` — `scheduler.py`, `queue.py`, `workers.py`, `budget.py`, `sessions.py`, `journal.py`, `dependencies.py`, `estimator.py`, `templates.py`, `certification.py` | — |
| Agent intelligence (trading) | `saathi/platform/tg/intelligence/` — `committee.py` (`InvestmentCommittee`), `explainable.py`, `monte_carlo.py`, `strategy_registry.py` | committee 202 lines |
| Decision journal | `saathi/platform/tg/journal.py`, `research_orchestrator/journal.py`, `paper_simulation/journal.py` | 133 lines |
| Regime | `saathi/platform/tg/regime.py`, `research_lab/regime_classifier.py`, `research_lab/regimes.py` | 225 lines |
| Strategies | `saathi/platform/tg/strategies/` — `base.py`, `momentum_rs.py`, `trend_following.py`, `kotegawa_mean_reversion.py`, `no_trade.py` | — |
| Provider / model routing | `saathi/inference/` (~50 modules incl. `registry.py`, `provider_descriptor.py`, `provider_policy.py`, `governance_service.py`, `circuit_breaker.py`, `cost_policy.py`, `certification.py`, `failure_taxonomy.py`, `adapters/{ollama,openai_compat,http_providers,kimi,cloud,fake}.py`), `saathi/model_router.py` | — |

## The single most consequential finding of Phase 0

`saathi/platform/tg/intelligence/committee.py` already implements an
`InvestmentCommittee` with macro / technical / fundamental / quant / risk /
portfolio roles producing per-role action + confidence + rationale + key-risk,
plus consensus and dissent notes.

**It is entirely deterministic.** Every role method takes numeric inputs
(`trend`, `vol`, `beta`, `valuation`, `concentration`) and returns a scored
opinion. There is no LLM anywhere in the SaathiOS trading plane.

That is the shape of the gap this evaluation exists to measure: SaathiOS has the
committee *structure* and the deterministic authority chain; it has no
LLM-driven qualitative research layer feeding it.
