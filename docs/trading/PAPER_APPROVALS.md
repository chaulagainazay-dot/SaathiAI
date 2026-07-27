# Paper Approvals & Permissions (M62.5)

## Server-owned approvals — no second subsystem

Paper-order submission reuses the existing M50/M51 **Approval Center**
(`ApprovalRecord`, `PlatformStore.get_approval` / `consume_approval_if_approved`).
No parallel approval system is introduced.

Two independent gates both apply to every gateway submission:

1. **Tool-runtime scope check** — the `paper.order.submit` manifest is
   `EXPLICIT_APPROVAL_REQUIRED`. `orchestration.submit_via_gateway` builds a
   server-side `ToolApprovalReference` (tool_id, tool_version, capability, authority,
   side-effect, actor), which `ToolExecutionService` re-validates immediately before
   the adapter runs. UI-only authority is never accepted.
2. **Service verification + atomic consumption** — `PaperTradingService._verify_approval`
   checks the `ApprovalRecord` is present, **tenant-matched** (cross-tenant rejected),
   `APPROVED`, unexpired, and not self-approved. Consumption
   (`APPROVED → CONSUMED`) runs **inside the same SQLite transaction** as the order
   write via `persist_submit`'s `consume_approval` callback, so consumption is atomic
   with submission authorization.

Consequences (tested):
- Every gateway submission requires a valid approval (`test_gateway_missing_approval_blocked`).
- A consumed approval cannot be reused (`test_gateway_reused_approval_blocked`).
- A cross-tenant approval is rejected and leaves no order
  (`test_gateway_cross_tenant_approval_rejected`).
- A successful submit flips the approval to `consumed`
  (`test_gateway_submit_consumes_approval_and_fills`).
- Modifying an approved intent invalidates the prior authorization (a new intent →
  new approval requirement).
- Approval records never authorize live trading.

The Trading Guardian may still veto **after** approval if account or market
conditions changed — a Guardian pass is never described as trade approval.

## Permission matrix (`paper_*`)

| role | read | create acct | propose | submit | cancel | halt |
|---|---|---|---|---|---|---|
| viewer | ✓ | | | | | |
| operator | ✓ | ✓ | ✓ | ✓ | ✓ | |
| owner / admin | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| system | ✓ | ✓ | ✓ | ✓ (event processing) | ✓ | ✓ |

Permissions: `PAPER_ACCOUNT_READ`, `PAPER_ACCOUNT_CREATE`, `PAPER_ORDER_READ`,
`PAPER_ORDER_PROPOSE`, `PAPER_ORDER_SUBMIT`, `PAPER_ORDER_CANCEL`,
`PAPER_ACCOUNT_HALT`. Agents do **not** gain approval-decision or account-halt
permissions by default; an agent cannot approve its own order or self-grant
approval permissions.
