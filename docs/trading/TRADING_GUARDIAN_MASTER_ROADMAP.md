# Trading Guardian Master Roadmap (Post M272–M279)

## Mission

Continue evolution from a research platform into a complete institutional-grade
quantitative investment **operating system** — research-first, paper-only by default.

**Do not prioritise broker connectivity.** The execution layer is the final layer, not the next one.

## Completed foundation

| Block | Focus | Verdict (summary) |
|-------|--------|-------------------|
| M248–M255 | Institutional investment intelligence | Certified with limitations |
| M256–M263 | Research market data & signal validation | Certified with limitations |
| M264–M271 | Recovery & historical qualification | Recovered + qualified with limitations |
| M272–M279 | Multi-strategy research lab | Certified with limitations |

## Phase 1 — M280–M287 · Autonomous Research Orchestrator

Self-managing quantitative research laboratory: experiment queue, scheduler,
resource/worker pool, budgets, templates, registries, notebook/journal,
hypothesis tracking, failure analysis, replay, dashboard, version promotion.

**Determinism preserved. Research only. No broker.**

## Phase 2 — M288–M295 · Institutional Paper Trading Simulation

Virtual exchange, matching, order books, fills, slippage, ledger, kill switch —
**all simulated**. No API keys, no exchange accounts.

## Phase 3 — M296–M303 · Institutional Portfolio & Risk Intelligence

Portfolio analytics, attribution, factor/sector exposure, risk budgets,
optimiser V2, committee V2 — portfolios not isolated strategies.

## Phase 4 — M304–M311 · Read-Only Market Observation

Only after prior phases succeed. Observe markets safely. **No** login, OAuth,
orders, balances, credential storage, or execution.

## Engineering principles

- Deterministic execution
- Clean-clone reproducibility
- Immutable evidence & audit trail
- Experiment lineage
- Fail-closed behaviour
- Offline capability
- Paper-only operation
- No investment-advice claims

## Final vision

Professional quant research platform: thousands of experiments, hundreds of
strategies, full lineage, constrained portfolios, regimes, robustness,
institutional paper simulation, risk intelligence, committee reports,
evidence-backed paper candidates only.

**Must not become a live trading engine by default.** Live execution requires a
separate governance programme and explicit human approval.

## Success criteria

Reproducible · explainable · evidence-driven · portfolio-aware · research-first ·
institution-grade · paper-only · scientifically defensible.


## Status (as of M311)

Phases 1–4 of this master roadmap are **implemented and certified with limitations** under paper/research/read-only authority. Broker connectivity remains out of scope.
