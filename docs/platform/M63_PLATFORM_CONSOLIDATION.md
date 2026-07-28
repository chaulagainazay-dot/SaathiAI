# M63 — Platform Consolidation

**Verdict:** `M63_COMPLETE_WITH_LIMITATIONS`
**Branch:** `milestone/m61-backend-workflow-persistence`
**Starting HEAD:** `12afdf7`
**Date:** 2026-07-28

M63 turns SaathiOS from a single-purpose surface into a **multi-application operating
platform**. The platform core (Runtime, Identity, Approval Center, Evidence, Notifications,
RBAC) stays centralized; applications extend the platform through a declarative **module
contract** rather than hard-coding themselves into the shell. **Trading** becomes the first
fully integrated module and the reference implementation.

No trading engine changes beyond the minimal integration surface. No live trading, real money,
external brokers, production deployment, or autonomous execution introduced. No push/merge/deploy.

---

## 1. Platform audit

| Concept | Classification | Notes |
|---------|---------------|-------|
| PlatformAgentRuntime, ExecutionGateway | REUSE | canonical runtime + sole mutation authority; unchanged |
| Approval Center, Evidence, Notifications, RBAC (`models.py` roles/permissions) | REUSE | centralized platform services; applications register namespaces only |
| `saathi-os/lib/navigation.js` (NAV_GROUPS) | REUSE + EXTEND | 4 platform groups kept intact (locked by test); Applications + Administration composed on top |
| Trading (`paper_trading/`, `safety/`, `market_data/`, `strategy/`, `research/`) | REUSE | wrapped as Module #1; business logic untouched |
| Per-app landing pages | EXTEND | new module-driven `/apps` dashboard added; old pages left working |
| Hard-coded app links in shell | DEPRECATE (soft) | superseded by registry-derived Applications nav; not removed |
| Existing working implementations | KEEP | nothing deleted |

## 2. Module framework

`saathi/platform/module_registry.py` (backend) and `saathi-os/lib/modules/registry.js` (frontend)
define the canonical `ModuleDescriptor` contract:

`id · name · version · description · icon · category · status · permissions · routes ·
nav_items · dashboard_widgets · search_provider · workspace_views · capabilities ·
feature_flags · health()`.

Every application declares this metadata; it never manipulates shell internals directly.

## 3. Module registry

`ModuleRegistry` is the single source of truth. Responsibilities:

- installed / enabled modules (`list_installed`, `list_enabled`, `enable`, `disable`)
- composed **navigation** (Applications group), **dashboard cards**, **widgets**,
  **search providers**, **workspace views**, **permission namespaces**, **health report**
- startup registration via `build_default_registry()` / `get_registry()` (stable singleton)

Registration grants **no capability** — the platform RBAC and gateway remain authoritative
(`test_module_registration_does_not_grant_permission`).

## 4. Unified dashboard

`/apps` (`saathi-os/app/apps/page.jsx`) renders one card per installed module entirely from the
registry — icon, health chip, description, contributed widgets, primary route. Enabled modules
link through; placeholders render disabled with a "soon" badge. Adding a module registration makes
it appear automatically; nothing is hard-coded in the page.

## 5. Unified navigation

`saathi-os/lib/modules/shell.js::getShellNavigation()` composes:

- **Platform** — existing `NAV_GROUPS` (Operate / Work / Business / System), unchanged
- **Applications** — derived from module registrations (data-driven)
- **Administration** — Settings / Identity / Organizations / Permissions / Health / Diagnostics

## 6. Search abstraction

Interface only (per spec — no global index built). Each module contributes a
`SearchProvider(provider_id, object_types)`. Trading contributes `order, account, strategy,
reconciliation`; placeholders declare their intended object types.

## 7. Widget framework

Modules contribute `DashboardWidget(id, title, kind, href)`. `registry.widgets()` aggregates them
dynamically. Trading: Active Accounts, Open Orders, Safety Alerts.

## 8. Workspace framework

`WorkspaceView(id, label, scope, href)` with scopes `application / project / mission / evidence`.
Trading contributes an application view and an evidence view.

## 9. Notifications / Evidence / Permissions

Unchanged and centralized. Modules **publish** events / evidence and **register** permission
namespaces; they never own the storage or the RBAC. The registry exposes a permission-namespace
**directory**, explicitly not a grant.

## 10. Applications

- **Trading** — Module #1, `status=enabled`, `health=healthy`, real routes + widgets + search +
  workspace views. `feature_flags`: `live_trading=false, real_money=false, external_broker=false`.
- **IELTSAlert, HCG POS, Travel, Finance** — metadata-only placeholders, `status=placeholder`,
  `health=not_implemented`, `feature_flags.implemented=false`. No business logic.

## 11. Tests

- Backend: `tests/test_m63_module_registry.py` — 16 tests (registration, dup rejection, enable/
  disable, navigation/dashboard/widget/search/workspace composition, health, Trading-enabled,
  placeholder metadata-only, singleton, no-capability-grant).
- Frontend: `saathi-os/lib/modules/registry.test.js` — 16 tests (mirror + shell composition,
  platform groups unchanged, Applications data-driven, dashboard module-driven).
- Regression: frontend `npm test` 146 pass / 0 fail; lint clean; `next build` succeeds (`/apps`
  route built); backend trading + api suites pass.

## 12. Known limitations

- Search is an interface only; no global index (by design for M63).
- Applications nav/dashboard consumed from the local registry mirror; a live backend
  `/api/v1/platform/modules` endpoint exists but the shell pages read the local registry for
  deterministic render (no auth round-trip needed for static metadata).
- Placeholder apps expose metadata only; routes are declared but not implemented.
- Existing legacy landing pages remain; they are superseded, not removed.
- Single-host, localhost-only; no distributed runtime; no production capability added.

## 13. Scope statement

M63 delivers a unified platform shell capable of hosting multiple bounded applications. Trading is
the first fully integrated module. PlatformAgentRuntime, ExecutionGateway, Approval Center,
Evidence, Notifications, Identity, and RBAC remain centralized. Applications extend the platform
through the module contract rather than duplicating platform capabilities. No live trading,
production deployment, external brokers, or autonomous execution introduced. No push, merge, or
deploy performed.
