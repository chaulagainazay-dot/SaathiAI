# M64 — Registry Authority Model

## Principle

The **backend `ModuleRegistry` is the single authoritative source** for browser
module discovery, availability, health, navigation, and dashboard composition. The
frontend static mirror is a **non-operational fallback skeleton only**.

```
Backend ModuleRegistry  (authoritative)
  → GET /api/v1/platform/modules            (authenticated, permission-filtered)
    → module client (client.js)             (fetch + classify + validate)
      → shell bootstrap machine (bootstrap.js)
        → navigation / dashboard / route guards
          (all state comes from the backend `state` field)

Frontend mirror (registry.js, SOURCE="fallback")
  → loading skeleton / offline presentation / drift comparison / tests ONLY
  → NEVER grants access, marks unavailable modules active, or overrides flags
```

## Authoritative fields (backend only)

installed · enabled · status · **state** · health · routes · navigation
contributions · dashboard cards · widgets · search-provider metadata · workspace
views · permission namespaces · capabilities · feature flags.

## Truthful module states (`ModuleState`)

| State | Meaning |
|-------|---------|
| `available` | enabled, implemented, healthy, caller permitted → actionable |
| `degraded` | enabled but health degraded → not actionable |
| `unavailable` | enabled but a dependency is unavailable |
| `disabled` | installed but turned off |
| `not_implemented` | placeholder / metadata-only |
| `permission_restricted` | caller lacks read permission, or is an agent actor |

`actionable` and `primary_route` are exposed **only** when state is `available`.

## Permission filtering (fail closed)

`ModuleDescriptor.resolve_state(can_read, is_agent)`:

1. placeholder → `not_implemented`
2. disabled → `disabled`
3. `is_agent` → `permission_restricted` (agents never get human shell operational access)
4. module declares read permissions and caller has none → `permission_restricted`
5. else map health → `available` / `degraded` / `unavailable`

`READ_PERMISSION_BY_NAMESPACE` maps `paper_account → paper_account.read`, etc. The
API builds `can_read = role_has_permission(ctx.role, perm)` and `is_agent =
is_agent_actor(ctx)`. **This is rendering guidance only** — backend routes and the
ExecutionGateway still enforce their own permissions. A `permission_restricted`
module is returned (shown locked), not silently dropped; its real routes stay
protected. Hidden navigation is never treated as authorization.

## Enablement scope (truthful)

Module enablement is **global** in this build — there is no per-tenant enablement
model, and M64 does not invent one. Per-caller variation is by **permission** and
**agent actor**, not by tenant-specific enablement. Cross-tenant safety is enforced
by the platform identity/context layer on every request; the module payload itself
carries no tenant-scoped enablement.

## Registration grants nothing

Declaring a permission namespace in a `ModuleDescriptor` is a directory entry, not
a grant. `test_registration_grants_no_permission` proves a caller with no reads is
`permission_restricted` even though Trading declares `paper_*` namespaces, and that
role permission sets are unchanged by registration.

## Drift

`drift.js` compares backend discovery against the mirror. Capability, permission,
enablement, and implemented-state mismatches are **critical** (tests fail closed);
version/route mismatches are informational. Drift is a diagnostic, never a security
control — the backend remains authoritative regardless.

## Safe serialization

`to_public()` / `discovery()` emit an allowlisted key set only. No `health_fn`,
class names, file paths, `db_path`, or sqlite references appear
(`test_no_internal_paths_in_response`, `test_module_public_keys_are_allowlisted`).

## Safe icons

Backend icon strings are DATA. `icons.js` resolves them through a fixed allowlist
to a static glyph; unknown/hostile values (`<script>…`, `__proto__`, non-strings)
fall back to a neutral glyph. No dynamic import, component lookup, or code
execution is ever driven by a backend-supplied value.
