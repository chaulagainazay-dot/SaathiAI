# M50 Workspace Model

## Hierarchy

```text
Organization
  └── Workspace(s)
        └── Project(s)
              └── Mission link(s)
```

## Isolation

- Users only see orgs they are members of.
- Sessions bind one org + one workspace.
- Cross-workspace project access denied (`PROJECT_ISOLATION`).

## State

`WORKSPACE_MODEL_ACTIVE`
