# PERFORMANCE-ATTRIBUTION-V2 — deterministic attribution over canonical records

Branch `feature/nepse-completion`, from `2e2e6042` (verified HEAD, clean, in sync).
All seven foundation milestones confirmed as ancestors before starting.

## Discovery — attribution already existed

| Component | Verdict |
|---|---|
| `tg/attribution_v2.py` — strategy/asset/venue/asset-class grouping, gross/cost/net, benchmark, drawdown, `reconciles()` | **EXTEND** — this is the authority |
| `portfolio_performance/engine.py` (666 lines) — NAV, PnL, drawdown, contribution over the fund ledger; "read/derived only, zero mutation authority" | **KEEP** — different scope, no overlap |
| `tg/portfolio_risk/attribution.py` — Brinson-lite over SYNTHETIC series, labelled research-only | **KEEP, DEFER** — explicitly not accounting |
| `production_readiness/performance.py` | **REJECT** — release gating, unrelated |

No second attribution authority was created. The existing `attribute()` and
`reconciles()` are untouched in behaviour; their nine tests still pass.

## The gaps that were real

1. **A generic `cost` bucket.** Fee, spread and slippage exist in the shadow
   records but were collapsed into one number. "Costs were 90" cannot tell you
   which lever to pull.
2. **No decision-layer visibility.** Nothing recorded that a 20% request became
   8% after construction and 5% after risk.
3. **Guardian counted, never classified.** Blocked trades were tallied; whether
   blocking helped or hurt was not measurable, even though SHADOW-TRADING-1
   already stores the forward path.
4. **Evidence classes merged.** Accounting facts and counterfactual estimates sat
   in one dict with no label separating them.
5. **`_dec` bypassed FINANCIAL-NUMERIC-1** — `Decimal(str(v))` accepted `"NaN"`
   and `"Infinity"`, so a non-finite number could enter a total, a comparison, or
   a reconciliation check. Now delegates to the fail-closed parser.
6. **No bridge to canonical records.** Attribution took hand-built inputs; nothing
   derived them from the durable shadow session.

## Design

`performance_attribution_report()` composes the existing `attribute()` and labels
every block with an `EvidenceClass`:

- `ACCOUNTING_ATTRIBUTION` — derived from records of what happened.
- `COUNTERFACTUAL_ESTIMATE` — what a frozen, versioned rule says would have
  happened to a decision never executed.
- `OBSERVATIONAL_ASSOCIATION` — context, no causal claim.

These are never merged, and a counterfactual is never added to realized PnL — a
test drives a 30,000 counterfactual past a 100 realized result and asserts the
totals do not move.

`DecisionLayerRecord` reports exposure **transformations**, not returns.
"Construction removed 12 percentage points" is an accounting fact about the
decision; "construction earned 2%" would be a counterfactual claim, and this
record refuses to imply it.

`attribution_source.py` bridges the shadow session to those types. It reads only,
and where the session cannot support a field the field is absent rather than zero
— an open position with no mark contributes its realized part only, because
marking it at cost would assert a flatness nobody observed.

## Limitations

- **NEPSE attribution is unexercised.** The types are asset-class agnostic, but
  there is no NEPSE execution data to attribute; the crypto shadow path is what is
  certified.
- **Strategy attribution is session-scoped.** A shadow session records one
  strategy version, so a session mixing strategies reports
  `AMBIGUOUS_PROVENANCE` rather than splitting a fill by guess.
- **Cash drag is not implemented.** Separating an allocation effect from a trading
  cost needs a benchmark-relative weight series the shadow session does not yet
  record. Reported as absent rather than approximated.
- **PIT safety is structural, not enforced.** Attribution consumes only records
  the caller supplies; it performs no lookup that could reach a later revision.
  A dedicated PIT harness belongs with the market-data layer.
