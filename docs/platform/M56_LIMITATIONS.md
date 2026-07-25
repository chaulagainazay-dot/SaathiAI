# M56 Limitations

- **Single-host only.** M56 is a foundation: workers, leases, nodes, scheduler,
  and the distributed clock are implemented and certified on a single host. No
  networking, no remote execution, no multi-host coordination backend is enabled.
- **Advisory coordination.** Leases and the scheduler are advisory metadata;
  `PlatformAgentRuntime` still performs all execution and `ExecutionGateway`
  remains the sole registered-tool authority. Nothing here dispatches work.
- **Config-backed state, single-writer.** Cluster state persists in the platform
  `config` table (no schema migration). This is restart-safe on one host but is
  not a multi-writer distributed store; concurrent multi-host writes are out of
  scope.
- **No distributed guarantees.** No consensus, quorum, or exactly-once execution
  is claimed. Recovery certification proves single-host restart/lease/heartbeat
  invariants only.
- **Metrics are single-host snapshots.** Queue latency is 0 (inline execution);
  restart_count is bounded per node.
- **Local browser certification.** The operator-console cluster surfaces are
  certified against a managed local BFF+UI+Chromium; backend contract tests are
  the CI-side guarantee.
- **No deployment, production mode, connector mutation, financial execution, or
  trading execution.** Trading Guardian remains unengaged/advisory-only.
