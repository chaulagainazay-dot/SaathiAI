# M62.8 — Trading UI Authority Model

The browser workspace is a **read + bounded-action** surface. It holds no authority.
Every mutation is server-enforced through the canonical chain.

## Authority chain (unchanged)

```
Browser (this workspace)
  → authenticated API (/api/v1/platform/*, X-Platform-Token)
    → PlatformAgentRuntime
      → ExecutionGateway (registered tool, fail-closed)
        → SafetyService / PaperTradingService / ReconciliationEngine
          → single-host SQLite
```

The frontend **never**: writes SQLite, calls service classes directly, fabricates
success, mutates financial state locally, bypasses permissions, bypasses the Approval
Center, bypasses Runtime/Gateway, provides a live-trading control, or shows fake live
prices.

## Permission matrix (backend authoritative; UI hides for clarity only)

| Action | Permission | UI gate |
|--------|-----------|---------|
| View any trading surface | `paper_safety.read` / `paper_*.read` | always shown when signed in |
| Run safety sweep | `paper_safety.sweep` | "Run safety sweep" button |
| Reconcile (integrated) | `paper_safety.sweep` | "Reconcile all" button |
| Manual trip | `paper_safety.trip` | (server-gated; broad scopes owner/admin) |
| Acknowledge trip | `paper_safety.acknowledge` | "Acknowledge" button |
| Request reset | `paper_safety.reset_request` | "Request reset" button |
| Execute reset | `paper_safety.reset` | "Execute reset" button |
| Configure breaker | `paper_safety.configure` | (owner/admin) |
| Read approvals | `approval.read` | Approvals table / permission-restricted state |

Frontend-hidden controls are **not** security — the backend denies regardless
(`ctx.require_permission` + `is_agent_actor`). Agents are additionally blocked from
acknowledge / configure / reset / trip by `is_agent_actor`, independent of the UI.

## Reset authority (fail-closed)

The reset UX mirrors the server sequence and never implies approval is sufficient:

1. Review trip evidence → 2. Acknowledge (halt retained) → 3. Request reset →
4. Obtain Approval Center approval → 5. Execute reset → 6. **Server re-runs**
reconciliation + accounting invariants + market-data health + active-threshold +
broader-breaker + breaker-version + approval checks → 7. success or exact denial.

Certified behaviours (browser):
- Acknowledgement keeps the account **HALTED**.
- Reset **without approval** → `400 approval required`, halt retained.
- Reset **with a valid, scope-bound, single-use approval** → succeeds only after all
  server checks pass; the account unhalts and **no financial state changes** (cash,
  positions, ledger unchanged).
- The panel states: *"Human approval cannot override failing technical checks.
  Approval alone is never sufficient."*

## Truthful data framing

- Environment: **PAPER**. Authority: **SIMULATION ONLY**. Live execution:
  **UNAVAILABLE**.
- Marks are labelled **REPLAY / FIXTURE DATA** — never "Live price".
- Repair plans are labelled **PLAN ONLY — NEVER AUTOMATICALLY EXECUTED**; there is no
  execute/apply control anywhere.
- Evidence is read-only with no mutation controls.
- Approvals: *"Approval does not remove a halt … Paper approval never grants
  live-trading authority."*

No live broker, real funds, leverage, margin, short selling, derivatives, borrowing,
withdrawal, production deployment, or autonomous capital allocation is exposed.
