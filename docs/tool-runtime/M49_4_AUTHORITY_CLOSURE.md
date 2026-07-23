# M49.4 Authority and Approval Closure

## State

`AUTHORITY_FAIL_CLOSED`

## Manifest-owned authority

Callers cannot lower authority or alter side-effect class via arguments.
`m49.financial_execution_stub` remains PROHIBITED with adapter_invoked=False even if
caller supplies authority_class overrides in arguments.

## Approval

ToolApprovalReference fields: action, target_resource, tool_id, expiry, revoked, active.
Action/target scoped; expiry and revocation enforced in ToolExecutionService.

## Trading Guardian

```text
TRADING_GUARDIAN_UNENGAGED_ADVISORY_ONLY
ADVISORY_ONLY / NO_LIVE_EXECUTION / LEVERAGE_DISABLED
```

## Tests

`audit_authority_closure`, `tests/test_m49_3_trading_boundary.py`, M49.1 security suite.
