"""M21.0 — Production configuration inventory + provider policy (deterministic)."""
from __future__ import annotations

import os
from unittest import mock

import pytest

from saathi.inference.config import InferenceSettings, load_inference_settings
from saathi.inference.path_inventory import (
    CALL_PATH_INVENTORY,
    PathClass,
    path_inventory_snapshot,
    residual_direct_paths,
)
from saathi.inference.prod_config import (
    production_config_bundle,
    validate_production_config,
)
from saathi.inference.provider_policy import (
    PROVIDER_POLICIES,
    ProviderAvailability,
    family_for_model_router_name,
    is_master_killed,
    is_provider_killed,
    is_provider_policy_enabled,
    kill_switch_env_keys,
    provider_policy_snapshot,
    resolve_availability,
)
from saathi.m20_console.flags import FLAG_CATALOG, disable_procedure, flag_snapshot


# ── Path inventory ────────────────────────────────────────────────────────


def test_path_inventory_schema_and_authorities():
    snap = path_inventory_snapshot()
    assert snap["schema"] == "m21.0.path_inventory.v1"
    assert snap["milestone"] == "M21.0"
    assert snap["second_model_router"] is False
    assert snap["second_inference_package"] is False
    assert snap["path_count"] == len(CALL_PATH_INVENTORY)
    assert snap["path_count"] >= 10
    ids = {p["path_id"] for p in snap["paths"]}
    assert "governed_local_gateway" in ids
    assert "legacy_llm_generate" in ids
    assert "model_router" in ids
    assert "cheap_ask" in ids
    assert "chat_engine" in ids


def test_residual_direct_inventoried_not_migrated():
    residual = residual_direct_paths()
    # M23: chat_engine is CANONICAL_GOVERNED; remaining residual_direct still inventoried
    assert not any(p.path_id == "chat_engine" for p in residual)
    for p in residual:
        assert p.classification is PathClass.RESIDUAL_DIRECT
        assert p.migration.value == "inventoried"
    # chat path still inventoried as governed
    from saathi.inference.path_inventory import CALL_PATH_INVENTORY

    chat = next(p for p in CALL_PATH_INVENTORY if p.path_id == "chat_engine")
    assert chat.classification is PathClass.CANONICAL_GOVERNED


# ── Provider policy + kill switches ───────────────────────────────────────


def test_provider_policy_covers_local_and_cloud():
    ids = {p.family_id for p in PROVIDER_POLICIES}
    assert "ollama" in ids
    assert "anthropic" in ids
    assert "openai" in ids
    snap = provider_policy_snapshot()
    assert snap["schema"] == "m21.0.provider_policy.v1"
    assert snap["second_model_router"] is False
    assert "SAATHI_INFERENCE_KILL_ALL" in snap["kill_switch_env_keys"]
    assert "SAATHI_PROVIDER_KILL_OLLAMA" in snap["kill_switch_env_keys"]


def test_cloud_disabled_by_default_policy():
    assert resolve_availability("anthropic") is ProviderAvailability.POLICY_DISABLED
    assert resolve_availability("openai") is ProviderAvailability.POLICY_DISABLED
    assert is_provider_policy_enabled("anthropic") is False


def test_ollama_policy_enabled_only_when_master_on():
    assert resolve_availability("ollama", master_inference_enabled=False) is (
        ProviderAvailability.POLICY_DISABLED
    )
    assert resolve_availability("ollama", master_inference_enabled=True) is (
        ProviderAvailability.POLICY_ENABLED
    )


def test_kill_switch_ollama(monkeypatch):
    monkeypatch.delenv("SAATHI_INFERENCE_KILL_ALL", raising=False)
    monkeypatch.setenv("SAATHI_PROVIDER_KILL_OLLAMA", "1")
    assert is_provider_killed("ollama") is True
    assert resolve_availability("ollama", master_inference_enabled=True) is (
        ProviderAvailability.KILLED
    )


def test_kill_all(monkeypatch):
    monkeypatch.setenv("SAATHI_INFERENCE_KILL_ALL", "1")
    assert is_master_killed() is True
    assert is_provider_killed("ollama") is True
    assert resolve_availability("anthropic") is ProviderAvailability.MASTER_KILLED


def test_unknown_family_fail_closed():
    assert is_provider_killed("totally_unknown_xyz") is True
    assert resolve_availability("totally_unknown_xyz") is ProviderAvailability.UNSUPPORTED


def test_family_for_model_router_name():
    assert family_for_model_router_name("anthropic/claude") == "anthropic"
    assert family_for_model_router_name("ollama/local") == "ollama"
    assert family_for_model_router_name("gemini/3.5-flash") == "gemini"
    assert family_for_model_router_name("deepseek/deepseek-chat") in {
        "deepseek",
        "openrouter",
    }


# ── Production config validation ──────────────────────────────────────────


def test_validate_safe_defaults():
    s = InferenceSettings()  # all defaults off
    rep = validate_production_config(s)
    assert rep.ok is True
    assert rep.blocking == 0
    assert rep.posture == "pilot_safe"
    assert rep.production_certified is False
    codes = {f.code for f in rep.findings}
    assert "safe_defaults" in codes


def test_validate_blocking_gateway_without_master():
    s = InferenceSettings(enabled=False, gateway_enabled=True)
    rep = validate_production_config(s)
    assert rep.ok is False
    assert rep.blocking >= 1
    assert any(f.code == "gateway_without_master" for f in rep.findings)
    assert rep.posture == "unsafe"


