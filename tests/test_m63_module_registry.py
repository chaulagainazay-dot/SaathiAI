"""M63 — platform module registry: registration, composition, health, isolation.

Covers the module contract, dynamic registration, the composed data-driven
navigation/dashboard/search/widget/workspace surfaces, Trading as the first
enabled module, metadata-only placeholders, and that registration grants no
capability (RBAC stays authoritative).
"""
from __future__ import annotations

import pytest

from saathi.platform.context import PlatformExecutionContext
from saathi.platform.models import PlatformPermission
from saathi.platform.module_registry import (
    ModuleRegistry, ModuleDescriptor, ModuleCategory, ModuleStatus, ModuleHealth,
    NavItemSpec, DashboardWidgetSpec, SearchProviderSpec, WorkspaceViewSpec,
    ModuleRegistryError, build_default_registry, get_registry,
)


def _ctx(role="owner", org="o1"):
    return PlatformExecutionContext(user_id="u1", role=role, org_id=org,
                                    workspace_id="w1", run_id="r1")


def _mini(id_="x", status=ModuleStatus.ENABLED):
    return ModuleDescriptor(
        id=id_, name=id_.upper(), version="1.0.0", description="d", icon="●",
        category=ModuleCategory.PLATFORM, status=status,
        permissions=(id_,), routes=(f"/{id_}",),
        nav_items=(NavItemSpec(f"{id_}-home", id_, f"/{id_}"),),
        dashboard_widgets=(DashboardWidgetSpec(f"{id_}-w", "W", "metric"),),
        search_provider=SearchProviderSpec(id_, ("thing",)),
        workspace_views=(WorkspaceViewSpec(f"{id_}-app", id_, "application"),),
    )


# ── registration ──────────────────────────────────────────────────────────────
def test_register_and_get():
    r = ModuleRegistry()
    r.register(_mini("a"))
    assert r.get("a").name == "A"
    assert r.get("missing") is None


def test_duplicate_registration_rejected():
    r = ModuleRegistry()
    r.register(_mini("a"))
    with pytest.raises(ModuleRegistryError):
        r.register(_mini("a"))


def test_missing_fields_rejected():
    r = ModuleRegistry()
    with pytest.raises(ModuleRegistryError):
        r.register(ModuleDescriptor(id="", name="x", version="1", description="", icon="●",
                                    category=ModuleCategory.PLATFORM))


def test_enable_disable_and_lists():
    r = ModuleRegistry()
    r.register(_mini("a", status=ModuleStatus.ENABLED))
    r.register(_mini("b", status=ModuleStatus.PLACEHOLDER))
    assert {m.id for m in r.list_installed()} == {"a", "b"}
    assert {m.id for m in r.list_enabled()} == {"a"}
    r.enable("b")
    assert {m.id for m in r.list_enabled()} == {"a", "b"}
    r.disable("a")
    assert {m.id for m in r.list_enabled()} == {"b"}
    with pytest.raises(ModuleRegistryError):
        r.enable("nope")


# ── composed surfaces ───────────────────────────────────────────────────────────
def test_navigation_is_data_driven():
    r = ModuleRegistry()
    r.register(_mini("a"))
    nav = r.navigation()
    assert nav["group"] == "applications"
    ids = [m["id"] for m in nav["modules"]]
    assert "a" in ids
    mod = next(m for m in nav["modules"] if m["id"] == "a")
    assert mod["items"][0]["href"] == "/a"


def test_dashboard_cards_one_per_module():
    r = ModuleRegistry()
    r.register(_mini("a"))
    r.register(_mini("b"))
    cards = r.dashboard_cards()
    assert {c["module_id"] for c in cards} == {"a", "b"}
    assert all("health" in c and "widgets" in c for c in cards)


def test_widgets_search_workspace_composition():
    r = ModuleRegistry()
    r.register(_mini("a"))
    assert any(w["module_id"] == "a" for w in r.widgets())
    sp = r.search_providers()
    assert sp[0]["object_types"] == ["thing"]
    wv = r.workspace_views()
    assert wv[0]["scope"] == "application"


def test_permission_namespaces_directory_not_grant():
    r = ModuleRegistry()
    r.register(_mini("a"))
    ns = r.permission_namespaces()
    assert ns[0]["namespaces"] == ["a"]


def test_health_report():
    r = ModuleRegistry()
    r.register(_mini("a", status=ModuleStatus.ENABLED))
    r.register(_mini("b", status=ModuleStatus.PLACEHOLDER))
    hr = {h["module_id"]: h["health"] for h in r.health_report()}
    assert hr["b"] == ModuleHealth.NOT_IMPLEMENTED.value


# ── default registry: Trading + IELTSAlert + placeholders ──────────────────────
def test_default_registry_has_trading_enabled():
    r = build_default_registry()
    t = r.get("trading")
    assert t is not None
    assert t.status == ModuleStatus.ENABLED
    assert t.health() == ModuleHealth.HEALTHY
    assert "/trading" in t.routes
    assert t.search_provider.object_types == ("order", "account", "strategy", "reconciliation")


def test_default_registry_placeholders_metadata_only():
    r = build_default_registry()
    for pid in ("hcgpos", "travel", "finance"):
        m = r.get(pid)
        assert m is not None, pid
        assert m.status == ModuleStatus.PLACEHOLDER
        assert m.health() == ModuleHealth.NOT_IMPLEMENTED
        assert m.feature_flags.get("implemented") is False


def test_trading_and_ielts_are_enabled_modules_by_default():
    r = build_default_registry()
    assert {m.id for m in r.list_enabled()} == {"trading", "ielts"}


def test_ielts_descriptor_is_truthful_and_provider_safe():
    ielts = build_default_registry().get("ielts")
    assert ielts.status == ModuleStatus.ENABLED
    assert ielts.health() == ModuleHealth.HEALTHY
    assert ielts.feature_flags["provider_assisted_scoring"] is False
    assert ielts.feature_flags["official_scoring"] is False
    assert ielts.feature_flags["live_availability"] is False
    assert ielts.feature_flags["payment_settlement"] is False
    assert "deterministic_local_feedback" in ielts.capabilities


def test_trading_declares_no_live_capability():
    r = build_default_registry()
    t = r.get("trading")
    assert t.feature_flags["live_trading"] is False
    assert t.feature_flags["real_money"] is False
    assert t.feature_flags["external_broker"] is False


def test_to_public_is_serializable_shape():
    r = build_default_registry()
    pub = r.to_public()
    assert pub["enabled_count"] == 2
    assert pub["navigation"]["group"] == "applications"
    assert len(pub["dashboard_cards"]) == len(r.list_installed())


def test_process_registry_is_stable_singleton():
    assert get_registry() is get_registry()
    assert get_registry().get("trading") is not None


# ── registration grants no capability (RBAC stays authoritative) ────────────────
def test_module_registration_does_not_grant_permission():
    # viewer has PLATFORM_READ (can see modules) but not PLATFORM_WRITE
    _ctx("viewer").require_permission(PlatformPermission.PLATFORM_READ)
    from saathi.platform.context import PlatformContextError
    with pytest.raises(PlatformContextError):
        _ctx("viewer").require_permission(PlatformPermission.PLATFORM_WRITE)
    # a module declaring a permission namespace does not create or grant it
    r = build_default_registry()
    assert "paper_account" in r.get("trading").permissions
