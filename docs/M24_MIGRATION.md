# M24 Migration

## From → To

| Before | After |
|--------|-------|
| Process-local circuit dict | Durable `provider_circuit` |
| Process-local daily cost dict | Durable `daily_spend_agg` + reservations |
| Cloud engine residual exception | CANONICAL adapter |
| OpenAI-compat residual exception | CANONICAL adapter + URL policy |

## Process-local state

Ephemeral historical process-local state is **not** migrated. Durable state starts conservatively empty. Open circuits from a prior process are not reconstructed.

## Compatibility

* Public APIs preserved (`get_circuit_registry`, `process_daily_store`, provider governance CLI).
* M23 governed chat unchanged.
* M22 http_providers transport unchanged.
* Kill switches and cloud-disabled defaults preserved.

## Database

* Path: `data/provider_governance.db`
* Upgrade: `DurableGovernanceStore.upgrade()` (auto on open)
* Downgrade: `DurableGovernanceStore.downgrade()` drops M24 governance tables only

## Residual manifest

* Before M24: 2 exceptions (`engine_cloud_caller`, `engine_openai_compat`)
* After M24: 0 exceptions
* Schema: `m24.residual_exception_manifest.v1`
