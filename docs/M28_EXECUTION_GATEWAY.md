# M28 ExecutionGateway Enforcement

## Contract

All migrated connector production execution enters through `ExecutionGateway.submit(ToolIntent)`.

The gateway enforces:

* typed ToolIntent validation  
* permission (actor, connector, operation)  
* risk / approval binding (digest)  
* idempotency  
* durable ExecutionRecord  
* family handler dispatch  

The **connector** family handler (M28) then runs `GovernedConnectorRuntime.execute`, which enforces:

* rollout mode  
* lifecycle  
* package certification (ACTIVE)  
* connector policy  
* side-effect class (caller cannot override)  
* approval tokens for mutations  
* auth references  
* rate limits  
* timeout  
* redacted evidence  
* incidents (deduped)  

## Result shape (ConnectorResult)

```text
request_id, status, connector_id, operation, executed,
side_effect_class, approval_state, policy_state, rollout_state,
idempotency_state, safe_output, evidence_refs, incident_id,
bypass=false, error_code, safe_message
```

## Direct adapter access

Allowed only for:

* unit tests  
* isolated adapter validation  
* framework internals (`saathi/connectors/gov/`)  

Enforced by structure (adapters not exported as public execute API) and `bypass_guard` scan.

## Platform ExecutionEngine

`ExecutionEngine.execute` already preferred the gateway. M28 removes the substrate-only fallback when the gateway is unavailable or submit errors — fail closed with `m28_fail_closed`.
