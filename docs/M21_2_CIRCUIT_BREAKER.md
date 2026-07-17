# M21.2 — Circuit Breaker

**Module:** `saathi/inference/circuit_breaker.py`

## States

`CLOSED | OPEN | HALF_OPEN | DISABLED`

## Behavior

* Provider-scoped
* Default threshold 3 failures
* Cooldown 30s → HALF_OPEN single probe
* Success → CLOSED; failed probe → OPEN
* Manual reset: `python -m saathi.inference.provider_governance reset-circuit <id> --confirm`
* Kill switch evaluated **before** circuit (caller responsibility + decision layer)
* Policy denials / invalid requests: `circuit_impact=false` — do not open circuit
* Auth failures: count toward circuit; no soft failover
* Injectable clock for tests
* Telemetry privacy-safe (no prompts/secrets)

## Persistence

**M24:** authoritative state is durable SQLite (`saathi.inference.governance_store`). Restart preserves OPEN/HALF_OPEN/CLOSED and failure counts. Process-local dicts are no longer production authority.
