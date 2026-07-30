# M280–M287 — Autonomous Research Orchestrator

## Verdict
`AUTONOMOUS_RESEARCH_ORCHESTRATOR_CERTIFIED_WITH_LIMITATIONS`

## Max state
`AUTONOMOUS_RESEARCH_ORCHESTRATION_ONLY`

## Package
`saathi/platform/tg/research_orchestrator/`

## Capabilities
Experiment queue · priority scheduling · worker pool · retry/resume/cancel ·
dependency graph · compute budget · runtime estimator · research calendar ·
templates · model registry · strategy registry V2 (M248 compose) · feature/dataset
views · lab notebook · journal · hypothesis tracking · failure analysis ·
reproducible sessions · job replay · version promotion · control center.

## Surfaces
- API: `/api/v1/platform/tg/research-orchestrator/*`
- CLI: `ro-*` / `paper-gov ro-*`
- UI: `/trading/research-orchestrator`

## Authority
Research only. No broker, credentials, orders, or live trading.
In-process deterministic workers only.

## Next
Phase 2 M288–M295 Institutional Paper Trading Simulation (still no broker).
