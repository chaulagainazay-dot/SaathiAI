# AUTHORITY_VISIBILITY_SPEC

## Chips

| Chip | Default product truth |
| --- | --- |
| ENVIRONMENT | PRIVATE ALPHA · loopback when API is local |
| EXECUTION | GOVERNED (ExecutionGateway) |
| TRADING | PAPER_ONLY when paper overview loads |
| TG | ACTIVE / DEGRADED / BLOCKED from safety surface |
| LIVE ORDERS | always DISABLED |
| PROVIDERS | DISABLED unless payload says otherwise; never fake healthy live |
| MODEL | UNKNOWN if not in overview |
| VOICE | session state from runtime/prefs only |
| SYSTEM | from infra/overview |

## Rules

- Unknown → UNKNOWN badge (pending tone)
- Disabled → neutral (not error)
- Stale → warning when timestamps exceed bound
- Display never grants authority
