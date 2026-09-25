# Risk and Authority Comparison

## TradingAgents risk "team"

Three agents: `aggressive_debator.py`, `conservative_debator.py`, `neutral_debator.py`.
Each is a single prompt with a persona. Representative source
(`conservative_debator.py`):

> "As the Conservative Risk Analyst, your primary objective is to protect assets,
> minimize volatility, and ensure steady, reliable growth… critically examine
> high-risk elements…"

They rotate for `3 × max_risk_discuss_rounds` turns, then the Portfolio Manager
synthesises. That is the entire risk architecture.

### What is absent

No VaR. No volatility computation. No position limits. No concentration limits.
No exposure or beta budget. No drawdown gate. No daily or weekly loss limit. No
liquidity model. No stress scenarios. No circuit breaker. No kill switch. No
correlation matrix. No margin logic.

Volatility, liquidity, and concentration are discussed **narratively** — the words
appear in prompts; no number is ever computed. Risk here is rhetoric about risk.

## SaathiOS risk architecture

| Concern | SaathiOS implementation |
|---|---|
| Deterministic portfolio risk | `saathi/portfolio.py::PortfolioRiskEngine` (403 lines) |
| Hard limits | `tg/portfolio_risk/limits.py` |
| Position sizing | `tg/portfolio_risk/sizing.py` |
| Scenarios / stress | `tg/portfolio_risk/scenarios.py`, `tg/stress_lab.py`, `research_lab/stress_testing.py` |
| Analytics / attribution | `tg/portfolio_risk/analytics.py`, `attribution.py` |
| Optimiser | `tg/portfolio_risk/optimiser_v2.py` |
| Committee review | `tg/portfolio_risk/committee_v2.py`, `tg/intelligence/committee.py` |
| Veto authority | `saathi/platform/trading_guardian.py`, `tg/policy.py`, `tg/risk.py` |
| Kill switch | `tg/kill_switch.py`, `tg/domain.py::TradingGuardianKillSwitch` |
| Certification | `tg/portfolio_risk/certification.py` |
| Recovery | `tg/recovery.py` |

Plus the `AGENTS.md` Trading Guardian contract: advisory-by-default, approval-gated
autonomy, mandatory stop-loss, daily/weekly loss limits, leverage disabled,
no-withdrawal credentials, stale-data and reconciliation checks, circuit breakers,
immutable audit trail, explicit human approval before live activation.

## Comparison

| Dimension | TradingAgents | SaathiOS | Winner |
|---|---|---|---|
| Determinism | none | full | **SaathiOS** |
| Quantitative measurement | none | VaR/limits/scenarios/attribution | **SaathiOS** |
| Hard veto | none | Trading Guardian | **SaathiOS** |
| Fail-closed | not applicable | yes | **SaathiOS** |
| Auditability | prose transcript | immutable audit trail + evidence | **SaathiOS** |
| Kill switch | none | yes | **SaathiOS** |
| Scenario *discovery* (naming risks nobody encoded) | LLM personas | limited to encoded scenarios | **TradingAgents** |
| Thesis challenge / red-teaming | adversarial personas | deterministic dissent notes | **TradingAgents (narrow)** |

## Portfolio Manager authority

**TradingAgents:** `graph/trading_graph.py:482` returns
`self.process_signal(final_state["final_trade_decision"])` — the LLM Portfolio
Manager's rating is the terminal output. Its prompt context includes prior prose
lessons (`get_past_context`). Nothing deterministic sits between the model and the
result. There is also no execution: no OMS, no broker, no ledger.

**SaathiOS:** proposal → `PortfolioConstructionEngine` → `PortfolioRiskEngine` →
Trading Guardian → Approval → `ExecutionGateway` → OMS → Canonical Ledger →
Reconciliation. Each stage deterministic, separable, auditable, fail-closed.

## Verdicts

| Item | Verdict | Reason |
|---|---|---|
| LLM risk debators as risk **authority** | **REJECT** | Zero quantitative content; would replace measurement with rhetoric |
| LLM risk debators as **risk commentary** on an already-computed risk report | **ADAPT (bounded)** | Can surface a risk nobody encoded; output is a note, never a gate |
| Adversarial persona **scenario discovery** feeding `scenarios.py` as *candidate* scenarios for human review | **ADAPT** | Genuine value: LLMs are good at naming tail cases; the scenario is then encoded and evaluated deterministically |
| LLM Portfolio Manager **execution approval** | **REJECT** | Direct violation of the SaathiOS authority chain |
| LLM Portfolio Manager **review / challenge / explain trade-offs** on a deterministic proposal | **ADAPT** | Useful narrative layer above `committee_v2.py`; produces a commentary artifact, not a decision |
| Trader-generated `position_sizing` / `entry_price` / `stop_loss` | **REJECT** | Sizing and levels are `portfolio_risk/sizing.py` and Trading Guardian territory. SaathiOS's `TradingIntentProposal` must carry **no** size or price fields |
| Risk round-robin rotation with a turn cap | **ADAPT (pattern only)** | Cheap bounded-debate mechanic; keep the cap, drop the authority |

## Binding rule for any future adoption

The deterministic plane must produce **byte-identical output** whether the LLM
research layer is present, absent, empty, or adversarial. That property is
testable, and it should be a certification gate in TA-9 before any LLM research
output is allowed to reach a proposal.
