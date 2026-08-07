# M56 Distributed Runtime Foundation

Prepares SaathiOS for future multi-host operation while preserving identical
single-host behavior. Additive, advisory, deterministic, fail-closed, backwards
compatible. **No production rollout, no platform rewrite, no runtime replacement.**

## Canonical authority unchanged
`PlatformAgentRuntime` remains canonical; `ExecutionGateway` remains the sole
registered-tool execution authority. Leases, workers, nodes, and the scheduler
are **advisory coordination metadata only** — nothing in M56 executes a tool,
dispatches work, or creates a second execution/approval path. Everything runs
locally; no networking is performed.

## Abstractions (`saathi/platform/cluster.py`)
- **RuntimeNode** — a host in the (currently single-node) cluster.
- **RuntimeCluster** — nodes + workers + leases snapshot.
- **WorkerLease / ExecutionLease** — single-owner advisory ownership of an
  execution (prevents a second worker claiming the same execution).
- **RuntimeHeartbeat** — worker liveness signal + logical tick.
- **DistributedClock** — wall time from the store plus a persisted logical
  counter; the same interface backs a future multi-host logical clock.

## Services (facade: `ClusterCoordinator`)
Worker Registry, Lease Coordinator, Scheduler Foundation, Topology, Node Health,
Distributed Metrics, Recovery Certifier — see the per-topic M56 docs.

## Persistence
State lives in the existing platform `config` table (`m56_nodes`, `m56_workers`,
`m56_leases`, `m56_scheduler`, `m56_logical_clock`). **No schema migration**, so
M56 is fully backwards compatible with M55 and restart-safe (config persists).

## Single-host guarantee
`ensure_local()` represents the current process as one `node-local` +
`worker-local`. All behavior is identical to M55; the abstractions simply make a
future multi-host deployment a configuration/scale change rather than a rewrite.
