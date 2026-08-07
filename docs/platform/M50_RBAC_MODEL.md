# M50 RBAC Model

## Roles

| Role | Intent |
|---|---|
| `viewer` | Read surfaces only |
| `operator` | Create work, request approvals, execute tools |
| `owner` | Decide approvals, manage org users/settings |
| `admin` | Full org admin (non-system) |
| `system` | Full permission set (service principals) |

## Permissions

See `PlatformPermission` enum: platform/workspace/project/mission/approval/settings/connector/audit/runtime/session.

## Inheritance

```text
viewer ⊂ operator ⊂ owner ⊂ admin
system = all permissions
```

## Enforcement

- `PlatformExecutionContext.require_permission`
- Service methods gate before mutations
- API returns 403 on denial

## State

`RBAC_ACTIVE`
