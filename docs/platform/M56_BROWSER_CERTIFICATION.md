# M56 Browser Certification

Harness: `saathi-os/scripts/m56_browser_cert.mjs` (`npm run cert:m56`).
Evidence: `docs/platform/m56_evidence/m56_browser_cert.json` + `screenshots/`.

## Lifecycle
clean ports → isolated `SAATHI_PLATFORM_DB` → start BFF (`saathi.server:app`,
CORS scoped to the managed UI origin) → seed owner + binding + governed execution
via API → start UI → inject the session token and drive the authenticated
`/platform/ops` operator console (now including the cluster surfaces) in headless
Chromium → screenshots + evidence JSON → teardown (kill UI/BFF, remove the
disposable database).

Exit 0 only when every hard gate passes. Never fabricates network success, never
marks a PR ready, never enables connectors, financial, or trading execution.

## Gates

**API contract (server-to-server):** the M54/M55 gates plus M56 distributed
gates — topology (canonical runtime + sole gateway + ≥1 node), node_health
(`node-local` present), distributed_metrics, worker_registry (register),
lease_coordination (single-owner acquire → HELD), cluster_recovery
(PASS/WARNING, `no_replay` invariant).

**Operator console (real Chromium):** the M55 console gates plus M56 cluster
cards — ops_topology (PlatformAgentRuntime + ExecutionGateway + nodes),
ops_node_health (`node-local`), ops_scheduler_metrics (`single_host_inline` +
leases), ops_cluster_recovery (PASS/WARNING + `no_replay`), no_unsafe_actions.

## Surfaces validated
Worker Registry, Topology, Scheduler, Lease dashboard, Node Health, Worker
Health, Recovery, Runtime Ownership, Operator Console.

## CI status
Certified **locally** (managed BFF+UI+Chromium). The reliability CI full-suite
runs the deterministic backend contract tests (`tests/test_m56_cluster.py`) as
the CI-side guarantee; the full browser run is kept local and is not falsely
claimed as CI-certified.

## Result
The recorded verdict and per-gate results for the current run are in
`docs/platform/m56_evidence/m56_browser_cert.json`.
