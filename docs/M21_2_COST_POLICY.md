# M21.2 — Cost Policy

**Module:** `saathi/inference/cost_policy.py`

## Pricing

Versioned `PricingMetadata` on each provider descriptor. **No live internet pricing fetch.**

Cost status: `KNOWN | ESTIMATED | STALE | UNKNOWN | ZERO_MARGINAL | NOT_APPLICABLE`

## Estimation

* Input token estimate (chars/4, ceiling)
* Output token ceiling from request
* Fixed per-request cost
* Decimal arithmetic for enforcement (`Decimal`, not binary float ceilings)

## Enforcement

Fail closed for automatic paid fallback when:

* Price unknown
* Currency unsupported (only USD)
* Estimate exceeds request/caller/provider ceiling
* Stale pricing on cloud fallback
* Malformed / negative / extreme prices
* Caller disallows paid/cloud

Local ollama: `ZERO_MARGINAL`.

## Daily budget

`DailyCostStore` protocol + process-local `InMemoryDailyCostStore`.  
**Not durable.** Durable accounting deferred (technical debt → M21.x/M24).

Do not claim durable daily budget enforcement.
