# M62.7 — Fail-Closed Breaker Reset Controls

Reset is **server-authoritative** and **fail-closed**. A human approval can never
override a failing technical check; all technical checks are re-evaluated at
execution time, inside the transaction that consumes the approval.

## Flow

```
operator acknowledgement → reset request → safe-condition verification →
fresh reconciliation → market-data health → accounting invariants →
active-threshold re-check → approval verification → PlatformAgentRuntime →
ExecutionGateway → registered paper_safety.reset tool → SafetyService →
atomic reset transaction → audit evidence
```

## Prerequisites (all required)

* Breaker is `HALTED` or `ACKNOWLEDGED` (reset requests move it to `RESET_PENDING`).
* An operator **acknowledgement** exists for the trip.
* Requester holds `PAPER_SAFETY_RESET` **and is not an agent** (`is_agent_actor`).
* **Fresh reconciliation** passes with no CRITICAL drift (account scope).
* **Accounting invariants** hold (available/reserved cash ≥ 0).
* Relevant **market-data source** is healthy (no blocking market-data breaker).
* **Triggering threshold** is no longer breached (breaker re-evaluated live).
* **No broader breaker** still blocks the scope (account ⊂ workspace ⊂ tenant ⊂ global).
* **Approval** is valid, unexpired, single-use, same tenant, tool-matched, and its
  approved payload hash equals the request payload hash (scope/definition/trip bound).
* **Reset reason** provided; **idempotency key** valid; **breaker version** matches
  the version captured when the request was made (a material change invalidates it).

## Reset denial matrix

| Failing condition | Check that fails |
|-------------------|------------------|
| Corruption / CRITICAL drift remains | `reconciliation_clean` |
| Loss / drawdown / exposure / rejection still breached | `threshold_cleared` |
| Market data stale/invalid | broader/market-data breaker blocking |
| Global or tenant breaker active | `no_broader_breaker` |
| Approval missing | `approval_valid` |
| Approval expired | `approval_valid` |
| Approval reused (already CONSUMED) | `approval_valid` |
| Approval cross-tenant | `approval_valid` |
| Approved payload/scope differs | `approval_valid` |
| Self-approval by requester | `approval_valid` |
| Breaker changed after approval | `breaker_version_match` |
| Requester is an agent | `PERMISSION_DENIED` (pre-check) |
| Requester lacks `PAPER_SAFETY_RESET` | `PERMISSION_DENIED` (pre-check) |

On denial: **no state change to NORMAL, no approval consumption, halt retained**;
`RESET_PENDING` returns to `ACKNOWLEDGED` so a legitimate retry is possible once the
underlying condition clears. The decision (with all checks) is persisted.

## A successful reset

Transitions `RESET_PENDING → RESET → NORMAL` (both legal edges asserted), clears the
last trip, and unhalts the paper account **only** when no other breaker still blocks
it. It runs in one atomic transaction with approval consumption.

A successful reset must **not** and does **not**: modify fills, positions, cash,
ledger; execute repairs; approve orders; resume live trading; change environment;
enable leverage/margin. It transitions protective breaker/halt state only.

## Approval integration

Uses the existing Approval Center (`ApprovalRecord`). Approval consumption is atomic
with the reset transaction (`UPDATE approvals SET status=CONSUMED ... WHERE
status=APPROVED`), so it is single-use by construction. The approved
`target_resource` carries the request payload hash — any scope/definition/trip change
breaks the match. A paper reset approval (`tool_id="paper_safety.reset"`,
`capability="paper_safety_reset"`, `authority="LOCAL_MUTATION"`) never authorizes
live trading.

## Runtime / Gateway mediation

All manual trips, acknowledgements, reset requests, and resets route through
`saathi.platform.safety.orchestration` → `ExecutionGateway.execute_registered_tool`
→ registered `paper_safety.*` tool → `SafetyService`. The reset tool is
`LOCAL_MUTATION` / `LOCAL_IRREVERSIBLE` / `EXPLICIT_APPROVAL_REQUIRED` /
`IDEMPOTENCY_KEY_REQUIRED` — never `FINANCIAL_EXECUTION`. No API route or agent
mutates breaker state directly; there is no bypass around Runtime/Gateway.
