# Decision Memory and Reflection

## What TradingAgents implements

`agents/utils/memory.py` — `TradingMemoryLog`, 299 lines, a **plain-text append log**
of markdown blocks (earlier releases used a vector store; this version does not).

Two-phase design:

**Phase A — at decision time**, `store_decision(ticker, trade_date, final_trade_decision)`
appends `[{date} | {ticker} | {rating} | pending]` + the decision text. **No LLM call.**
Idempotent via a raw-text scan for an existing pending tag.

**Phase B — once the outcome is known**, `update_with_outcome(ticker, trade_date,
raw_return, alpha_return, holding_days, reflection)` replaces the pending tag and
appends a REFLECTION section, written atomically. `batch_update_with_outcomes()`
handles many at once. `_apply_rotation()` bounds log growth.

`graph/reflection.py` — `Reflector.reflect_on_final_decision()` makes one LLM call:

```
Raw return: {raw_return:+.1%}
Alpha vs {benchmark_name}: {alpha_return:+.1%}
Final Decision: {final_decision}
```
→ "exactly 2–4 sentences of plain prose … stored verbatim in a decision log and
re-read by future analysts".

**Recall** — `get_past_context(ticker, n_same=5, n_cross=3)` injects the 5 most
recent same-ticker entries (full) plus 3 cross-ticker entries (reflection only)
into the Portfolio Manager prompt.

## What is genuinely good

1. **Benchmark-relative outcome.** The reflection is anchored on **alpha vs a
   benchmark** (`SPY`, or `^N225` for `.T` listings), not raw return. This is the
   correct measure and most systems get it wrong.
2. **Deferred reflection.** Nothing is "learned" at decision time. The lesson is
   written only when the outcome exists. This structurally prevents the most common
   self-congratulation loop.
3. **Pending-state modelling.** A decision is explicitly `pending` until resolved,
   and pending entries are excluded from recall. Clean.
4. **Bounded output.** 2–4 sentences, enforced by prompt, plus log rotation.
5. **Idempotent write** and **atomic update**.

## Risk audit of the recall path

| Risk | Present? | Mechanism |
|---|---|---|
| Prompt poisoning | **YES** | The lesson is free prose stored *verbatim* and re-injected into a later prompt. If any upstream content (news, Reddit) influenced the decision text, an injected instruction can persist into future runs. This is a durable injection channel. |
| Stale conclusions | **YES** | No validity period, no expiry. A lesson from a different rate regime is injected with equal weight forever. |
| Regime dependence | **YES** | Nothing tags the market regime the lesson was learned in. |
| False causal learning | **YES** | A single outcome over one holding period is attributed to thesis quality. Nothing distinguishes a good decision with a bad outcome from a bad decision with a good outcome. No statistical significance, no sample size. |
| Survivorship / selection bias | **YES** | Only resolved entries are recalled; recall is "most recent N", not a representative sample. |
| Data leakage | Partial | Recall filters `pending`, but nothing checks that a recalled lesson's *outcome date* precedes the analysis date. In a historical replay this can leak the future. |
| Unbounded context growth | Mitigated | Rotation + fixed `n_same`/`n_cross` caps. |
| Free-form memory influencing authority | **YES, critical** | The lessons feed the Portfolio Manager, whose output is the terminal decision. In TradingAgents an unvalidated prose lesson can move the final call. |

## Proposed SaathiOS equivalent — `InvestmentDecisionJournal`

SaathiOS already has three journals (`tg/journal.py`, `research_orchestrator/journal.py`,
`paper_simulation/journal.py`). This is a **schema proposal to extend the existing
`tg/journal.py`**, not a new subsystem.

```
decision_id                 stable id
timestamp                   decision time (UTC)
instrument                  canonical instrument id
research_snapshot_ref       -> evidence store, immutable
signal_snapshot_ref         -> deterministic signals at T
market_snapshot_ref         -> market_data snapshot at T
portfolio_snapshot_ref      -> holdings/cash/NAV at T
proposal_ref                -> TradingIntentProposal
decision                    what the deterministic chain actually did
expected_thesis             structured claims, each falsifiable
risk_assumptions            structured, each with a measurable trigger
regime_at_decision          from tg/regime.py  (upstream has nothing here)
actual_outcome              realised return, holding period
benchmark_outcome           benchmark return over the same window
attribution                 from portfolio_risk/attribution.py
postmortem                  structured, not prose
lesson_status               PROPOSED | VALIDATED | EXPIRED | REJECTED
confidence                  calibrated, with sample size
validity_period             explicit expiry
evidence_refs               provenance ids for every claim
```

### Rules that must hold

1. **`ADVISORY_ONLY`.** A journal lesson may enter a research prompt. It may never
   enter `PortfolioConstructionEngine`, `PortfolioRiskEngine`, Trading Guardian,
   Approval, or `ExecutionGateway`. The deterministic plane must produce identical
   output with the journal empty. Make that a test.
2. **No verbatim re-injection.** Lessons enter prompts as *structured fields*, not
   as free text. This closes the durable-injection channel.
3. **Expiry is mandatory.** No `validity_period` ⇒ not recallable.
4. **Regime-matched recall.** A lesson is recalled only when the current regime
   matches the regime it was learned in, or it is explicitly marked regime-agnostic.
5. **Point-in-time recall.** Only lessons whose outcome resolved strictly before
   the analysis date are visible — enforced centrally, tested.
6. **Promotion gate.** `PROPOSED → VALIDATED` requires more than one observation and
   should pass through `research_lab/multiple_testing.py`. A single lucky trade is
   not a lesson.
7. **Auditable.** Every recalled lesson is recorded in the decision's evidence
   manifest, so any decision can be replayed with the exact lessons it saw.

## Verdicts

| Item | Verdict |
|---|---|
| Two-phase pending → resolved design | **ADAPT — high value** |
| Alpha-vs-benchmark as the outcome measure | **ADAPT — high value** |
| Deferred reflection (no learning at decision time) | **ADAPT** |
| Bounded lesson length + rotation | **ADAPT** |
| Free-prose lesson re-injected verbatim | **REJECT** |
| No validity period / no regime tag / no sample size | **REJECT** — SaathiOS must add all three |
| Lessons influencing the final decision | **REJECT AUTHORITY MODEL** — advisory only, enforced by test |
| Plain-text log as storage | **REJECT DUPLICATE** — SaathiOS journals + storage layers already exist |