def test_validate_blocking_skills_without_sandbox():
    s = InferenceSettings(
        third_party_skills_enabled=True,
        skill_sandbox_required=False,
    )
    rep = validate_production_config(s)
    assert rep.ok is False
    assert any(f.code == "skills_without_sandbox" for f in rep.findings)


def test_validate_warning_cloud_fallback():
    s = InferenceSettings(allow_cloud_fallback=True)
    rep = validate_production_config(s)
    assert rep.ok is True  # warning only
    assert rep.warnings >= 1
    assert any(f.code == "cloud_fallback_enabled" for f in rep.findings)
    assert rep.posture == "attention"


def test_validate_blocking_concurrency_cap():
    s = InferenceSettings(max_concurrent_local=5)
    # dataclass is frozen — construct with invalid via replace pattern
    # InferenceSettings clamps on load; construct raw for validator
    from dataclasses import replace

    # frozen allows replace
    s2 = replace(s, max_concurrent_local=5)
    rep = validate_production_config(s2)
    assert rep.ok is False
    assert any(f.code == "concurrency_too_high" for f in rep.findings)


def test_load_settings_still_clamps():
    with mock.patch.dict(os.environ, {"SAATHI_INFERENCE_MAX_CONCURRENT": "99"}, clear=False):
        s = load_inference_settings()
        assert s.max_concurrent_local <= 2


def test_production_bundle_authorities():
    b = production_config_bundle()
    assert b["schema"] == "m21.0.production_bundle.v1"
    assert b["authorities"]["second_model_router"] is False
    assert b["authorities"]["trading_guardian_engaged"] is False
    assert "validation" in b
    assert "provider_policy" in b
    assert "path_inventory" in b
    assert "disable" in b


# ── Console flag catalog extension ────────────────────────────────────────


def test_flag_catalog_includes_kill_switches():
    keys = {f.key for f in FLAG_CATALOG}
    assert "SAATHI_INFERENCE_KILL_ALL" in keys
    assert "SAATHI_PROVIDER_KILL_OLLAMA" in keys
    assert "SAATHI_PROVIDER_KILL_ANTHROPIC" in keys
    d = disable_procedure()
    assert "provider_kill_keys" in d
    assert "SAATHI_INFERENCE_KILL_ALL" in d["provider_kill_keys"]


def test_flag_snapshot_includes_kills():
    snap = flag_snapshot()
    keys = {r["key"] for r in snap["flags"]}
    assert "SAATHI_PROVIDER_KILL_OLLAMA" in keys


# ── Gateway kill-switch integration ───────────────────────────────────────


@pytest.mark.asyncio
async def test_gateway_respects_ollama_kill(monkeypatch):
    monkeypatch.setenv("SAATHI_INFERENCE_ENABLED", "1")
    monkeypatch.setenv("SAATHI_INFERENCE_GATEWAY_ENABLED", "1")
    monkeypatch.setenv("SAATHI_PROVIDER_KILL_OLLAMA", "1")
    monkeypatch.delenv("SAATHI_INFERENCE_KILL_ALL", raising=False)

    from saathi.inference.gateway_path import (
        GovernedLocalInferencePath,
        reset_gateway_path_state,
    )
    from saathi.inference.request import InferenceErrorCategory, InferenceRequest

    reset_gateway_path_state()
    path = GovernedLocalInferencePath(settings=load_inference_settings())
    req = InferenceRequest(
        prompt="hello",
        caller_component="test_m21_0",
        local_only=True,
        max_output_tokens=32,
    )
    result = await path.execute(req)
    assert result.ok is False
    assert result.error_category == InferenceErrorCategory.PROVIDER_UNAVAILABLE.value
    assert "kill" in (result.error_message or "").lower() or "KILL" in (
        result.error_message or ""
    )


@pytest.mark.asyncio
async def test_gateway_respects_kill_all(monkeypatch):
    monkeypatch.setenv("SAATHI_INFERENCE_ENABLED", "1")
    monkeypatch.setenv("SAATHI_INFERENCE_GATEWAY_ENABLED", "1")
    monkeypatch.setenv("SAATHI_INFERENCE_KILL_ALL", "1")

    from saathi.inference.gateway_path import (
        GovernedLocalInferencePath,
        reset_gateway_path_state,
    )
    from saathi.inference.request import InferenceErrorCategory, InferenceRequest

    reset_gateway_path_state()
    path = GovernedLocalInferencePath(settings=load_inference_settings())
    result = await path.execute(
        InferenceRequest(prompt="x", caller_component="test_m21_0", local_only=True)
    )
    assert result.ok is False
    assert result.error_category == InferenceErrorCategory.PROVIDER_UNAVAILABLE.value
    assert "KILL_ALL" in (result.error_message or "")


# ── CLI smoke ─────────────────────────────────────────────────────────────


def test_prod_config_cli_validate():
    from saathi.inference.prod_config import main

    assert main(["validate"]) == 0


def test_prod_config_cli_inventory():
    from saathi.inference.prod_config import main

    assert main(["inventory"]) == 0


def test_m20_console_prod_config_cmd():
    from saathi.m20_console.cli import main

    assert main(["prod-config"]) == 0


def test_no_trading_surface_in_m21_modules():
    import saathi.inference.path_inventory as pi
    import saathi.inference.prod_config as pc
    import saathi.inference.provider_policy as pp

    for mod in (pi, pc, pp):
        src = open(mod.__file__, encoding="utf-8").read().lower()
        assert "withdraw" not in src
        assert "live_trade" not in src
