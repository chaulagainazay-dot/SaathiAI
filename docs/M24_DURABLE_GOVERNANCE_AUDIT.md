# M24 — Durable Governance State Audit

**Milestone:** Platform M24  
**Baseline HEAD:** `00bfae9`  
**Evidence tier:** repository source + focused tests  

## Questions

| # | Question | Answer |
|---|----------|--------|
| 1 | Where are circuit/cost state stored? | **Before:** process-local dicts in `circuit_breaker.py` / `InMemoryDailyCostStore`. **After:** SQLite `data/provider_governance.db` via `DurableGovernanceStore`. |
| 2 | Which processes can mutate them? | Only governance store / service / CLI with confirm; adapters and product callers cannot write ledger/circuit rows. |
| 3 | Can transitions be durable and transactional? | Yes — `BEGIN IMMEDIATE` + versioned circuit rows + unique idempotency keys. |
| 4 | Budget reserved before execution? | Yes — `reserve_budget` / `GovernanceService.reserve_for_attempt`. |
| 5 | Actual cost settled after? | Yes — `settle_reservation` writes `cost_usage` and adjusts daily aggregates. |
| 6 | Stale reservations recovered? | Yes — `recover_stale_reservations` (safe_release / reconciliation_required). |
| 7 | Retries avoid double charge? | Separate `attempt_id` + unique usage/reservation idempotency keys. |
| 8 | Circuit survives restart? | Yes — proven in tests (`test_circuit_open_survives_restart`). |
| 9 | Concurrent workers share authority? | Yes — multi-process budget test + concurrent half-open probe bound. |
| 10 | Cloud + openai_compat residuals removed? | Yes — both CANONICAL adapters; manifest exceptions = 0. |
| 11 | Operator resets auditable? | Yes — `manual_reset` / overrides require confirm + `governance_audit`. |
| 12 | Production fail-closed without live cert? | Yes — `production_certified=false`; live cert remains ENVIRONMENT_BLOCKED. |

## Inventory

| State ID | File | Symbol | Storage | Classification | M24 action |
|----------|------|--------|---------|----------------|------------|
| CB-REG | `saathi/inference/circuit_breaker.py` | `ProviderCircuitBreakerRegistry` | Durable store (private `:memory:` or global DB) | CANONICAL_DURABLE | Migrated authority off process dict |
| CB-GLOBAL | `circuit_breaker.py` | `get_circuit_registry` | `data/provider_governance.db` | CANONICAL_DURABLE | Default durable |
| COST-INMEM | `cost_policy.py` | `InMemoryDailyCostStore` | process dict | TEST_FAKE | Not production authority |
| COST-DURABLE | `cost_policy.py` | `DurableDailyCostStore` / `process_daily_store` | governance store | CANONICAL_DURABLE | Production default |
| GOV-STORE | `governance_store.py` | `DurableGovernanceStore` | SQLite | CANONICAL_DURABLE | New sole authority |
| GOV-SVC | `governance_service.py` | `GovernanceService` | store | CANONICAL_DURABLE | Reservation protocol |
| ENGINE-CLOUD | `adapters/cloud.py` | `CloudCallerEngine` | n/a (transport) | CANONICAL | Residual removed |
| ENGINE-OAI | `adapters/openai_compat.py` | `OpenAICompatEngine` | n/a (transport) | CANONICAL | Residual removed; SSRF URL policy |
| HTTP-TRANSPORT | `adapters/http_providers.py` | family callers | n/a | CANONICAL_TRANSPORT | Unchanged M22 |

## Required outcomes

```text
UNKNOWN = 0
PROCESS_LOCAL_PRODUCTION_AUTHORITIES = 0
UNCLASSIFIED_GOVERNANCE_STATE = 0
```

## Currency and time

* Money: `Decimal` / TEXT fixed precision; binary float rejected.
* Timestamps: UTC epoch seconds.
* Budget day timezone: `SAATHI_BUDGET_DAY_TZ` (default `UTC`).

## Trading Guardian

```text
UNCHANGED
UNENGAGED
LIVE TRADING NOT AUTHORIZED
```
