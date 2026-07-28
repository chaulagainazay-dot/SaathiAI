"""M64 — authenticated module discovery: permission-filtered, truthful states,
safe serialization. Backend registry stays authoritative; registration grants
nothing; placeholders never become operational.
"""
from __future__ import annotations

import json

import pytest

from saathi.platform.models import PlatformPermission, role_has_permission
from saathi.platform.module_registry import (
    get_registry, build_default_registry, ModuleState, ModuleStatus, ModuleHealth,
    READ_PERMISSION_BY_NAMESPACE,
)


def _can_read(role):
    def f(perm):
        try:
            return role_has_permission(role, perm)
        except Exception:
            return False
    return f


# ── contract + shape ───────────────────────────────────────────────────────────
def test_discovery_has_contract_version():
    d = build_default_registry().discovery(can_read=_can_read("owner"))
    assert d["contract_version"] == "m64.1"
    assert "installed" in d and "navigation" in d and "dashboard_cards" in d


def test_module_public_has_truthful_flags():
    m = build_default_registry().get("trading")
    pub = m.to_public(can_read=_can_read("owner"))
    assert pub["enabled"] is True
    assert pub["implemented"] is True
    assert pub["state"] == ModuleState.AVAILABLE.value
    assert pub["operational"] is True


# ── permission filtering (fail-closed) ─────────────────────────────────────────
def test_trading_available_for_role_with_paper_reads():
    for role in ("viewer", "operator", "owner"):
        st = build_default_registry().get("trading").resolve_state(can_read=_can_read(role))
        assert st == ModuleState.AVAILABLE, role


def test_trading_permission_restricted_without_reads():
    # a caller whose predicate denies every read → fail closed
    st = build_default_registry().get("trading").resolve_state(can_read=lambda p: False)
    assert st == ModuleState.PERMISSION_RESTRICTED


def test_agent_actor_never_gets_operational_trading():
    st = build_default_registry().get("trading").resolve_state(can_read=_can_read("owner"), is_agent=True)
    assert st == ModuleState.PERMISSION_RESTRICTED


def test_read_permission_map_covers_trading_namespaces():
    m = build_default_registry().get("trading")
    reads = m.candidate_read_permissions()
    assert "paper_account.read" in reads and "paper_safety.read" in reads
    for p in reads:
        PlatformPermission(p)  # valid permission


# ── remaining placeholders remain non-operational ─────────────────────────────
def test_placeholders_not_implemented_and_not_actionable():
    d = build_default_registry().discovery(can_read=_can_read("owner"))
    cards = {c["module_id"]: c for c in d["dashboard_cards"]}
    for pid in ("hcgpos", "travel", "finance"):
        c = cards[pid]
        assert c["state"] == ModuleState.NOT_IMPLEMENTED.value
        assert c["actionable"] is False
        assert c["implemented"] is False
        assert c["primary_route"] == ""   # no live route for a placeholder


def test_only_available_module_exposes_primary_route():
    d = build_default_registry().discovery(can_read=_can_read("owner"))
    cards = {c["module_id"]: c for c in d["dashboard_cards"]}
    assert cards["trading"]["primary_route"] == "/trading"
    assert cards["ielts"]["primary_route"] == "/ielts"
    # restricted caller: trading loses its live route
    d2 = build_default_registry().discovery(can_read=lambda p: False)
    assert {c["module_id"]: c for c in d2["dashboard_cards"]}["trading"]["primary_route"] == ""


# ── navigation truthfulness ────────────────────────────────────────────────────
def test_navigation_marks_actionable_only_for_available():
    d = build_default_registry().discovery(can_read=_can_read("owner"))
    nav = {m["id"]: m for m in d["navigation"]["modules"]}
    assert nav["trading"]["actionable"] is True
    assert nav["ielts"]["actionable"] is True


def test_ielts_requires_canonical_read_permission_and_blocks_agents():
    module = build_default_registry().get("ielts")
    assert module.candidate_read_permissions() == ["ielts.read"]
    assert module.resolve_state(can_read=lambda p: p == "ielts.read") == ModuleState.AVAILABLE
    assert module.resolve_state(can_read=lambda p: False) == ModuleState.PERMISSION_RESTRICTED
    assert module.resolve_state(can_read=lambda p: True, is_agent=True) == ModuleState.PERMISSION_RESTRICTED


# ── safe serialization (no internal leakage) ───────────────────────────────────
def test_serialization_is_json_safe_and_leaks_no_internals():
    d = build_default_registry().discovery(can_read=_can_read("owner"))
    blob = json.dumps(d)  # must be JSON-serializable
    lowered = blob.lower()
    for needle in ("health_fn", "/users/", "\\users\\", "moduledescriptor", ".py", "sqlite", "db_path", "callable"):
        assert needle not in lowered, needle


def test_module_public_keys_are_allowlisted():
    pub = build_default_registry().get("trading").to_public(can_read=_can_read("owner"))
    allowed = {
        "id", "name", "version", "description", "icon", "category", "status",
        "permissions", "routes", "nav_items", "dashboard_widgets", "search_provider",
        "workspace_views", "capabilities", "feature_flags", "health", "enabled",
        "implemented", "state", "operational",
    }
    assert set(pub.keys()) == allowed


# ── determinism + unknown handling ─────────────────────────────────────────────
def test_discovery_is_deterministic():
    a = build_default_registry().discovery(can_read=_can_read("owner"))
    b = build_default_registry().discovery(can_read=_can_read("owner"))
    assert json.dumps(a) == json.dumps(b)


def test_unknown_module_returns_none():
    assert get_registry().get("does-not-exist") is None


# ── disabled module fails safe ─────────────────────────────────────────────────
def test_disabled_module_state():
    reg = build_default_registry()
    reg.disable("trading")
    st = reg.get("trading").resolve_state(can_read=_can_read("owner"))
    assert st == ModuleState.DISABLED


# ── registration still grants nothing ──────────────────────────────────────────
def test_registration_grants_no_permission():
    # Trading declares paper_* namespaces, but a caller with no reads is restricted.
    st = build_default_registry().get("trading").resolve_state(can_read=lambda p: False)
    assert st == ModuleState.PERMISSION_RESTRICTED
    # viewer role's permission set is unchanged by registration
    assert role_has_permission("viewer", PlatformPermission.PAPER_ACCOUNT_READ)
    assert not role_has_permission("viewer", PlatformPermission.PAPER_ORDER_SUBMIT)
