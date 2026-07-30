# M272–M279 — Multi-Strategy Research Lab, Portfolio Optimisation and Adaptive Regime Intelligence

## Terminal verdict

`MULTI_STRATEGY_RESEARCH_LAB_AND_ADAPTIVE_PORTFOLIO_INTELLIGENCE_CERTIFIED_WITH_LIMITATIONS`

## Maximum research state

`RESEARCH_PORTFOLIO_AND_PAPER_CANDIDATE_EVALUATION_ONLY`

## Authority boundary

- **PAPER ONLY / SANDBOX ONLY / RESEARCH ONLY / OFFLINE-FIRST**
- No broker connectivity, API keys, OAuth, provider canaries
- No order submission, modification, cancellation
- No paper or live execution authority
- `PAPER_CANDIDATE` means **ELIGIBLE_FOR_FUTURE_PAPER_SIMULATION_REVIEW** only
- Human review required for promotion
- Preserved M270 OOS failures are **not** reinterpreted:
  - AAPL `tf_dual_ma`: `OUT_OF_SAMPLE_FAILED`
  - BTCUSDT `tf_dual_ma`: `OUT_OF_SAMPLE_FAILED`

## Architecture

Package: `saathi/platform/tg/research_lab/`

Composes with M248–M255 intelligence, M256–M263 market data, M264–M271 historical qualification — no parallel strategy/dataset/backtest systems.

| Milestone | Capability |
|-----------|------------|
| M272 | Experiment registry, pre-registration, config checksums, lineage, immutable versions, replay |
| M273 | Fair multi-strategy comparison under common assumptions; preserved failures; research scorecard |
| M274 | Parameter/temporal/cross-asset/cost/data robustness; multiple-testing burden; deflated confidence |
| M275 | Point-in-time regime definitions (train-only thresholds), classification, unknown regimes |
| M276 | Constrained research portfolio construction (equal weight, inv-vol, risk parity, min-var, …) |
| M277 | Strategy ensembles with frozen allocation rules; leakage blocked |
| M278 | Stress testing + hard-gated candidate promotion with human review |
| M279 | Control Center UI, API, CLI, certification, evidence |

## Surfaces

- **API**: `/api/v1/platform/tg/research-lab/*`
- **CLI**: `python -m saathi.platform.tg rl-*` and `paper-gov rl-*`
- **UI**: `/trading/research-lab`
- **Storage**: `research_lab.db` (SQLite, no credentials/orders)

## Certification invariant

`certified_experiment_requires_pre_registration=true`

## Explicit non-actions

- Did not connect brokers or request credentials
- Did not activate M240–M247 canaries
- Did not start M280
- Did not promote failed AAPL/BTC dual-MA results to paper candidates
- Did not claim profitability, investment advice, or production readiness

## Recommended next milestone

M280+ only after owner review — e.g. paper-simulation queue for human-approved `PAPER_CANDIDATE` strategies under continued sandbox authority (not automatic execution).

## Evidence

See `docs/trading/m272_m279_evidence/`.
