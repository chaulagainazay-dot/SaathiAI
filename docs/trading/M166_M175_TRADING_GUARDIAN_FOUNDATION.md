# M166–M175 — Trading Guardian Research and Paper-Trading Foundation

**Terminal verdict:** `TRADING_GUARDIAN_RESEARCH_AND_PAPER_FOUNDATION_READY_WITH_LIMITATIONS`

**Date:** 2026-07-29

## Authority

| Claim | Status |
| --- | --- |
| Paper trading only | **YES** |
| Live trading authorized | **NO** |
| Live order capability | **NO** |
| Broker credentials supported | **NO** |
| Profitability guarantee | **NO** |
| Production trading authorized | **NO** |
| Public exposure | **NO** |

Default authority mode: **ADVISORY**.

Executable modes only: `ADVISORY`, `APPROVAL_REQUIRED`, `LIMITED_AUTONOMOUS_PAPER`.

Live trading is **not** an executable option in this mission.

## Architecture (composition over M62)

```
Market Data → Strategy Registry → Strategy Evaluation → Trade Proposal
→ Policy Engine → Risk Engine → Approval Center → ExecutionGateway
→ Paper Broker → Portfolio Ledger → Evidence / Journal
```

### New package

`saathi/platform/tg/` — research & paper foundation composition layer.

### Reused (not reimplemented)

| System | Role |
| --- | --- |
| `saathi/platform/strategy` | Deterministic backtesting, metrics, walk-forward |
| `saathi/platform/paper_trading` | Paper broker, fills, accounting, reconciliation |
| `saathi/platform/safety` | Circuit breakers, sweeps, alerts |
| `saathi/platform/trading_guardian.py` | Order-intent veto (M62.1) |
| `saathi/platform/market_data` | Fixtures, replay, quality |
| `saathi/platform/research` | Thesis / research pipeline |
| Approval Center + ExecutionGateway | Sole mutation authorities for paper tools |

## Milestone map

| ID | Scope |
| --- | --- |
| M166 | Domain model + versioned strategy registry |
| M167 | Governed catalog: Kotegawa-inspired MR, trend, momentum RS, no-trade |
| M168 | Deterministic market regime engine |
| M169 | Versioned policy engine (mandatory gates) |
| M170 | Deterministic risk engine + scoped kill switches |
| M171 | Backtest bridge to M62.4 engine + metrics view |
| M172 | Paper path remains M62.5; TG attaches proposal provenance |
| M173 | Append-only journal, evaluation verdicts, comparison |
| M174 | APIs (`/api/v1/platform/tg/*`), CLI, operator UI surfaces |
| M175 | Tests, docs, certification, limitations |

## Strategies

1. **kotegawa_mean_reversion** — interpretation of publicly discussed mean-reversion principles; **not** an exact private-method reproduction. Requires deviation + volume abnormality + reversal confirmation. Never buys solely because price fell.
2. **trend_following** — MA alignment, breakout, volume confirmation, vol-adjusted stop.
3. **momentum_rs** — instrument + sector momentum, relative strength, breadth + liquidity.
4. **no_trade** — control baseline; always zero signals.

Each version is **immutable after activation**. Changes require a new version.

## Policy gates (mandatory)

Instrument allowlist, market, timeframe, data freshness/completeness, strategy active, strategy version approved, regime compatible, liquidity, spread, avg traded value, volatility, event risk, earnings window, market hours, portfolio/sector/correlated exposure, risk budget, stop-loss, exit plan, reward:risk, position size, daily/weekly loss, drawdown, open positions, loss cooldown, kill switch, approval, idempotency, stale proposal, live trading disabled.

One failed mandatory gate blocks the proposal.

## Risk controls

- Fixed fractional sizing: `allowed_risk / stop_distance`
- Caps: max position value, portfolio heat, sector/correlated exposure, open positions
- Daily / weekly loss limits, drawdown ceiling, consecutive-loss cooldown
- No leverage, margin, withdrawals, martingale, unlimited grid, doubling after losses
- Kill switches: GLOBAL, STRATEGY, INSTRUMENT, MARKET, WORKSPACE, PORTFOLIO, AUTOMATION, TRADING_GUARDIAN — immediate, persistent, audited; strategy/LLM cannot activate or override

## LLM boundary

May: explain, summarize evidence, compare backtests, draft research notes.

Must not: issue orders, approve, size positions, override policy/kill switch, invent market data, claim guaranteed returns.

## Operator surfaces

### API (`/api/v1/platform/tg/...`)

posture, strategies, policies, regime/evaluate, proposals (+ review), backtests (+ compare), journal, kill-switch, strategy suspend.

### CLI

`python -m saathi.platform.tg.cli <strategy|regime|backtest|proposal|paper|journal|kill-switch|posture> ...`

### UI (`/trading/*`)

Existing M62 workspace plus: Regime, Proposals, Backtest Lab, Comparison, Journal, Policy & Kill Switch. Persistent banners: **PAPER TRADING ONLY**, **NO LIVE ORDERS**, **SIMULATED FUNDS**.

## Explicit limitations

1. Historical / simulated performance is **not** future performance.
2. Simulated fills may differ from real execution.
3. Strategies may stop working; human approval does **not** remove financial risk.
4. No live broker, no production deployment, no public listener.
5. Backtest bridge may fall back to fixture metrics if engine mapping fails (still paper-only).
6. LIMITED_AUTONOMOUS_PAPER exists as a mode enum but default remains ADVISORY with approval required for execution path.
7. Target machine: Apple Silicon, 8 GB RAM class, localhost only.

## Threat model (summary)

| Threat | Mitigation |
| --- | --- |
| Live order path | No live adapter; `live_trading_allowed=False`; LIVE env vetoed in M62 guardian |
| Self-approval | Actors `strategy:`, `llm:`, `agent:` rejected |
| LLM risk override | Sizing/policy pure Python; LLM outputs advisory only |
| Kill-switch bypass | Persistent store; strategy/LLM cannot activate/clear |
| Credential theft | No broker credential fields in TG package |
| Tenant leakage | org/workspace checks on registry, proposals, journal |

## Evidence

- Tests: `tests/test_m166_m175_trading_guardian.py`
- Frontend: `saathi-os/lib/m166_trading_guardian.test.js`
- Package: `saathi/platform/tg/`

## Non-claims

This milestone does **not** claim profitability, live readiness, regulatory approval, or production trading authorization.
