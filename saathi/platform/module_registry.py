"""M63 — Platform Module Registry.

The single source of truth for platform applications ("modules"). SaathiOS is a
multi-application operating platform: the *platform core* (Runtime, Identity,
Approval Center, Evidence, Notifications, RBAC) is centralized, and applications
extend the platform through a declarative contract rather than hard-coding
themselves into the shell.

This module is metadata + composition ONLY. It:

- defines the canonical ModuleDescriptor contract every application declares,
- provides a ModuleRegistry that composes navigation, dashboard cards, widgets,
  search providers, workspace views, permission namespaces, and health, and
- registers Trading as the first fully integrated module plus metadata-only
  placeholders for future applications.

It NEVER owns evidence, notifications, RBAC, or business logic — those remain
centralized platform services. Registering a module does not grant capability;
the platform's existing permission and gateway checks remain authoritative.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional


# ── enums ─────────────────────────────────────────────────────────────────────
class ModuleCategory(str, Enum):
    TRADING = "trading"
    EDUCATION = "education"
    RETAIL = "retail"
    TRAVEL = "travel"
    FINANCE = "finance"
    PLATFORM = "platform"


class ModuleStatus(str, Enum):
    """Lifecycle of a module within the platform."""
    ENABLED = "enabled"            # installed and active
    DISABLED = "disabled"          # installed but turned off
    PLACEHOLDER = "placeholder"    # metadata-only registration, no implementation


class ModuleHealth(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNKNOWN = "unknown"
    NOT_IMPLEMENTED = "not_implemented"


# ── contract sub-specs ────────────────────────────────────────────────────────
@dataclass(frozen=True)
class NavItemSpec:
    id: str
    label: str
    href: str
    icon: str = "▦"
    description: str = ""

    def to_public(self) -> dict:
        return {"id": self.id, "label": self.label, "href": self.href,
                "icon": self.icon, "description": self.description}


@dataclass(frozen=True)
class DashboardWidgetSpec:
    id: str
    title: str
    kind: str                      # e.g. "metric", "list", "alert"
    href: str = ""
    description: str = ""

    def to_public(self) -> dict:
        return {"id": self.id, "title": self.title, "kind": self.kind,
                "href": self.href, "description": self.description}


@dataclass(frozen=True)
class SearchProviderSpec:
    """Declares the searchable object types a module contributes. M63 builds the
    interface only — no global index is built here."""
    provider_id: str
    object_types: tuple[str, ...] = ()

    def to_public(self) -> dict:
        return {"provider_id": self.provider_id, "object_types": list(self.object_types)}


@dataclass(frozen=True)
class WorkspaceViewSpec:
    id: str
    label: str
    scope: str                     # "application" | "project" | "mission" | "evidence"
    href: str = ""

    def to_public(self) -> dict:
        return {"id": self.id, "label": self.label, "scope": self.scope, "href": self.href}


# ── module descriptor ─────────────────────────────────────────────────────────
@dataclass
class ModuleDescriptor:
    """The declarative contract every platform application exposes."""
    id: str
    name: str
    version: str
    description: str
    icon: str
    category: ModuleCategory
    status: ModuleStatus = ModuleStatus.PLACEHOLDER
    permissions: tuple[str, ...] = ()          # permission NAMESPACES the module registers
    routes: tuple[str, ...] = ()               # frontend routes the module owns
    nav_items: tuple[NavItemSpec, ...] = ()
    dashboard_widgets: tuple[DashboardWidgetSpec, ...] = ()
    search_provider: Optional[SearchProviderSpec] = None
    workspace_views: tuple[WorkspaceViewSpec, ...] = ()
    capabilities: tuple[str, ...] = ()
    feature_flags: dict = field(default_factory=dict)
    # health() returns a ModuleHealth; defaults to NOT_IMPLEMENTED for placeholders.
    health_fn: Optional[Callable[[], ModuleHealth]] = None

    def health(self) -> ModuleHealth:
        if self.health_fn is not None:
            try:
                return self.health_fn()
            except Exception:
                return ModuleHealth.DEGRADED
        return (ModuleHealth.NOT_IMPLEMENTED
                if self.status == ModuleStatus.PLACEHOLDER else ModuleHealth.UNKNOWN)

    @property
    def is_enabled(self) -> bool:
        return self.status == ModuleStatus.ENABLED

    def to_public(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "icon": self.icon,
            "category": self.category.value,
            "status": self.status.value,
            "permissions": list(self.permissions),
            "routes": list(self.routes),
            "nav_items": [n.to_public() for n in self.nav_items],
            "dashboard_widgets": [w.to_public() for w in self.dashboard_widgets],
            "search_provider": self.search_provider.to_public() if self.search_provider else None,
            "workspace_views": [v.to_public() for v in self.workspace_views],
            "capabilities": list(self.capabilities),
            "feature_flags": dict(self.feature_flags),
            "health": self.health().value,
        }


# ── registry ──────────────────────────────────────────────────────────────────
class ModuleRegistryError(Exception):
    pass


class ModuleRegistry:
    """Single source of truth for installed platform modules. Composes the shell's
    data-driven navigation, dashboard, search, and workspace surfaces. Applications
    register through this registry; the shell never hard-codes an application."""

    def __init__(self) -> None:
        self._modules: dict[str, ModuleDescriptor] = {}

    def register(self, module: ModuleDescriptor) -> ModuleDescriptor:
        if module.id in self._modules:
            raise ModuleRegistryError(f"module already registered: {module.id}")
        if not module.id or not module.name or not module.version:
            raise ModuleRegistryError("module requires id, name, version")
        self._modules[module.id] = module
        return module

    def get(self, module_id: str) -> Optional[ModuleDescriptor]:
        return self._modules.get(module_id)

    def list_installed(self) -> list[ModuleDescriptor]:
        return sorted(self._modules.values(), key=lambda m: (m.category.value, m.name))

    def list_enabled(self) -> list[ModuleDescriptor]:
        return [m for m in self.list_installed() if m.is_enabled]

    def enable(self, module_id: str) -> None:
        m = self._require(module_id)
        m.status = ModuleStatus.ENABLED

    def disable(self, module_id: str) -> None:
        m = self._require(module_id)
        m.status = ModuleStatus.DISABLED

    def _require(self, module_id: str) -> ModuleDescriptor:
        m = self._modules.get(module_id)
        if not m:
            raise ModuleRegistryError(f"unknown module: {module_id}")
        return m

    # ── composed platform surfaces (data-driven) ─────────────────────────────
    def navigation(self) -> dict:
        """The Applications navigation group, derived from module registrations.
        Platform/Administration groups remain owned by the platform shell."""
        apps = []
        for m in self.list_installed():
            apps.append({
                "id": m.id,
                "label": m.name,
                "icon": m.icon,
                "status": m.status.value,
                "category": m.category.value,
                "items": [n.to_public() for n in m.nav_items],
            })
        return {"group": "applications", "label": "Applications", "modules": apps}

    def dashboard_cards(self) -> list[dict]:
        """One card per installed module for the unified dashboard."""
        cards = []
        for m in self.list_installed():
            cards.append({
                "module_id": m.id,
                "title": m.name,
                "icon": m.icon,
                "category": m.category.value,
                "status": m.status.value,
                "health": m.health().value,
                "description": m.description,
                "widgets": [w.to_public() for w in m.dashboard_widgets],
                "primary_route": (m.routes[0] if m.routes else ""),
            })
        return cards

    def widgets(self) -> list[dict]:
        out = []
        for m in self.list_installed():
            for w in m.dashboard_widgets:
                out.append({"module_id": m.id, **w.to_public()})
        return out

    def search_providers(self) -> list[dict]:
        out = []
        for m in self.list_installed():
            if m.search_provider:
                out.append({"module_id": m.id, **m.search_provider.to_public()})
        return out

    def workspace_views(self) -> list[dict]:
        out = []
        for m in self.list_installed():
            for v in m.workspace_views:
                out.append({"module_id": m.id, **v.to_public()})
        return out

    def permission_namespaces(self) -> list[dict]:
        """Applications register permission NAMESPACES; the platform RBAC remains
        authoritative. This is a directory, not a grant."""
        return [{"module_id": m.id, "namespaces": list(m.permissions)}
                for m in self.list_installed() if m.permissions]

    def health_report(self) -> list[dict]:
        return [{"module_id": m.id, "status": m.status.value, "health": m.health().value}
                for m in self.list_installed()]

    def to_public(self) -> dict:
        return {
            "installed": [m.to_public() for m in self.list_installed()],
            "enabled_count": len(self.list_enabled()),
            "navigation": self.navigation(),
            "dashboard_cards": self.dashboard_cards(),
            "search_providers": self.search_providers(),
            "workspace_views": self.workspace_views(),
            "health": self.health_report(),
        }


# ── canonical module descriptors ──────────────────────────────────────────────
def _trading_module() -> ModuleDescriptor:
    """Trading — the first fully integrated platform module (reference impl).
    Its business logic lives in saathi/platform/paper_trading + safety; this
    descriptor only declares its platform integration surface."""
    return ModuleDescriptor(
        id="trading",
        name="Trading",
        version="62.9",
        description="Bounded paper-trading platform: research → strategy → paper orders "
                    "→ reconciliation → safety. Simulation-only, long-only, localhost.",
        icon="◈",
        category=ModuleCategory.TRADING,
        status=ModuleStatus.ENABLED,
        permissions=("paper_account", "paper_order", "reconciliation", "paper_safety"),
        routes=("/trading", "/trading/accounts", "/trading/orders", "/trading/positions",
                "/trading/strategies", "/trading/reconciliation", "/trading/safety",
                "/trading/approvals", "/trading/evidence"),
        nav_items=(
            NavItemSpec("trading-home", "Overview", "/trading", "◈", "Trading overview"),
            NavItemSpec("trading-accounts", "Accounts", "/trading/accounts", "▤", "Paper accounts"),
            NavItemSpec("trading-orders", "Orders", "/trading/orders", "▦", "Order lifecycle"),
            NavItemSpec("trading-safety", "Safety", "/trading/safety", "⛊", "Circuit breakers"),
            NavItemSpec("trading-recon", "Reconciliation", "/trading/reconciliation", "⚖", "Integrity"),
        ),
        dashboard_widgets=(
            DashboardWidgetSpec("trading-active-accounts", "Active Accounts", "metric",
                                "/trading/accounts", "Active paper accounts"),
            DashboardWidgetSpec("trading-open-orders", "Open Orders", "metric",
                                "/trading/orders", "Orders in flight"),
            DashboardWidgetSpec("trading-safety-alerts", "Safety Alerts", "alert",
                                "/trading/safety", "Active breaker trips + alerts"),
        ),
        search_provider=SearchProviderSpec(
            "trading", ("order", "account", "strategy", "reconciliation")),
        workspace_views=(
            WorkspaceViewSpec("trading-app", "Trading", "application", "/trading"),
            WorkspaceViewSpec("trading-evidence", "Trading Evidence", "evidence", "/trading/evidence"),
        ),
        capabilities=("paper_trading", "reconciliation", "circuit_breakers",
                      "deterministic_backtest", "fixture_replay_market_data"),
        feature_flags={"live_trading": False, "real_money": False, "external_broker": False},
        health_fn=lambda: ModuleHealth.HEALTHY,
    )


def _placeholder(id_, name, icon, category, description, routes, widgets, search_types) -> ModuleDescriptor:
    """Metadata-only registration for a future application. Exposes contract
    surface but no business logic. status=PLACEHOLDER, health=NOT_IMPLEMENTED."""
    return ModuleDescriptor(
        id=id_, name=name, version="0.0.0", description=description, icon=icon,
        category=category, status=ModuleStatus.PLACEHOLDER,
        permissions=(id_,),
        routes=tuple(routes),
        nav_items=(NavItemSpec(f"{id_}-home", name, routes[0] if routes else f"/{id_}", icon,
                               f"{name} (coming soon)"),),
        dashboard_widgets=tuple(
            DashboardWidgetSpec(f"{id_}-{w.lower().replace(' ', '-')}", w, "metric", "",
                                f"{name} {w}") for w in widgets),
        search_provider=SearchProviderSpec(id_, tuple(search_types)),
        workspace_views=(WorkspaceViewSpec(f"{id_}-app", name, "application",
                                           routes[0] if routes else f"/{id_}"),),
        capabilities=(),
        feature_flags={"implemented": False},
    )


def build_default_registry() -> ModuleRegistry:
    """Construct the platform's default module registry: Trading (enabled) plus
    metadata-only placeholders for future applications."""
    reg = ModuleRegistry()
    reg.register(_trading_module())
    reg.register(_placeholder(
        "ielts", "IELTSAlert", "✦", ModuleCategory.EDUCATION,
        "IELTS exam alerting and preparation.",
        ["/ielts"], ["Upcoming Exams", "Alerts", "Students"], ["test", "student", "alert"]))
    reg.register(_placeholder(
        "hcgpos", "HCG POS", "▣", ModuleCategory.RETAIL,
        "Canteen point-of-sale and kitchen operations.",
        ["/pos"], ["Sales", "Kitchen", "Orders"], ["order", "inventory", "customer"]))
    reg.register(_placeholder(
        "travel", "Travel", "✈", ModuleCategory.TRAVEL,
        "Trip, itinerary, and booking management.",
        ["/travel"], ["Trips", "Bookings"], ["booking", "itinerary", "client"]))
    reg.register(_placeholder(
        "finance", "Finance", "$", ModuleCategory.FINANCE,
        "Personal and business finance tracking.",
        ["/finance"], ["Cashflow", "Budgets"], ["account", "transaction", "budget"]))
    return reg


# process-wide default registry (startup registration)
_DEFAULT_REGISTRY: Optional[ModuleRegistry] = None


def get_registry() -> ModuleRegistry:
    global _DEFAULT_REGISTRY
    if _DEFAULT_REGISTRY is None:
        _DEFAULT_REGISTRY = build_default_registry()
    return _DEFAULT_REGISTRY
