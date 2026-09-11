# Final Recommendation

## Verdict

**`TRADINGAGENTS_RECOMMENDED_WITH_LIMITATIONS`**

Adopt selected *patterns and schemas*. Adopt **zero code**, **zero dependencies**,
and **zero authority**.

## The finding in one paragraph

TradingAgents and SaathiOS are almost perfect complements. SaathiOS has a mature
deterministic financial plane — `ExecutionGateway`, Trading Guardian,
`PortfolioRiskEngine`, bias controls, provenance, walk-forward, multiple-testing,
certification — and **no LLM anywhere in the trading plane**. TradingAgents is
entirely an LLM research layer with **no deterministic plane at all**: no risk
engine, no limits, no approval, no ledger, no OMS, no broker, and — despite
declaring `backtrader` — no backtesting. Each has what the other lacks. The
recommendation is therefore to take the research-layer *ideas* and impose the
authority boundary SaathiOS already owns.

## Why not "strongly recommended"

Three findings cap the verdict:

1. **Fundamentals look-ahead is broken.** `_filter_reports_by_date` filters on
   fiscal period end, not filing date — a 30–75 day forward-looking advantage. The
   `OVERVIEW` path is documented as ignoring `curr_date` entirely. Neither is tested.
   Any research produced by this system on fundamentals is contaminated.
2. **Prompt injection is unmitigated and can persist.** Untrusted Reddit, StockTwits,
   and news text flows into prompts, then into a decision, then **verbatim** into
   the decision log, then back into future prompts across tickers.
3. **The authority model is the opposite of SaathiOS's.** `propagate()` returns the
   LLM Portfolio Manager's rating as the terminal decision, with LLM-generated
   position sizing and stop-loss upstream of it. Adopting the pipeline as designed
   would invert SaathiOS's core architectural commitment.

None is fatal to *selective adaptation*. All are fatal to *integration*.

## TOP 10 to adopt

| # | Item | Verdict | Why |
|---|---|---|---|
| 1 | Structured agent contracts (Pydantic; field descriptions as output instructions; render back to markdown) | ADAPT | Ends prose handoffs; the single highest-leverage pattern |
| 2 | `SentimentReport` schema (band + 0–10 score + confidence keyed to source sparsity + narrative) | ADAPT | Best contract in the repo; fills a total SaathiOS gap |
| 3 | Two-phase decision journal: pending → resolved, **alpha vs benchmark**, deferred reflection | ADAPT_WITH_AUDIT | Correct learning loop; correct outcome measure |
| 4 | `ModelCapabilities.preferred_structured_method` per model + quirk table | ADAPT | SaathiOS currently has one bool hardcoded to Kimi |
| 5 | `bind_structured` / `invoke_structured_or_freetext` graceful degradation | ADAPT | Bind once, fall back for the session; essential for local models |
| 6 | Checkpoint **shape signature** in the resume key | ADAPT | Prevents resuming a session under a changed pipeline |
| 7 | Look-ahead idioms: defensive re-filter, exclusive upper bound, tz-aware conversion, undated-excluded-in-backtest | ADAPT | Cheap; turns silent leaks loud |
| 8 | Boundary-condition test style + hermetic offline suite (576 tests, refuses live calls) | ADAPT | Most transferable artifact in the repository |
| 9 | Bull/bear challenge as a *role structure* | ADAPT (redesigned) | Right idea; must emit falsifiable claims with evidence refs |
| 10 | `safe_ticker_component` path allowlist incl. dot-only rejection; Polymarket as an evidence source; `VendorError` taxonomy; deterministic rating parse with no LLM call | ADAPT | Four small, correct, free wins |

## TOP 10 to reject or defer

| # | Item | Verdict | Why |
|---|---|---|---|
| 1 | LLM Portfolio Manager execution approval | **REJECT** | Terminal LLM authority; inverts the SaathiOS chain |
| 2 | LLM-generated `position_sizing` / `entry_price` / `stop_loss` | **REJECT** | Sizing belongs to `portfolio_risk/sizing.py` and Trading Guardian |
| 3 | Persona risk debators as risk authority | **REJECT** | Zero quantitative content — rhetoric about risk, not risk |
| 4 | Fiscal-period fundamentals filtering + unfiltered `OVERVIEW` | **REJECT** | Material look-ahead; filter on availability date instead |
| 5 | Verbatim free-prose lessons re-injected into prompts | **REJECT** | Durable injection channel; unfalsifiable content |
| 6 | LangGraph runtime | **DEFER** | Linear topology + two counters; 288 MB; duplicate orchestration on an 8 GB host |
| 7 | Backtrader and Redis | **REJECT** | Declared but imported nowhere; SaathiOS backtesting is far stronger |
| 8 | Reddit / StockTwits ingestion | **DEFER** | Highest injection volume, lowest signal; blocked until TA-1 controls exist |
| 9 | Provider clients / `langchain-*` SDKs / second provider registry | **REJECT** | `saathi/inference/` is an order of magnitude more capable |
| 10 | Placeholder-string-on-missing-data; string-prefix debate routing; second market-data plane | **REJECT** | Silent degradation, fragile routing, duplicate canon |

