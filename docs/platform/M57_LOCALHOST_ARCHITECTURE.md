# M57 Localhost Architecture

M57 hardens SaathiOS for daily localhost use. Additive, localhost-only,
reversible. No runtime redesign, no multi-host, no production.

## Components
```
  ⌥⌘B (operator-assigned)                 macOS Shortcuts app
        │                                        │
  scripts/macos/saathi-open.sh  ───────►  bin/saathi-local (symlinked ~/.local/bin)
                                                 │  start/stop/restart/status/open/logs/doctor
                          ┌──────────────────────┴───────────────────────┐
                          ▼                                               ▼
     backend: uvicorn saathi.server:app                frontend: next dev
       127.0.0.1:8765  (+ single-host heartbeat)        localhost:3000
       node-local health kept fresh                     NEXT_PUBLIC_SAATHI_API=127.0.0.1:8765
```

## Pieces
- **Launcher** (`bin/saathi-local`) — safe process manager (PID-file + signature
  ownership; reuse healthy, stop only own; fail-closed on unrelated).
- **Heartbeat** — `ClusterCoordinator.beat_local_node()` on a 30 s BFF task keeps
  `node-local` health accurate; goes stale after stop.
- **Cold-load hardening** — operator console retries with backoff and shows a
  loading state instead of a misleading fatal on the first cold compile.
- **Local readiness** (`saathi.platform.local_readiness`) — advisory checks used
  by `doctor` and the release gate.
- **LaunchAgent** (`com.saathi.local-launcher`) — prepared, disabled by default.

## Invariants
`PlatformAgentRuntime` canonical; `ExecutionGateway` sole registered-tool
authority; localhost-only (127.0.0.1 / localhost, never 0.0.0.0, no tunnels);
production/connectors/financial/trading/multi-host all disabled.
