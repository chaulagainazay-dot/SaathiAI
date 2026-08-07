# M53 Binding Administration

## Model

A binding contains a stable binding ID, agent identity, display metadata,
organization/workspace scope, optional project/mission constraints, tool and
capability allowlists, authority ceiling, lifecycle state, version,
creator/updater identities, and timestamps.

The workspace uniqueness key is `(organization, workspace, agent_id)`. Multiple
agent identities are supported within a workspace.

## Lifecycle

```text
ACTIVE → SUSPENDED → ACTIVE
ACTIVE → REVOKED
SUSPENDED → REVOKED
REVOKED → (no transitions)
```

Suspension, activation, revocation, security metadata changes, and explicit
rotation increment the binding version. Revoked bindings are immutable.

## Permissions and ceilings

- Viewer: binding summaries only.
- Operator: use an active binding; cannot administer it.
- Owner: administer workspace bindings up to `EXTERNAL_MUTATION`.
- Admin/system: administer up to `SECURITY_SENSITIVE`.
- Financial, trading, unknown, and unsupported authority ceilings are rejected.
- Owner-configured authority ceilings may only narrow these role ceilings.

All reads and mutations are scoped to token-trusted organization/workspace
context. Cross-workspace identifiers return a non-enumerating not-found error.
