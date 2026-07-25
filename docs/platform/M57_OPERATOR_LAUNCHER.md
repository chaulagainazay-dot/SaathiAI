# M57 Operator Launcher — `saathi-local`

One-command localhost management for SaathiOS. Localhost-only, fail-closed,
reversible, no sudo. Script: `bin/saathi-local` (symlinked to
`~/.local/bin/saathi-local`).

## Commands
```bash
saathi-local start      # start (or reuse healthy) backend + frontend, wait ready
saathi-local stop       # stop only launcher-owned processes (graceful → force)
saathi-local restart    # stop owned, then start
saathi-local status     # backend/frontend pid, port, readiness, owner, safety
saathi-local open       # start if needed, then open http://localhost:3000
saathi-local logs        [--backend|--frontend|--launcher]
saathi-local doctor     # environment, ports, health, CORS, local readiness gate
saathi-local install-login    # write (DISABLED) LaunchAgent for login start
saathi-local uninstall-login  # remove the LaunchAgent
```

## URLs
- Frontend: `http://localhost:3000`
- API/BFF: `http://127.0.0.1:8765` (backend explicitly bound to 127.0.0.1)
- Operator console: `http://localhost:3000/platform/ops`
- Frontend API base: `NEXT_PUBLIC_SAATHI_API=http://127.0.0.1:8765` (set by the launcher)

## Runtime location
PID files and bounded logs live under `~/.saathi/` (`run/`, `logs/`) — outside the
repo, never committed. Override with `SAATHI_LOCAL_HOME`.

## Safety
Localhost-only; never binds 0.0.0.0; no tunnels; never enables production,
connectors, financial, trading, or multi-host; never requires sudo.
