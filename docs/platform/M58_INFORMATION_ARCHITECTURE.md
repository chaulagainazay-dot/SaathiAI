# M58 — Information Architecture

## Home (`/platform`) — central spatial command
- **Core (SaathiCore):** SaathiOS / PlatformAgentRuntime state — one of READY /
  ATTENTION / BLOCKED / IDLE / UNKNOWN + Local Private Alpha + compact real metrics.
- **Module ring (12):** Missions, Projects, Agents, Runtime, Approvals, Attention,
  Bindings, Evidence, Operations, Memory, Automation, Settings. Each node shows icon,
  name, status pulse, live count/detail.
- **Glass detail panels** (mounted, cert-visible): Operational readiness (safety
  labels, evidence export, retention dry-run), Runtime summary, Agent bindings,
  Runtime attention, Recent executions + lifecycle timeline, Projects, Approvals,
  Configuration.

The first screen answers: *What is Saathi doing? What needs my attention? What is safe?
What is blocked? Where do I go next?*

## Operations (`/platform/ops`) — constellation
Central "Runtime Operations" node with connected nodes: Health, Metrics, Release,
Topology, Nodes, Scheduler, Recovery, Backup, Localhost, Security. Each node carries
live data inline (preserving all data-testids); selecting opens a contextual glass
drawer.

## Module → source mapping (all live or explicit-unavailable)
| Module | Signal source | Route |
|---|---|---|
| Missions | runtime executions | `/missions` |
| Projects | `/projects` | `/projects` |
| Agents | agent bindings | `/agents` |
| Runtime | `/runtime/metrics` | in-page `#mod-runtime` |
| Approvals | `/approvals?status=pending` | `/approvals` |
| Attention | `/runtime/attention` | in-page `#mod-attention` |
| Bindings | `/agent-bindings` | in-page `#mod-bindings` |
| Evidence | (verification) | `/evidence` |
| Operations | `/runtime/diagnostics` | `/platform/ops` |
| Memory | — | `/knowledge` |
| Automation | — | `/automation` |
| Settings | — | `/settings` |

## Data integrity rule
Counts/status come from live APIs; absent data yields "Unavailable"/"UNKNOWN"/"—",
never invented values. `moduleState` returns UNKNOWN (dashed) rather than a false zero
when no datasource is bound.
