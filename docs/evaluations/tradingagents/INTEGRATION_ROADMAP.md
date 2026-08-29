# Staged Integration Roadmap (proposal — not scheduled, not started)

Every stage is evidence-backed by a finding in this evaluation. Stages with no
supporting evidence were dropped rather than padded.

**Sequencing rule:** TA-1 gates everything. No LLM touches trading data until the
evidence contract, the untrusted-content control, and the boundary-invariance test
exist. That ordering is the whole point.

---

## TA-1 — Evidence and safety contract *(precondition for all others)*

**Do:** define `MarketDataEvidence` with `available_at` distinct from `as_of`;
define `UNTRUSTED_DATA` as a type that cannot be concatenated into a system prompt;
define `ResearchClaim` with mandatory `evidence_refs`; extend
`failure_taxonomy.py` to evidence adapters; add typed `Unavailable(reason, source,
as_of)`; add the defensive re-filter idiom and the undated-record rule; add the
checkpoint **shape signature** to `research_orchestrator/sessions.py`; replace
`ProviderDescriptor.structured_output_supported: bool` with a
`preferred_structured_method` enum.

**Also do:** write the **boundary-invariance test** — the deterministic plane
produces identical output with the research layer absent, empty, and adversarial.

**Evidence:** `LOOKAHEAD_AUDIT` Defects 1–4 · `SECURITY_REVIEW` injection paths 1–4 ·
`GRAPH_CHECKPOINT_ANALYSIS` shape signature · `PROVIDER_COMPARISON` capability gap.
**Touches:** `market_data/`, `inference/provider_descriptor.py`,
`research_orchestrator/sessions.py`. **No LLM involved.** **Risk: low.**

---

## TA-2 — Analyst adapters (read-only, structured)

**Do:** Fundamental, Technical-narrator, News, Sentiment, Macro analysts. Each reads
`MarketDataEvidence`, emits `ResearchClaim[]`, fetches nothing, computes no number
that feeds a decision. Adopt the `SentimentReport` schema (band + 0–10 + confidence
+ narrative). Add FRED-style macro ingestion **with vintage handling**. Add the
Polymarket adapter. Gate all calls through `cost_policy.py` + `budget.py`.

**Explicitly deferred within TA-2:** Reddit and StockTwits ingestion — highest
injection volume, lowest signal, blocked until TA-1's controls are proven in use.

**Evidence:** `GAP_MATRIX` rows 1–6 · `AGENT_ARCHITECTURE` role mapping ·
`DEPENDENCY_RESOURCE_AUDIT` call-volume analysis. **Risk: medium** (look-ahead,
injection, cost).

---

## TA-3 — Bull/Bear challenge protocol

**Do:** structured challenge, not advocacy. Bull emits claims; Bear must challenge
*specific* claim ids with counter-evidence; unsupported claims are dropped, not
softened. Bounded rounds (hard cap for cost) **plus** convergence and repetition
detection, which upstream lacks. Route on typed speaker identity, not
`startswith("Bull")`.

**Evidence:** `AGENT_ARCHITECTURE` (advocacy prompting produces rhetoric) ·
`GRAPH_CHECKPOINT_ANALYSIS` (string-prefix routing is fragile). **Risk: medium.**

---

## TA-4 — Research arbiter and risk commentary

**Do:** narrative arbitration layered **above** the existing deterministic
`InvestmentCommittee` — the committee's consensus/dissent stays canonical. Add
LLM risk *commentary* on an already-computed `PortfolioRiskEngine` report, and
adversarial *scenario discovery* producing **candidate** scenarios for human review
before encoding into `portfolio_risk/scenarios.py`. Add PM-style *review/challenge*
commentary on a deterministic proposal.

**Hard boundary:** no output of this stage gates, sizes, approves, or vetoes.

**Evidence:** `RISK_AUTHORITY_COMPARISON` (scenario discovery is the one place
LLMs beat the deterministic engine) · `CURRENT_STATE` (committee already exists).
**Risk: medium-high** — this is where authority creep would occur; the invariance
test from TA-1 is the control.

