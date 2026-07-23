# M50 Approval Center

## Lifecycle

```text
pending → approved | rejected | expired | revoked
approved → consumed (after one execute)
```

## Scope binding

Approvals bind: user/org/workspace, tool_id, optional project/mission, authority, side_effect, target, expiry.

Cannot be reused:

- after consume
- after revoke/expiry/reject
- for a different tool
- across org/workspace

## M49 bridge

Approved records convert to `ToolApprovalReference` for `ExecutionGateway`.

## UI

- API: `/api/v1/platform/approvals`
- Console: `/platform` + existing `/approvals` multi-source inbox

## State

`APPROVAL_CENTER_ACTIVE`
