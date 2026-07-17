# M30 — Security

## Invariants preserved

```text
production_certified = true (computed)
connector rollout = OFF
inference rollout = OFF
connector bypasses = 0
connector conformance bypasses = 0
direct provider bypasses = 0
process-local production authorities = 0
residual inference exceptions = 0
cloud fallback = disabled
live credentials used in M30 = 0
live external accounts connected = 0
Trading Guardian = UNCHANGED / UNENGAGED
```

## Enforced

* Secret redaction in evidence packages
* Approval required for external mutations
* Trust / PROHIBITED / trading connectors blocked
* Side-effect floors (financial, account change, trading)
* Direct adapter execute outside allowlisted paths = bypass
* Caller cannot override certification via payload
* ACTIVE/CANARY require fresh connector certification
* Revocation blocks activation without deleting prior evidence

## Trading Guardian boundary

No exchange, broker, order-entry, withdrawal, or payment-transfer connectors
are certified for execution. Named trading-like IDs assess as FAILED / PROHIBITED.
