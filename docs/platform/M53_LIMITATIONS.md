# M53 Limitations

- Platform state and reconciliation coordination remain single-host SQLite; no
  distributed worker or multi-host consistency claim.
- A recorded dispatch with no terminal evidence requires manual resolution and
  can never be resumed/replayed by M53.
- Metrics are bounded snapshots over at most 500 recent persisted executions,
  not a metrics backend or real-time telemetry.
- Compatibility wrappers remain where required. `PlatformService.execute_tool`
  delegates to the runtime; bound `AgentExecutor` delegates to the runtime and
  otherwise fails closed; the M49 legacy allowlist bridge delegates registered
  tools through ExecutionGateway.
- The frontend is a bounded private-alpha operator surface, not browser
  certified in this milestone.
- No CI result exists until the local M53 branch is explicitly pushed.
- No deployment, production OAuth/email, live connector mutation, financial
  execution, trading execution, or production authority.
- Trading Guardian is unengaged and advisory-only.
