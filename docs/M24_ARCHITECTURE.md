# M24 Architecture — Durable Provider Governance

## Target flow

```text
caller
→ canonical InferenceRequest
→ caller and privacy policy
→ durable budget check and reservation
→ durable circuit check
→ deterministic provider decision
→ ModelRouter
→ governed provider adapter
→ typed attempt result
→ durable usage settlement
→ durable circuit transition
→ typed final result
```

## Authorities (one each)

| Authority | Module |
|-----------|--------|
| Durable store | `saathi.inference.governance_store.DurableGovernanceStore` |
| Circuit state | store `provider_circuit` + registry facade |
| Cost accounting | store `cost_usage` + `daily_spend_agg` |
| Reservation | store `budget_reservation` + `GovernanceService` |
| Reset/override | store `manual_reset` / `operator_override` + audit |
| Provider decision | `saathi.inference.provider_decision` |
| Adapter boundary | `saathi.inference.adapters.*` |

## Schema (SQLite `data/provider_governance.db`)

* `provider_circuit` — state, failure_count, open_until, half-open lease, version
* `circuit_transition` — history
* `cost_usage` — estimated vs actual, idempotency_key unique
* `budget_reservation` — RESERVED/SETTLED/RELEASED/EXPIRED/CANCELLED/FAILED/RECONCILIATION
* `daily_spend_agg` — settled + reserved totals per day/caller/currency
* `governance_audit` — privacy-safe mutation log
* `operator_override` — expiring overrides (cannot enable cloud/kill/prod cert)

## Circuit semantics

CLOSED → OPEN (threshold) → HALF_OPEN (cooldown) → CLOSED (success)  
HALF_OPEN probe is lease-bound; concurrent workers cannot all probe.

Policy/cost/kill denials and user cancellations do not open circuits.

## Reservation protocol

```text
estimate → reserve (txn budget check) → mark started → provider attempt
→ settle actual OR release unused
```

Recovery classifies stale rows: safe_release | needs_reconciliation | provider_attempt_unknown | already_settled | invalid_state.

## Engine consolidation

* `CloudCallerEngine` — CANONICAL adapter wrapping `http_providers`; no residual exception.
* `OpenAICompatEngine` — CANONICAL transport with allowlisted base URL / SSRF policy.

## Invariants

```text
process-local production authorities = 0
residual inference exceptions = 0
production_certified = false
cloud fallback disabled by default
```
