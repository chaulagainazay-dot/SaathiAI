# M57 Single-Host Heartbeat

Fixes the cosmetic M56 issue where `node-local` could show `healthy=false` because
`ensure_local` wrote one heartbeat and nothing refreshed it.

## Mechanism
- `ClusterCoordinator.beat_local_node()` stamps `node-local` (and `worker-local`)
  `last_heartbeat = now`. It is the **smallest safe** liveness signal — no
  network, no execution/lease authority, no dispatcher, config-backed.
- The BFF runs `run_local_heartbeat()` as an asyncio task started on FastAPI
  startup (`start_local_heartbeat`) and cancelled on shutdown
  (`stop_local_heartbeat`). Interval: 30 s. Enabled by default; disable with
  `SAATHI_LOCAL_HEARTBEAT=0`.

## Behavior
- While the BFF runs, `node-local` health is **accurate** (heartbeat age < 90 s).
- After the process stops, no more beats occur, so health goes **stale** after the
  bounded 90 s timeout.

## Guarantees
Heartbeat changes only liveness; it never alters ownership, leases, or runtime
authority. `PlatformAgentRuntime` remains canonical; `ExecutionGateway` remains
the sole registered-tool authority. Certified by
`tests/test_m57_local.py::test_heartbeat_refresh_makes_node_local_healthy`,
`::test_heartbeat_expiry_makes_node_local_stale`, `::test_heartbeat_grants_no_authority`.
