# M24 Release Check

**Command:** `python -m saathi.inference.release_check`

## New rules (M24)

| rule_id | Intent |
|---------|--------|
| `m24_residual_exceptions_nonzero` | Manifest exceptions must be 0 |
| `m24_engine_residual_reintroduced` | cloud/openai_compat exceptions must not return |
| `m24_governance_modules_missing` | durable modules present |
| `m24_schema_marker_missing` | schema/protocol markers |
| `m24_engine_not_canonical` | engines CANONICAL |
| `m24_circuit_not_durable` | circuit uses governance store |
| `m24_cost_not_durable` | durable daily cost |
| `m24_adapter_circuit_mutation` | adapters must not mutate circuits |
| `m24_adapter_budget_mutation` | adapters must not mutate budgets |
| `m24_openai_compat_ssrf_missing` | URL policy present |
| `m24_float_money_not_rejected` | float money rejected |
| `m24_production_certified_true` | production_certified stays false |

Offline, no network.
