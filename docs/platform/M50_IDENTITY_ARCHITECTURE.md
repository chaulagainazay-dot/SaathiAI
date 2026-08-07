# M50 Identity Architecture

## Purpose

Provide a fail-closed identity chain for every platform execution, on top of the M49 tool runtime.

## Chain

```text
User → Role → Organization → Workspace → Project → Mission → Run → Approval → ExecutionGateway
```

Anonymous execution is **prohibited**.

## Components

| Layer | Module |
|---|---|
| Models | `saathi.platform.models` |
| Store | `saathi.platform.store.PlatformStore` (SQLite `data/platform/platform.db`) |
| Context | `saathi.platform.context.PlatformExecutionContext` |
| Service | `saathi.platform.service.PlatformService` |
| API | `/api/v1/platform/*` |
| Sessions | Platform sessions with hashed tokens, expiry, revocation |

## Rules

1. Session token required for context.
2. Membership role resolved per organization.
3. Workspace must belong to session org.
4. Project must belong to session workspace/org.
5. Mission must belong to session org (and project when bound).
6. Execution always uses `ExecutionGateway.execute_registered_tool`.

## Relationship to existing systems

- Does **not** replace `saathi.security.store` (auth v1.2 passwords/passkeys).
- Does **not** replace `saathi.missions.store` (business Mission OS).
- Platform missions are **links** for tenancy isolation; legacy MissionStore remains for domain ops.

## State

`IDENTITY_ACTIVE`
