# M54 Operator Workflows

The certified private-alpha operator path, as exercised through the `/platform`
browser surface and the platform API.

1. **Sign in** — bootstrap owner (first run) then `POST /auth/login`; the UI
   stores the session token client-side (`saathi_platform_token`) and sends it
   as `X-Platform-Token`.
2. **Enter organization / workspace** — `GET /me` resolves tenancy from the
   session; switching is restricted to authorized membership.
3. **Administer agent bindings** — create, list, inspect, update, suspend,
   activate, rotate, revoke through `/agent-bindings*`. Authority ceiling and
   allowed tool scope are server-enforced.
4. **Enter project / mission context** — `/projects`, `/missions`.
5. **Initiate governed execution** — `/execute` (or `/agent/execute`) routes
   through `PlatformAgentRuntime` → `ExecutionGateway`.
6. **Handle approval** — mutations enter `WAITING_APPROVAL`; owners decide via
   `/approvals/{id}/decide`; approvals are single-use.
7. **Inspect runtime state** — `/runtime/executions`, `/runtime/executions/{id}`,
   `/runtime/metrics`, `/runtime/diagnostics`.
8. **Respond to attention** — `/runtime/attention` classifies every waiting,
   paused, uncertain, timeout, cancellation, binding, and context condition.
9. **Safe reconciliation** — `/runtime/executions/{id}/reconcile` with permitted
   actions only; uncertain recorded dispatch cannot replay.
10. **Inspect audit & lifecycle evidence** — `/runtime/executions/{id}/timeline`,
    `/audit`. Raw arguments, results, tokens, and secrets are never shown.
11. **Export bounded evidence** — `/runtime/export` (JSON/CSV) with a
    deterministic manifest and content hash.
12. **Recover from interruption** — see `M54_RECOVERY_REHEARSAL.md`.
13. **Remain tenant-isolated** — every step is scoped to the caller's org and
    workspace; cross-tenant access fails closed.

## Diagnostics & retention (readiness panel)

The `/platform` readiness panel shows environment classification (LOCAL_OR_TEST),
private-alpha and non-production labels, safety badges (connectors DRY_RUN_ONLY,
financial DISABLED, trading DISABLED, guardian UNENGAGED_ADVISORY_ONLY),
diagnostics counts, evidence export buttons, and — for owners/admins — a dry-run
retention preview. No control on this surface enables connectors, financial
execution, or trading.
