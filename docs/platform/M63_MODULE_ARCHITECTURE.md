# M63 — Module Architecture

```
SaathiOS
├── Platform Core (centralized, REUSE — unchanged)
│   ├── PlatformAgentRuntime        canonical agent runtime
│   ├── ExecutionGateway            sole authority for registered mutation tools
│   ├── Identity / RBAC             models.py roles + permissions
│   ├── Approval Center             approvals
│   ├── Evidence                    audit timeline
│   ├── Notifications               event aggregation
│   ├── Workspace / Projects / Missions / Knowledge
│   └── Module Registry  ◄── NEW (M63)   single source of truth for modules
│
├── Shell (data-driven composition — NEW/EXTEND)
│   ├── Navigation   platform groups (navigation.js) + Applications + Administration
│   ├── Dashboard    /apps — one card per module, from the registry
│   ├── Search       provider interfaces contributed by modules
│   └── Widgets/Workspace   aggregated from module descriptors
│
└── Applications (extend platform via the module contract)
    ├── Trading      ◄── Module #1, enabled, reference implementation
    ├── IELTSAlert   placeholder (metadata only)
    ├── HCG POS      placeholder (metadata only)
    ├── Travel       placeholder (metadata only)
    └── Finance      placeholder (metadata only)
```

## Components

### Backend — `saathi/platform/module_registry.py`
- `ModuleCategory`, `ModuleStatus`, `ModuleHealth` enums
- Sub-specs: `NavItemSpec`, `DashboardWidgetSpec`, `SearchProviderSpec`, `WorkspaceViewSpec`
- `ModuleDescriptor` — the contract (+ `to_public()`, `health()`)
- `ModuleRegistry` — register/get/list + composition (`navigation`, `dashboard_cards`,
  `widgets`, `search_providers`, `workspace_views`, `permission_namespaces`, `health_report`)
- `build_default_registry()` + `get_registry()` singleton (startup registration)

### Backend API — `saathi/platform/api.py` (read-only, `PLATFORM_READ`)
- `GET /api/v1/platform/modules` — installed modules + composed surfaces
- `GET /api/v1/platform/modules/{id}`
- `GET /api/v1/platform/modules/{id}/health`
- `GET /api/v1/platform/dashboard` — module-driven dashboard cards
- `GET /api/v1/platform/navigation` — data-driven Applications group

### Frontend — `saathi-os/lib/modules/`
- `registry.js` — mirror of the contract + `TRADING_MODULE`, `PLACEHOLDER_MODULES`,
  `buildDefaultRegistry()`, `getRegistry()`
- `shell.js` — `getShellNavigation()`, `getDashboard()`, `getSearchProviders()`,
  `getWorkspaceViews()`, `ADMIN_GROUP`
- `app/apps/page.jsx` — module-driven Applications dashboard

## Data flow

```
ModuleDescriptor  ──register──►  ModuleRegistry  ──compose──►  Shell surfaces
   (per app)                     (single source)                (nav / dashboard /
                                                                 search / widgets /
                                                                 workspace)
```

Registration is metadata; capability continues to flow only through RBAC + ExecutionGateway.

## Invariants

- Platform `NAV_GROUPS` unchanged (locked by `navigation.test.js`); Applications composed on top.
- Trading is the only enabled module by default; placeholders are metadata-only.
- No business logic duplicated; Trading logic untouched.
- No live/production/broker capability anywhere in the module layer.
