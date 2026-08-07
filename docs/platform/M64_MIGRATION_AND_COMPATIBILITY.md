# M64 — Migration & Compatibility

## Audit classification

| Surface | Classification | Disposition |
|---------|---------------|-------------|
| `saathi/platform/module_registry.py` | EXTEND | added caller-aware `discovery()`, `resolve_state()`, `ModuleState`, permission map |
| `saathi/platform/api.py` module endpoints | EXTEND | now permission-filtered discovery; fixed latent missing `PlatformPermission` import |
| `saathi-os/lib/modules/registry.js` | MIGRATE → LEGACY_COMPATIBILITY | marked `SOURCE="fallback"`; no longer operational authority |
| `saathi-os/app/apps/page.jsx` | MIGRATE | now backend-authoritative via `useModuleDiscovery` |
| Production Sidebar / CommandPalette / route boundary | MIGRATE | shared shell discovery; backend Applications entries and route state |
| `saathi-os/lib/navigation.js` (NAV_GROUPS) | REUSE | platform groups unchanged (locked by test) |
| `saathi-os/lib/platform-client.js` (`plat`) | REUSE | canonical authenticated transport |
| `saathi/config.py` HOST default | EXTEND (hardening) | default → `127.0.0.1`; deploy sets `SAATHI_HOST` explicitly |
| Legacy landing pages (`/os`, `/platform`, `/business`, per-dept) | KEEP | working; superseded as app-launcher by `/apps`, not removed |
| Trading pages (`/trading/*`) | REUSE | unchanged; business logic untouched |

## Canonical entry point

`/apps` is the one canonical, backend-driven applications dashboard. The M63
mirror-driven `/apps` is replaced in place (same route). No competing active module
registry: the frontend mirror is now explicitly a fallback skeleton.

## Legacy pages retained

`/os`, `/platform`, `/business`, department landing pages, and the CEO/attention
home remain functional. They predate the module shell and are kept for compatibility.
Module-owned placeholder paths are the exception: the production route boundary
withholds their legacy content until the backend marks the module available. In M64,
direct `/finance` therefore renders a truthful not-implemented state. The
authoritative applications view is `/apps`.

## Localhost hardening

`config.py` HOST default changed `0.0.0.0 → 127.0.0.1`. Safe because:

- `Dockerfile` sets `ENV SAATHI_HOST=0.0.0.0` (container deploy unaffected);
- `scripts/start_local.sh` sets `SAATHI_HOST=127.0.0.1` (launcher unaffected);
- a bare `python -m saathi.server` now fails safe to loopback instead of exposing
  the LAN.

Locked by `tests/test_m64_localhost_binding.py` (default loopback; explicit env
override still honored). No deployment assumption depended on the code default.

## Redirects / auth

No redirect bypasses auth. `/apps` gates on token via `useModuleDiscovery`
(`AUTH_REQUIRED` → link to `/unlock`). Backend endpoints require `PLATFORM_READ`.
