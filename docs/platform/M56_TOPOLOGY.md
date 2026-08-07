# M56 Runtime Topology

Read-only cluster view — `GET /cluster/topology` (RUNTIME_READ).

Reports: cluster (node + worker counts), nodes, workers, tenant-scoped leases,
runtime status, queue status (active leases), execution ownership model
(single-owner advisory lease), recovery state, logical clock, and the canonical
authority markers (`PlatformAgentRuntime`, `ExecutionGateway`).

Leases are filtered to the caller's org/workspace. No secrets, credentials,
database internals, or filesystem paths are exposed. Everything is read-only.
