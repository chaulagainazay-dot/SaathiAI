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

## M312–M319 Connectivity Governance (COMPLETE WITH LIMITATIONS)

- **Verdict:** `TRADING_CONNECTIVITY_GOVERNANCE_CERTIFIED_WITH_LIMITATIONS`
- **Max state:** `CONNECTIVITY_GOVERNANCE_READY_NO_PROVIDER_CONNECTION`
- **Maturity:** `GOVERNANCE_ONLY`
- **Branch:** `milestone/m312-m319-connectivity-governance`
- Governance charter, authority model, provider registry, approval framework,
  credential policy, revocation/emergency/incident, threat model, control center.
- **No provider connection. No credentials. No orders. No canary. No live trading.**
- Evidence: `docs/trading/m312_m319_evidence/`

## M320–M327 Credentialless Provider Contracts (CERTIFIED WITH LIMITATIONS)

- **Verdict:** `PROVIDER_CONTRACTS_AND_MOCK_CONNECTIVITY_CERTIFIED_WITH_LIMITATIONS`
- **Browser verdict:** `PROVIDER_CONTRACTS_MOCK_CONNECTIVITY_BROWSER_CERT_PASSED_WITH_LIMITATIONS`
- **Maximum state:** `MOCK_PROVIDER_READY_NO_REAL_CONNECTIVITY`
- **Maturity:** `MOCK_CONNECTIVITY_ONLY`
- **Branch:** `milestone/m320-m327-provider-contracts`
- Provider-neutral interfaces, exact capability negotiation, deterministic
  synthetic fixtures, mock/replay transports, replay integrity, normalized
  errors, idempotency, and offline-only session lifecycle.
- Composes with M312–M319 governance; approval never activates connectivity.
- **No real provider, credential, authentication, account, balance, position,
  order, transfer, withdrawal, canary, deployment, or live-trading path.**
- Specification: `docs/trading/M320_M327_PROVIDER_CONTRACTS.md`
- Evidence: `docs/trading/m320_m327_evidence/`
- Backend, predecessor, frontend, build, clean-clone, secret, network, SDK, and
  authority gates passed. The historical in-app browser failure is preserved;
  the later authoritative project-pinned Playwright Chromium rerun passed all
  interactive UI, deterministic-flow, forbidden-control, console, and
  localhost-only network checks.

## M328–M335 Production Readiness, Observability & Operational Resilience (CERTIFIED WITH LIMITATIONS)

- **Verdict:** `PRODUCTION_READINESS_AND_OPERATIONAL_RESILIENCE_CERTIFIED_WITH_LIMITATIONS`
- **Browser verdict:** `PRODUCTION_READINESS_OPERATIONAL_RESILIENCE_BROWSER_CERT_PASSED_WITH_LIMITATIONS`
- **Maximum state:** `OPERATIONALLY_READY_OFFLINE`
- **Maturity:** `OPERATIONALLY_READY_OFFLINE`
- **Branch:** `milestone/m328-m335-production-readiness`
- Centralized health framework (7 domains, 5 states, worst-wins rollup), unified
  offline observability (deterministic trace IDs, correlation, timelines, execution
  history, audit visualization), local metrics (7 kinds, nearest-rank percentiles),
  offline alerting (3 severities, 3 local destinations), backup integrity and
  recovery simulation, a single diagnostics centre over 7 subsystems, deterministic
  modelled load validation over 5 dimensions, and a read-only operations control
  centre with 8 panels.
- Composes M312–M319 governance and M320–M327 provider contracts; introduces no
  parallel monitoring system.
- Observation grants no authority: a FAILED component, a breached threshold, or a
  CRITICAL alert changes nothing but what an operator sees.
- Fully deterministic — no wall clock, no random source. The certification evidence
  hash is byte-identical across processes and across a clean clone.
- **No external telemetry, cloud monitoring, email/SMS/push alerting, cloud backup,
  deployment control, or execution control. No provider connection, credential,
  OAuth, account, balance, position, order, canary, or live-trading path.**
- Backend hard gate 62/62; browser certification 257/257 on real Playwright Chromium
  against localhost-only servers; focused suites 96 backend + 16 frontend; full
  frontend 318; predecessor M312–M327 112; clean clone verified.
- Specification: `docs/trading/M328_M335_PRODUCTION_READINESS.md`
- Evidence: `docs/trading/m328_m335_evidence/`

## M336–M343 Baseline Regression Debt Closure & Private-Alpha Launch Readiness (CERTIFIED WITH LIMITATIONS)

- **Verdict:** `PRIVATE_ALPHA_LAUNCH_READINESS_CERTIFIED_WITH_LIMITATIONS`
- **Browser verdict:** `PRIVATE_ALPHA_LAUNCH_READINESS_BROWSER_CERT_PASSED_WITH_LIMITATIONS`
- **Maximum state:** `PRIVATE_ALPHA_READY_OFFLINE_INVITE_ONLY`
- **Branch:** `milestone/m336-m343-private-alpha-readiness`
- Closes the eight inherited backend failures M328–M335 correctly identified but
  did not own. All eight reduced to two root causes, both repaired in
  implementation: the three test files containing them are byte-identical to the
  predecessor commit.
  - **RC-A** (7 failures) — `bin/saathi-local` and `private_alpha.prepare()`
    treated the build artifacts `.venv` and `saathi-os/node_modules` as required
    host prerequisites. They are outputs of installation, so on any fresh
    checkout — including a newly invited tester's machine — `init_first_run`,
    `apply_local_upgrade` and the M165 gate were permanently blocked.
  - **RC-B** (1 failure) — the release gate counted a bare PEM header as a leaked
    private key and so blocked on its own secret-rejection sample and detector
    pattern. Red since `79d3c29` (M224–M231).
- Two further defects found while building the certification: the release SHA was
  recorded twice in every manifest (`rev-parse HEAD HEAD`), and concurrent
  `decide_approval` calls could all win a read-check-write race. Both fixed;
  the approval decision is now a conditional UPDATE under the runtime lock.
- Private-alpha contract, 71-step certified journey (31 positive, 18 refusals
  each asserted to return its own specific code), corrected platform-status
  wording, twelve failure and empty states, bounded soak with concurrency and
  recovery scenarios, four operational runbooks, and a read-only launch-readiness
  Control Center at `/operations/private-alpha-readiness`.
- **Invite-only. Localhost-only. No public registration, no broker or provider
  connection, no credential, no account, balance or position access, no order,
  no paper or live execution. All fifteen authority locks false.**
- Owner review is required, is not satisfied by any code path, and had not been
  performed at certification time.
- Browser certification 92/92 on real Playwright Chromium; frontend suite 342;
  production build clean.
- Specification: `docs/private-alpha/M336_M343_PRIVATE_ALPHA_LAUNCH_READINESS.md`
- Evidence: `docs/private-alpha/m336_m343_evidence/`