## SaathiOS modules that would benefit

| Module | Benefit |
|---|---|
| `saathi/inference/provider_descriptor.py` | Per-model structured-output method replacing the Kimi-only bool |
| `saathi/inference/engine.py` | Structured→free-text graceful degradation; nullish coercion |
| `saathi/inference/failure_taxonomy.py` | Extend normalised failures to evidence adapters |
| `saathi/platform/tg/market_data/bias_controls.py` | Defensive re-filter idiom; `available_at` vs `as_of`; undated rule |
| `saathi/platform/tg/market_data/provenance.py` | `UNTRUSTED_DATA` trust flag on evidence records |
| `saathi/platform/tg/intelligence/committee.py` | Narrative arbitration layered above deterministic consensus |
| `saathi/platform/tg/portfolio_risk/scenarios.py` | LLM-discovered candidate scenarios for human encoding |
| `saathi/platform/tg/journal.py` | `InvestmentDecisionJournal` schema; alpha-relative outcomes |
| `saathi/platform/tg/research_orchestrator/sessions.py` | Checkpoint shape signature; stale-session expiry |
| `saathi/platform/tg/research_orchestrator/budget.py` | Cost gating for any adopted LLM research layer |
| `saathi/platform/tg/regime.py` | Regime tagging on journal lessons |
| `saathi/platform/tg/research_lab/multiple_testing.py` | Promotion gate for learned lessons |

## Expected benefit, complexity, cost

**Benefit — high but bounded.** SaathiOS gains a qualitative research layer it
entirely lacks (news, sentiment, macro narrative, adversarial thesis challenge,
outcome-linked learning) without weakening any deterministic guarantee. It does not
gain better risk, better backtesting, better data handling, or better provider
management — SaathiOS is already ahead on all four.

**Complexity — medium, concentrated at one seam.** TA-1, TA-7, TA-8 are low risk.
TA-2, TA-3, TA-6 are medium. TA-4 and TA-5 are where authority creep would happen,
and the boundary-invariance test is the control for both.

**Resource cost — the real constraint.** Measured: ~17–25 LLM calls per
instrument-day, with 15k–40k input tokens on later nodes because full prose reports
are re-injected at every stage. Emitting structured claims instead of prose is what
makes this affordable. Zero new dependencies; zero new runtime processes; 385 MB of
upstream environment stays in `~/dev-toolkits`, never in SaathiOS.

## Authority audit

Nothing in this evaluation grants TradingAgents — or any LLM — the ability to submit
an order, approve execution, bypass Trading Guardian, override `PortfolioRiskEngine`,
mutate the canonical ledger, alter risk budgets, access withdrawals, enable leverage,
or write to a broker. The proposed `TradingIntentProposal` deliberately carries no
quantity, price, stop, or sizing field. LLMs remain advisory research and proposal
generators, and the deterministic plane must be provably invariant to their output.

`ExecutionGateway`, Trading Guardian, `PortfolioRiskEngine`,
`PortfolioConstructionEngine`, Approval, the Canonical Fund Ledger, audit/evidence
infrastructure, RBAC, deterministic risk limits, no-withdrawal authority,
no-leverage default, and fail-closed behaviour are all unchanged by this mission.

## Remaining risks

1. **Authority creep at TA-4/TA-5** — narrative commentary gradually becoming a gate.
   Control: boundary-invariance test, enforced at TA-9.
2. **Cost blow-out** — a watchlist × 20 calls/day is the dominant system cost.
   Control: `budget.py` gating, structured claims instead of prose re-injection.
3. **Injection through a source added later** — a new adapter bypassing the
   `UNTRUSTED_DATA` type. Control: the chokepoint, plus injection tests.
4. **Look-ahead reintroduced by an analyst that fetches its own data.** Control:
   analysts read evidence records only; never fetch.
5. **Upstream drift** — TradingAgents moves fast; this evaluation pins `a33fd4c`.
   Nothing is vendored, so drift costs nothing.
6. **Learned-lesson poisoning** — stale or regime-mismatched lessons steering
   research. Control: expiry, regime matching, multiple-testing promotion gate.

## Final classification

**ADAPT** — selected patterns and schemas, self-authored, no code copied, no
dependency added, no authority granted.

Not `INTEGRATE` (the pipeline's authority model is incompatible).
Not `REJECT` (the research-layer gap is real and this is the best available map of it).
Not `KEEP SAATHIOS` alone (that would leave a genuine capability gap unaddressed).

## Next recommended mission

**Finish T-NEXT-4 first.** This roadmap is advisory-layer work above a deterministic
chain that is still being hardened; interleaving them would make regressions
unattributable.

After T-NEXT-4, the next mission should be **TA-1 — Evidence and Safety Contract**:
`available_at` vs `as_of`, the `UNTRUSTED_DATA` type, `ResearchClaim` with mandatory
provenance, the checkpoint shape signature, the provider structured-method enum, and
the boundary-invariance test. TA-1 involves no LLM, touches no financial authority,
and is independently valuable to SaathiOS even if no further stage is ever built.