---

## TA-5 — Structured thesis and intent contract

**Do:** `StructuredInvestmentThesis` and `TradingIntentProposal` as defined in
`PROPOSED_ARCHITECTURE.md`. Wire the proposal into `PortfolioConstructionEngine`
as an *input*, alongside existing deterministic signals — never replacing them.

**Hard boundary:** the proposal carries no quantity, price, stop, or sizing.

**Evidence:** `COMPONENT_VERDICTS` (Trader shape ADAPT / fields REJECT) ·
`GAP_MATRIX` row 9. **Risk: high** — this is the seam that touches the
deterministic plane. Requires the TA-9 certification before it carries weight.

---

## TA-6 — Investment decision journal

**Do:** extend `tg/journal.py` with the schema in `MEMORY_REFLECTION_ANALYSIS.md`.
Two-phase pending → resolved. Alpha-vs-benchmark outcome via
`portfolio_risk/attribution.py`. Structured lessons only — never free text.
Mandatory `validity_period`, `regime_at_decision`, and sample size. Regime-matched,
point-in-time recall. Promotion `PROPOSED → VALIDATED` through
`research_lab/multiple_testing.py`.

**Hard boundary:** `ADVISORY_ONLY` — lessons enter research prompts, nothing else.

**Evidence:** `MEMORY_REFLECTION_ANALYSIS` full risk audit. **Risk: medium** —
prompt poisoning and stale conclusions are the named hazards.

---

## TA-7 — Evaluation and test discipline

**Do:** boundary-condition date tests per evidence adapter; provider-quirk
regression tests; prompt-injection tests (upstream has none); an agent-behaviour
regression suite (golden evidence → expected structured claims, scored). Target the
upstream test-to-source ratio.

**Not in scope:** Backtrader, or any new backtesting engine. SaathiOS's
`walk_forward_v2`, `backtest_v2`, `monte_carlo`, `stress_lab`, `dataset_split`,
`multiple_testing`, and `robustness` are strictly superior to upstream's *nothing*.

**Evidence:** `TEST_REPORT` gaps 1–5 · `GAP_MATRIX` row 18. **Risk: low.**

---

## TA-8 — Local-model qualification

**Do:** qualify a small local analyst model via `adapters/ollama.py` +
`hardware.py` on the 8 GB host. Measure RAM, latency, and structured-output
reliability. Hybrid target: local for high-frequency narrow extraction, cloud for
arbitration. Expect local models to need the free-text fallback path more often —
which is exactly why TA-1's `preferred_structured_method` work comes first.

**Evidence:** `DEPENDENCY_RESOURCE_AUDIT` (17–25 calls, 15k–40k input tokens on
later nodes) · `PROVIDER_COMPARISON`. **Risk: low** (qualification only).

---

## TA-9 — Integration certification

**Do:** certify, with evidence artifacts, that every invariant in
`PROPOSED_ARCHITECTURE.md` §Invariants holds: boundary invariance, no LLM write
path, point-in-time correctness, provenance completeness, untrusted isolation,
advisory memory, bounded cost, fail-safe absence. Reuse
`tg/portfolio_risk/certification.py` and `research_lab/certification.py` patterns.

**Gate:** no research output influences a live or paper proposal until TA-9 passes.

**Risk: n/a — this is the control.**

---

## Not recommended at any stage

LangGraph · Backtrader · Redis · provider SDKs · a second market-data plane · a
second provider registry · a second orchestrator · a second journal store ·
LLM-generated sizing, price, or approval · Reddit/StockTwits before TA-1 is proven.

## Relationship to T-NEXT-4

TA-1 through TA-9 are **independent of** T-NEXT-4 (Canonical Trading Chain
Integration & Execution Integrity) and must not be interleaved with it. T-NEXT-4
hardens the deterministic plane; this roadmap adds an advisory layer above it.
Doing both at once would make it impossible to attribute a regression to either.

**Recommended order: finish T-NEXT-4 first.** A research layer proposing into an
unfinished OMS/reconciliation chain is premature.
