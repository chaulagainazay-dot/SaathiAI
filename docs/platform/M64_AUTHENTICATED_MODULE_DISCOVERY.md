# M64 — Authenticated Module Discovery

## API surface (read-only, reused M63 routes — no duplicate namespace)

| Endpoint | Auth | Returns |
|----------|------|---------|
| `GET /api/v1/platform/modules` | `PLATFORM_READ` | permission-filtered discovery: `{contract_version, installed[], navigation, dashboard_cards, ...}` |
| `GET /api/v1/platform/modules/{id}` | `PLATFORM_READ` | one module, caller-scoped `state` |
| `GET /api/v1/platform/modules/{id}/health` | `PLATFORM_READ` | `{status, health, state}` |
| `GET /api/v1/platform/dashboard` | `PLATFORM_READ` | `{contract_version, cards[], health[]}` |
| `GET /api/v1/platform/navigation` | `PLATFORM_READ` | Applications nav group (caller-scoped) |

Each response is authenticated, permission-filtered, bounded, deterministic,
contract-versioned (`m64.1`), and free of secrets / internal paths.

## Frontend client (`saathi-os/lib/modules/client.js`)

One canonical client layered on the existing authenticated `plat()` (X-Platform-Token):

- `fetchModuleDiscovery({token, platFn, signal})` — single bounded request; the
  default transport is lazy-loaded so pure units/tests never pull the browser chain.
- `normalizeModule(raw)` — validates required fields (`id,name,version,state`);
  **rejects malformed descriptors** (fail closed, dropped from the render set).
- `classifyError(e)` — 401→`session_expired`, 403→`permission_restricted`,
  404→`not_found`, 409→`conflict`, 5xx→`server_error`, network→`network`.
- `isActionable(mod)` — true only when backend `state === "available"`. Actionability
  is never inferred client-side.

## Shell bootstrap state machine (`bootstrap.js`)

Pure reducer over states `INITIALIZING · AUTH_REQUIRED · LOADING_CONTEXT ·
LOADING_MODULES · READY · DEGRADED · OFFLINE · PERMISSION_RESTRICTED ·
SESSION_EXPIRED · ERROR`. Guarantees:

- never shows stale modules as operational while the authoritative request is unresolved;
- any discovery failure **clears** the module set (no stale render);
- `LOGOUT` clears module state; `CONTEXT_SWITCH` (tenant/workspace change)
  invalidates all prior module state before reload → **no cross-tenant flash**.

## Discovery hook (`useModuleDiscovery.js`)

Drives the machine from the endpoint: no token → `AUTH_REQUIRED`; success →
`READY`/`DEGRADED`; classified failure → the matching phase; bounded retry (≤3) on
network only. Generation checks, abort-signal propagation through `plat()`, cleared
retry timers, and request cancellation prevent an old request completing after
unmount, logout, or context change.

## Shell-wide owner (`ModuleDiscoveryContext.jsx`)

One provider owns discovery for the production Sidebar, CommandPalette, route
boundary, and `/apps`; these surfaces do not issue competing requests or hold
independent authority state. `setToken()` emits a same-tab platform-context event,
and `notifyPlatformContextChanged()` provides the corresponding org/workspace
invalidation hook. Cross-tab token changes are handled through the storage event.

## Caching policy

**No cache** in M64. Every shell mount performs one authenticated discovery request;
context switch and logout invalidate in-memory state. This keeps the design simple
and fails safe (no stale cross-tenant data, no cache-as-authorization). Performance
is acceptable (single bounded request; localhost p50 well under 100 ms).

## Evidence

`m64_evidence/DISCOVERY_SAMPLE.json` — real FastAPI app: unauthenticated `/modules`
= 401, authenticated = 200, unknown module = 404, `contract_version = m64.1`,
5 modules (trading available; ielts/hcgpos/travel/finance not_implemented).

`m64_evidence/M64_BROWSER_CERT.json` — production shell certification: authenticated
request, context/logout invalidation, classified failures, bounded retry, and
malformed-response fail-closed behavior.
