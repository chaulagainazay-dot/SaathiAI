# M26 Incident Response

## Incident record (typed, privacy-safe)

```text
incident_id, incident_type, severity, state,
opened_at, updated_at, resolved_at,
provider, model, check_ids, safe_summary,
evidence_refs, recommended_action, resolution
```

**Never** include raw prompts, outputs, secrets, or tokens.

## Types

```text
provider_unreachable
model_unavailable
memory_pressure
disk_pressure
repeated_timeout
invalid_provider_response
reservation_reconciliation_failed
circuit_open
startup_failed
shutdown_failed
```

## Deduplication

Open incidents with the same fingerprint (type + provider + check_ids + summary)
are not duplicated; `updated_at` is refreshed.

## Operator flow

1. `python -m saathi.inference.ops status`  
2. Inspect `docs/evidence/m26/incidents.json`  
3. Remediate (memory, Ollama, disk) — no automatic destructive actions  
4. `python -m saathi.inference.ops recover` if reservations stale  
5. Resolve incident when stable  
6. Historical M25 live PASS is **not** erased by temporary blocks  

## Alerts

Reuse existing event bus / alert-delivery patterns. M26 emits redacted
`inference.*` events; does not invent a second monitoring product.
