**Production authorized: false.** Local-only private alpha.

# Private Alpha Operations

## Lifecycle

All start/stop/restart/status/open/logs operations use `bin/saathi-local`
(via `bin/saathi-alpha`):

| Command | Behavior |
| --- | --- |
| start | Start owned backend/frontend on localhost only |
| stop | Stop **launcher-owned** processes only |
| restart | stop + start |
| status | Exact service health + ownership |
| doctor | Prepare + local readiness + listener scan |
| open | Open browser only if fully ready (fail-closed) |
| logs | Tail bounded logs under `~/.saathi/logs` |

## Process ownership rules

1. PID file + command signature must both match
2. Unrelated processes on the port are **never** killed
3. Stale PID files are reported, not acted on aggressively
4. No `pkill` / `killall` by process name

## Ports

| Service | Bind | Port |
| --- | --- | --- |
| Backend | 127.0.0.1 | 8765 |
| Frontend | localhost | 3000 |

## Configuration

Versioned config: `data/alpha/config/alpha_config.json`

- Schema validated; secret-shaped keys rejected
- Localhost-only host
- History under `data/alpha/config/history/` for rollback
- `automation_execution_enabled` default **false**

## Upgrade (local fixtures only)

```bash
bin/saathi-alpha upgrade-preflight
# apply_local_upgrade is programmatic; no remote auto-update
```

Upgrade flow: preflight → record version → backup → disk check → schema
compatibility → migrate config → smoke → commit or rollback.
