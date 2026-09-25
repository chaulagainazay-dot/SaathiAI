# Proposed SaathiOS Research Intelligence Layer v2

**Status: proposal only. Nothing here is implemented. No code was written.**

## Principle

SaathiOS already owns the deterministic plane. What it lacks is a qualitative
research layer feeding it. TradingAgents is that layer — badly bounded. The design
below takes the layer and imposes the boundary.

## Structure

```
                    SaathiOS market_data plane (canonical, unchanged)
                    bias_controls · provenance · corporate_actions
                    adjustments · dataset_split · signal_validation
                                      │
                                      ▼
                            MarketDataEvidence
                (typed, point-in-time, availability-dated, provenance-tagged)
                                      │
        ┌──────────────┬──────────────┼──────────────┬──────────────┐
        ▼              ▼              ▼              ▼              ▼
   Fundamental     Technical        News         Sentiment        Macro
    Analyst        Narrator        Analyst        Analyst        Analyst
   (LLM, reads    (LLM, reads     (LLM, reads   (LLM, reads    (LLM, reads
    evidence)      features)       evidence)     evidence)      regime)
        └──────────────┴──────────────┼──────────────┴──────────────┘
                                      ▼
                          Research Evidence Store
              (structured claims; each claim carries evidence_refs,
               as_of, confidence, and an UNTRUSTED_DATA provenance flag)
                                      │
                                      ▼
                        Bull Thesis  ⇄  Bear Challenge
                    (structured claims + counter-claims, bounded rounds,
                     every claim must cite an evidence_ref or be dropped)
                                      │
                                      ▼
                              Research Arbiter
              (narrative synthesis layered ABOVE the existing deterministic
               InvestmentCommittee consensus/dissent — committee stays canonical)
                                      │
                                      ▼
                     Structured Investment Thesis
              (direction, horizon, falsifiable claims, risk assumptions
               with measurable triggers, calibrated confidence, full provenance)
                                      │
                                      ▼
                        TradingIntentProposal
        (instrument, direction, conviction, thesis_ref, evidence_manifest_ref)
        ── NO quantity. NO price. NO stop. NO sizing. NO approval. ──
                                      │
╔═════════════════════════════════════════════════════════════════════════╗
║              DETERMINISTIC AUTHORITY BOUNDARY — LLM STOPS HERE          ║
╚═════════════════════════════════════════════════════════════════════════╝
                                      │
                                      ▼
                        PortfolioConstructionEngine        (proposal → sized target)
                                      ▼
                          PortfolioRiskEngine              (deterministic risk)
                                      ▼
                            Trading Guardian               (deterministic veto)
                                      ▼
                               Approval                    (explicit, separate)
                                      ▼
                           ExecutionGateway                (sole external boundary)
                                      ▼
                               Future OMS
                                      ▼
                        Paper / Shadow Broker
                                      ▼
                        Canonical Fund Ledger              (authoritative state)
                                      ▼
                    Future ReconciliationAuthority         (fails closed)
```

## Contracts

### `MarketDataEvidence`
Emitted only by the existing `market_data` plane. Every record carries
`value`, `source`, `as_of` (event time), **`available_at` (publication/filing
time)**, `vintage`, `provenance_ref`, and `trust: TRUSTED | UNTRUSTED_DATA`.
Analysts read this and nothing else — no analyst fetches.

`available_at` is the field that fixes the upstream fundamentals leak. Recall and
analysis filter on `available_at <= T`, never on period end.

### `ResearchClaim`
```
claim_id · instrument · claim_text · claim_type
evidence_refs[]        (>=1 required; a claim with none is dropped, not softened)
confidence             (calibrated)
as_of
falsifiable_by         (what observation would refute this)
source_trust           (TRUSTED | UNTRUSTED_DATA)
```

### `StructuredInvestmentThesis`
```
thesis_id · instrument · direction · horizon
supporting_claims[] · challenged_claims[] · unresolved_disagreements[]
risk_assumptions[]     (each with a measurable trigger)
confidence · regime_at_analysis
evidence_manifest_ref
```

### `TradingIntentProposal`
```
proposal_id · instrument · direction · conviction (ordinal)
thesis_ref · evidence_manifest_ref · created_at
```
Deliberately absent: quantity, notional, price, entry, stop, target, sizing,
approval. Those are `PortfolioConstructionEngine`, `portfolio_risk/sizing.py`,
and Trading Guardian territory.

## Invariants (each must be a test, not a comment)

1. **Boundary invariance.** The deterministic plane produces byte-identical output
   whether the research layer is present, absent, empty, or adversarial.
2. **No LLM write path.** No LLM output reaches `PortfolioRiskEngine`,
   Trading Guardian, Approval, `ExecutionGateway`, or the ledger — only a
   `TradingIntentProposal` reaches `PortfolioConstructionEngine`.
3. **Point-in-time.** No analyst, claim, or journal lesson may reference data with
   `available_at > T`.
4. **Provenance completeness.** Every claim in a thesis resolves to an evidence ref.
5. **Untrusted isolation.** `UNTRUSTED_DATA` never enters a system prompt
   undelimited and never enters persistent memory as free text.
6. **Advisory memory.** Journal lessons influence prompts only; removing the journal
   changes no deterministic output.
7. **Bounded cost.** Calls per instrument per day are capped by
   `research_orchestrator/budget.py`; exceeding the budget degrades the research
   layer, never the deterministic plane.
8. **Fail-safe absence.** If the research layer fails, times out, or returns
   nothing, the deterministic plane runs exactly as it does today.

## What is deliberately NOT in this design

No LangGraph. No Backtrader. No Redis. No provider SDKs. No second market-data
system. No second provider registry. No second orchestrator. No second journal
store. No LLM-generated position size, price, or approval. No execution authority
anywhere in the research layer.
