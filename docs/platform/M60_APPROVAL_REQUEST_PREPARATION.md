# M60 — Approval Request Preparation

Route: `/platform/approvals/new`. Behavior: **LIVE** — `POST /approvals` (request).

This prepares a scoped request; it is not the decision screen. `buildApprovalRequest()`
produces both a review preview and the exact server body, and validates required
fields (tool, reason, operator acknowledgement).

Review shows: who is requesting, what authority, exact scope (org/workspace/project/
mission), tool, risk, expiration, single-use. On submit, `POST /approvals` runs, then
the flow refetches `/approvals?status=` and confirms the record before navigating to
the approval detail (server reconciliation). Never fabricates approval lifecycle
state. Role-gated by `request_approval`.
