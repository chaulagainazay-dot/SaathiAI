# M62.7 — Safety Alert Escalation

Every breaker trip emits a durable, tenant-scoped alert persisted in
`safety_alerts` (same SQLite DB), plus an audit event via the platform audit sink.
No disconnected alert service is introduced; no external transport is required.

## Alert content

```
breaker type, scope + scope_ref, severity, alert level, trip timestamp,
metric snapshot, threshold, reason codes, correlation id, open-order policy,
required operator action, reconciliation run id (when applicable)
```

Alerts never contain secrets or full sensitive source text.

## Levels & posture

| Posture | Alert level | Attention |
|---------|-------------|-----------|
| WARNING breach (e.g. concentration warn band) | `WARNING` | non-blocking |
| TRIPPED / HALTED | `ERROR` / `CRITICAL` | blocking, high-priority |

`INVALID_MARKET_DATA`, `RECONCILIATION_CRITICAL` and `ACCOUNTING_INVARIANT` map to
`CRITICAL`; other trips to `ERROR`; soft warnings to `WARNING`.

## Behaviour

* Alerts are **tenant-scoped** — another tenant's listing is empty.
* A blocking trip writes the alert **atomically** with the trip + halt (one
  transaction); a rollback removes the alert too (no orphan alerts).
* **Duplicate sweep evaluations do not produce duplicate alerts** — a blocking
  breaker is not re-tripped.
* **Acknowledgement** marks the alert acknowledged (audited) but does **not** reset
  the breaker or remove the halt.

## Transport

Credential-free local durable persistence only. External email / SMS / Slack /
Telegram / webhook delivery is **out of scope** and not implemented. No network
call, no credential field.
