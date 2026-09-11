# Component Verdicts

Every major TradingAgents subsystem, one verdict each. No hedging.

## Agents

| Component | Verdict | Justification |
|---|---|---|
| Fundamentals Analyst | **ADAPT** | Real gap in SaathiOS. Must consume SaathiOS evidence records, never fetch, and must never see a figure before its filing date. |
| Market/Technical Analyst | **ADAPT (narrative only)** | SaathiOS computes indicators correctly. Adopt only the interpretation layer; an LLM must never compute a number that feeds a decision. |
| News Analyst | **ADAPT** | Full gap. The tz-aware, exclusive-upper-bound, undated-excluded windowing is the part worth taking. |
| Sentiment Analyst — **schema** | **ADAPT** | `SentimentReport` (band + 0–10 score + confidence + narrative, with the confidence rule keyed to source sparsity) is the best contract in the repository. |
| Sentiment Analyst — **Reddit/StockTwits sources** | **DEFER** | Highest injection volume, lowest signal. Blocked until the untrusted-content controls in `SECURITY_REVIEW.md` exist. |
| Macro (FRED) adapter | **COMBINE** | Adopt the adapter shape; add the vintage/revision handling upstream lacks. |
| Polymarket adapter | **ADAPT** | Cheap, timestamped, differentiated signal SaathiOS does not have. |
| Bull Researcher | **ADAPT (redesigned)** | The role is right; "advocate and win" prompting produces rhetoric. Must emit structured, falsifiable claims with evidence refs. |
| Bear Researcher | **ADAPT (redesigned)** | Same. The bear must challenge specific claims, not compose counter-rhetoric. |
| Research Manager | **COMBINE** | Keep `InvestmentCommittee`'s deterministic consensus/dissent as canonical; layer narrative arbitration above it. |
| Trader Agent — **proposal shape** | **ADAPT** | A typed intent object between research and construction is the right seam. |
| Trader Agent — **entry_price / stop_loss / position_sizing fields** | **REJECT** | LLM-generated sizing and levels. `portfolio_risk/sizing.py` and Trading Guardian own these. |
| Risk debators — as risk authority | **REJECT** | Zero quantitative content. Replaces measurement with persona rhetoric. |
| Risk debators — as commentary / scenario discovery | **ADAPT (bounded)** | Useful for naming tail cases nobody encoded; output is a candidate scenario for human review, never a gate. |
| Portfolio Manager — execution approval | **REJECT** | `propagate()` returns the LLM's rating as the terminal decision. Direct violation of the SaathiOS authority chain. |
| Portfolio Manager — review / challenge / explain | **ADAPT** | Narrative commentary on a *deterministic* proposal is genuinely useful and carries no authority. |

## Graph and orchestration

| Component | Verdict | Justification |
|---|---|---|
| LangGraph runtime | **DEFER** | Realised topology is linear + two counters. `research_orchestrator/` already does more. 288 MB installed on an 8 GB host. Duplicate orchestration authority. |
| Graph patterns (typed shared state, node contracts, bounded loop counters, message-clear step) | **ADAPT** | Free; no dependency. |
| Count-based debate termination | **ADAPT with improvement** | Keep the hard cap as a cost guarantee; add convergence and repetition detection, which upstream lacks. |
| String-prefix turn routing (`startswith("Bull")`) | **REJECT** | Fragile. Route on typed speaker identity. |
| SQLite checkpoint store | **REJECT DUPLICATE** | `research_orchestrator/sessions.py` + `storage.py` own this. |
| **Checkpoint shape-signature in the resume key** | **ADAPT — high value** | Prevents resuming a session under a changed pipeline. Small, correct, directly applicable. |
| Stale-checkpoint expiry | **ADAPT (as a SaathiOS improvement)** | Neither system has it; SaathiOS should. |
| `SignalProcessor` — deterministic parse, no LLM call | **ADAPT (principle)** | Never spend a model call parsing your own structured output. |

## Data

