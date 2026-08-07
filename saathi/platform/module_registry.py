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
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"
    NOT_IMPLEMENTED = "not_implemented"
    DISABLED = "disabled"


class ModuleState(str, Enum):
    """Truthful, per-caller module state combining status + health + access. This is
    what the shell renders. It is presentation only — backend routes and RBAC remain
    authoritative regardless of what state a caller is shown."""
    AVAILABLE = "available"                        # enabled, implemented, healthy, permitted
    DEGRADED = "degraded"                          # enabled but health degraded
    UNAVAILABLE = "unavailable"                    # enabled but a dependency is unavailable
    DISABLED = "disabled"                          # installed but turned off
    NOT_IMPLEMENTED = "not_implemented"            # placeholder / metadata-only
    PERMISSION_RESTRICTED = "permission_restricted"  # caller lacks read permission (or agent actor)


# Read-permission required to *see* a module's operational surface, by namespace.
# Placeholders declare a bare namespace (their own id) with no ".read" permission;
# they are never operational, so they are not gated on a read permission here.
READ_PERMISSION_BY_NAMESPACE = {
    "paper_account": "paper_account.read",
    "paper_order": "paper_order.read",
    "reconciliation": "reconciliation.read",
    "paper_safety": "paper_safety.read",
    "ielts": "ielts.read",
}


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

    def candidate_read_permissions(self) -> list[str]:
        """The read permissions that grant visibility of this module's operational
        surface. Empty for placeholders (no operational surface to gate)."""
        out = []
        for ns in self.permissions:
            perm = READ_PERMISSION_BY_NAMESPACE.get(ns)
            if perm:
                out.append(perm)
        return out

    def resolve_state(self, *, can_read=None, is_agent: bool = False) -> ModuleState:
        """Compute the truthful state for a caller. `can_read(perm_str) -> bool` is a
        non-raising permission predicate; `is_agent` marks autonomous/agent actors,
        which never receive human operational shell access. Fail-closed: any actor
        without an explicit read grant to an operational module is PERMISSION_RESTRICTED."""
        if self.status == ModuleStatus.PLACEHOLDER:
            return ModuleState.NOT_IMPLEMENTED
        if self.status == ModuleStatus.DISABLED:
            return ModuleState.DISABLED
        # enabled + implemented → gate on read permission
        reads = self.candidate_read_permissions()
        if is_agent:
            return ModuleState.PERMISSION_RESTRICTED
        if reads and can_read is not None and not any(can_read(p) for p in reads):
            return ModuleState.PERMISSION_RESTRICTED
        h = self.health()
        if h == ModuleHealth.HEALTHY:
            return ModuleState.AVAILABLE
        if h == ModuleHealth.DEGRADED:
            return ModuleState.DEGRADED
        if h == ModuleHealth.UNAVAILABLE:
            return ModuleState.UNAVAILABLE
        return ModuleState.AVAILABLE if self.is_enabled else ModuleState.UNAVAILABLE

    def to_public(self, *, can_read=None, is_agent: bool = False) -> dict:
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
            "enabled": self.is_enabled,
            "implemented": self.status != ModuleStatus.PLACEHOLDER,
            "state": self.resolve_state(can_read=can_read, is_agent=is_agent).value,
            "operational": self.resolve_state(can_read=can_read, is_agent=is_agent) == ModuleState.AVAILABLE,
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

    # ── caller-aware, permission-filtered discovery (M64 authoritative payload) ──
    CONTRACT_VERSION = "m64.1"

    def discovery(self, *, can_read=None, is_agent: bool = False) -> dict:
        """The authoritative browser module-discovery payload. Every module carries a
        truthful, caller-scoped `state`; navigation and dashboard cards carry the same.
        Permission filtering is advisory for RENDERING only — backend routes and RBAC
        stay authoritative, so a PERMISSION_RESTRICTED module is still returned (shown
        locked) rather than silently dropped, and its real routes remain protected."""
        installed = []
        for m in self.list_installed():
            pub = m.to_public(can_read=can_read, is_agent=is_agent)
            installed.append(pub)
        nav_modules = []
        for m in self.list_installed():
            state = m.resolve_state(can_read=can_read, is_agent=is_agent)
            nav_modules.append({
                "id": m.id,
                "label": m.name,
                "icon": m.icon,
                "category": m.category.value,
                "state": state.value,
                "enabled": m.is_enabled,
                "implemented": m.status != ModuleStatus.PLACEHOLDER,
                "actionable": state == ModuleState.AVAILABLE,
                "items": [n.to_public() for n in m.nav_items],
            })
        cards = []
        for m in self.list_installed():
            state = m.resolve_state(can_read=can_read, is_agent=is_agent)
            cards.append({
                "module_id": m.id,
                "title": m.name,
                "icon": m.icon,
                "category": m.category.value,
                "description": m.description,
                "version": m.version,
                "state": state.value,
                "health": m.health().value,
                "enabled": m.is_enabled,
                "implemented": m.status != ModuleStatus.PLACEHOLDER,
                "actionable": state == ModuleState.AVAILABLE,
                "capabilities": list(m.capabilities),
                # only an actionable (available) module exposes a live primary route
                "primary_route": (m.routes[0] if (m.routes and state == ModuleState.AVAILABLE) else ""),
                "widgets": [w.to_public() for w in m.dashboard_widgets],
            })
        return {
            "contract_version": self.CONTRACT_VERSION,
            "installed": installed,
            "enabled_count": len(self.list_enabled()),
            "navigation": {"group": "applications", "label": "Applications", "modules": nav_modules},
            "dashboard_cards": cards,
            "search_providers": self.search_providers(),
            "workspace_views": self.workspace_views(),
            "health": self.health_report(),
        }

    def to_public(self) -> dict:
        return {
            "contract_version": self.CONTRACT_VERSION,
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


def _ielts_module() -> ModuleDescriptor:
    """IELTSAlert — bounded local preparation and manual-review application."""
    routes = (
        "/ielts", "/ielts/onboarding", "/ielts/dashboard", "/ielts/goals",
        "/ielts/practice", "/ielts/practice/reading", "/ielts/practice/listening",
        "/ielts/practice/writing", "/ielts/practice/speaking",
        "/ielts/submissions", "/ielts/alerts", "/ielts/payments",
        "/ielts/evidence", "/ielts/settings",
    )
    return ModuleDescriptor(
        id="ielts", name="IELTSAlert", version="1.0.0-local",
        description="Bounded IELTS preparation with transparent local practice feedback, "
                    "fixture availability alerts, and manual payment verification.",
        icon="✦", category=ModuleCategory.EDUCATION, status=ModuleStatus.ENABLED,
        permissions=("ielts",), routes=routes,
        nav_items=(
            NavItemSpec("ielts-home", "Dashboard", "/ielts", "✦", "Preparation summary"),
            NavItemSpec("ielts-goals", "Exam goals", "/ielts/goals", "◎", "Target and date"),
            NavItemSpec("ielts-practice", "Practice", "/ielts/practice", "▤", "Four skills"),
            NavItemSpec("ielts-alerts", "Availability alerts", "/ielts/alerts", "◉", "Fixture-labelled alerts"),
            NavItemSpec("ielts-payments", "Manual payments", "/ielts/payments", "◇", "Human verification"),
            NavItemSpec("ielts-evidence", "Evidence", "/ielts/evidence", "▧", "Activity timeline"),
        ),
        dashboard_widgets=(
            DashboardWidgetSpec("ielts-goal", "Exam Goal", "metric", "/ielts/goals"),
            DashboardWidgetSpec("ielts-next-practice", "Next Practice", "action", "/ielts/practice"),
            DashboardWidgetSpec("ielts-active-alerts", "Active Alerts", "alert", "/ielts/alerts"),
            DashboardWidgetSpec("ielts-progress", "Progress Summary", "metric", "/ielts"),
        ),
        search_provider=SearchProviderSpec(
            "ielts", ("profile", "goal", "practice", "submission", "feedback", "alert", "payment")),
        workspace_views=(
            WorkspaceViewSpec("ielts-learner", "IELTS Learner", "application", "/ielts"),
            WorkspaceViewSpec("ielts-reviewer", "IELTS Reviewer", "application", "/ielts/payments"),
            WorkspaceViewSpec("ielts-evidence", "IELTS Evidence", "evidence", "/ielts/evidence"),
        ),
        capabilities=(
            "local_practice", "reading_listening_records", "writing_submission",
            "speaking_submission", "deterministic_local_feedback",
            "fixture_availability_alerts", "manual_payment_submission",
            "manual_payment_review", "in_app_notifications", "evidence_timeline",
        ),
        feature_flags={
            "provider_assisted_scoring": False, "official_scoring": False,
            "live_availability": False, "external_notifications": False,
            "payment_settlement": False, "manual_payment_verification": True,
            "local_scoring_fallback": True,
        },
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
    """Construct the platform's default registry: Trading and IELTSAlert enabled,
    with remaining future applications retained as metadata-only placeholders."""
    reg = ModuleRegistry()
    reg.register(_trading_module())
    reg.register(_ielts_module())
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
