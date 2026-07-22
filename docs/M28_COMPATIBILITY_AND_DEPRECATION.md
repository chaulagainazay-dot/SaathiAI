# M28 Compatibility and Deprecation

## Wrappers retained

| Legacy | Shim | Removal criterion |
|--------|------|-------------------|
| `connectors.manager.execute` | `gov.compat.governed_manager_execute` | Zero callers; API uses ToolIntent |
| `python -m saathi.connectors.gov exec` | `execute_via_gateway` | CLI is thin gateway client only |
| Server `/api/v1/connectors/execute` | via manager shim | Rewrite to gateway |

## Properties of shims

* Call governed path only (no second transport)  
* Emit `m28.deprecation.v1` events  
* No new unsafe parameters  
* Fail closed for live adapters / financial / trading  
* `bypass=false` on results  

## Deprecation evidence

```text
docs/evidence/m28/deprecation_events.jsonl
docs/evidence/m28/connector_migration_ledger.json
```

## Unresolved / deferred callers

* Infrastructure drivers under `saathi/infrastructure/connectors/drivers/` (OUT_OF_SCOPE)  
* Ad-hoc HTTP clients outside connectors tree (technical debt, not M28 bypass count)