| Component | Verdict | Justification |
|---|---|---|
| Market-data plane as a whole | **KEEP SAATHIOS** | `bias_controls`, `provenance`, `corporate_actions`, `adjustments`, `dataset_split`, `licensing`, `signal_validation` have no upstream counterpart. |
| Defensive re-filter idiom (`_verified_rows`) | **ADAPT** | Re-apply the cutoff even when the loader already did. Converts a silent leak into a loud one. |
| Undated-record rule (excluded in backtest, kept in live) | **ADAPT** | Correct nuance; encode explicitly in the evidence contract. |
| Exclusive upper bound + tz-aware conversion | **ADAPT** | Convention plus the tests that pin it. |
| Fiscal-period fundamentals filtering | **REJECT** | Ignores filing lag; a 30–75 day look-ahead. SaathiOS must filter on availability date. |
| Unfiltered `OVERVIEW` fundamentals path | **REJECT** | `curr_date` documented as unused. Unbounded look-ahead. |
| `VendorError` taxonomy + per-capability vendor routing | **ADAPT** | Extend SaathiOS's `failure_taxonomy.py` to evidence adapters. |
| Placeholder-string-on-missing-data | **REJECT** | Absence must be a typed `Unavailable(reason, source, as_of)`, never prose. |
| `yfinance` / `stockstats` as dependencies | **REJECT** | Unofficial scraper + maths SaathiOS already has. |

## Memory

| Component | Verdict | Justification |
|---|---|---|
| Two-phase pending → resolved decision log | **ADAPT — high value** | Nothing is "learned" before the outcome exists. |
| Alpha-vs-benchmark outcome measure | **ADAPT — high value** | Correct measure; most systems use raw return. |
| Deferred single-call reflection | **ADAPT** | Cheap and correctly timed. |
| Free-prose lesson stored verbatim | **REJECT** | Durable prompt-injection channel and unfalsifiable content. |
| Verbatim re-injection into future prompts | **REJECT** | Same. |
| No validity period / regime tag / sample size | **REJECT** | SaathiOS must add all three; upstream has none. |
| Lessons influencing the final decision | **REJECT AUTHORITY MODEL** | Advisory only, enforced by an invariance test. |
| Plain-text log as storage | **REJECT DUPLICATE** | Three SaathiOS journals already exist. |
| Overall reflection loop | **ADAPT_WITH_AUDIT** | Right idea, wrong safeguards. |

## Providers

| Component | Verdict | Justification |
|---|---|---|
| Provider registry | **KEEP SAATHIOS** | ~50 governed modules vs a factory. Do not build a second registry. |
| `ModelCapabilities.preferred_structured_method` | **ADAPT — highest-value provider borrow** | Replaces SaathiOS's single bool hardcoded to `family_id == "kimi"`. |
| Per-model quirk table with issue references | **ADAPT** | Operational knowledge as data. |
| `bind_structured` / `invoke_structured_or_freetext` degradation | **ADAPT** | Bind once; fall back for the session; uniform warning. |
| `_coerce_optional_float` nullish coercion | **ADAPT (trivial)** | Prevents avoidable validation failures. |
| Concrete provider clients / `langchain-*` SDKs | **REJECT** | Duplicates `saathi/inference/adapters/`. |

## Structured outputs

| Component | Verdict |
|---|---|
| Pydantic schemas as agent contracts | **ADAPT** |
| Field descriptions as output instructions | **ADAPT** |
| Render-back-to-markdown for human display | **ADAPT** |
| Prose as the primary artifact between agents | **REJECT** — typed contracts end to end |
| Absence of evidence refs / citations on every claim | **REJECT** — SaathiOS must require provenance |
| Confidence on only one schema | **REJECT** — required on all |

## Testing, backtesting, security

| Component | Verdict |
|---|---|
| Hermetic offline test suite (576 passing, refuses live calls) | **ADAPT (as a norm)** |
| Boundary-condition date tests per adapter | **ADAPT — high value** |
| Provider-quirk regression tests | **ADAPT** |
| `safe_ticker_component` path allowlist + dot-only rejection | **ADAPT** |
| Backtesting | **KEEP SAATHIOS** — upstream has none; `backtrader` is a phantom dependency |
| Backtrader / Redis dependencies | **REJECT** |
| Untrusted-content handling | **REJECT upstream approach**; SaathiOS must build its own before TA-2 |
| Prompt-injection tests | **ADAPT (as a requirement SaathiOS adds)** — upstream has none |
