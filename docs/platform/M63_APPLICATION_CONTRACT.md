# M63 — Application Contract

Every SaathiOS application ("module") declares a `ModuleDescriptor` and registers it with the
`ModuleRegistry`. The shell composes its surfaces from these declarations. Applications never
manipulate shell internals directly and never own platform services.

## Descriptor fields

| Field | Type | Meaning |
|-------|------|---------|
| `id` | string | stable unique module id |
| `name` | string | display name |
| `version` | string | module version |
| `description` | string | one-line summary |
| `icon` | string | glyph shown in nav/cards |
| `category` | enum | trading / education / retail / travel / finance / platform |
| `status` | enum | enabled / disabled / placeholder |
| `permissions` | string[] | permission **namespaces** the module uses (directory, not a grant) |
| `routes` | string[] | frontend routes the module owns |
| `nav_items` | NavItem[] | Applications-group navigation entries |
| `dashboard_widgets` | Widget[] | cards/metrics contributed to the dashboard |
| `search_provider` | {provider_id, object_types[]} \| null | searchable object types (interface only) |
| `workspace_views` | WorkspaceView[] | views for application/project/mission/evidence scopes |
| `capabilities` | string[] | declared capabilities |
| `feature_flags` | object | flags (e.g. `live_trading:false`) |
| `health()` | fn → enum | healthy / degraded / unknown / not_implemented |

## Contract methods (registry-composed)

Rather than each module implementing shell hooks, the registry derives the shell surfaces:

| Platform need | Registry method | Backend | Frontend |
|---------------|-----------------|---------|----------|
| register() | `register(descriptor)` | ✓ | ✓ |
| health() | `descriptor.health()` | ✓ | ✓ |
| routes() | `descriptor.routes` | ✓ | ✓ |
| permissions() | `permission_namespaces()` | ✓ | ✓ |
| dashboardCards() | `dashboard_cards()` | ✓ | ✓ |
| searchProvider() | `search_providers()` | ✓ | ✓ |
| workspaceViews() | `workspace_views()` | ✓ | ✓ |
| capabilities() | `descriptor.capabilities` | ✓ | ✓ |
| navigation() | `navigation()` | ✓ | ✓ |

## Rules

1. A module **declares**; the shell **composes**. No app hard-codes itself into the shell.
2. Registration grants no capability — RBAC and the ExecutionGateway remain authoritative.
3. Applications publish evidence/notifications and register permission namespaces; they never own
   evidence storage, notification transport, or RBAC.
4. Placeholders expose metadata only (`status=placeholder`, `health=not_implemented`).

## Reference implementation

`_trading_module()` in `saathi/platform/module_registry.py` and `TRADING_MODULE` in
`saathi-os/lib/modules/registry.js`. Trading is the canonical example of a fully integrated module.

## Adding a new application

1. Author a `ModuleDescriptor` (backend) and mirror it (frontend).
2. Register it in `build_default_registry()` / `buildDefaultRegistry()`.
3. It appears automatically in Applications nav, the `/apps` dashboard, search, and workspace
   aggregation. No shell edits required.
