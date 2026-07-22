"""M22 — Governed provider implementation and legacy SDK migration."""
from __future__ import annotations

import ast
import json
from pathlib import Path
from unittest import mock

import pytest

from saathi.inference.adapters import http_providers as hp
from saathi.inference.adapters.grounding import GroundingResult, grounded_generate
from saathi.inference.release_check import run_release_check, PROVIDER_SDK_ALLOWLIST
from saathi.inference.residual_paths import (
    ResidualDisposition,
    residual_paths_snapshot,
    get_residual_control,
)
from saathi.inference.runtime_gate import (
    EXPECTED_EXCEPTION_COUNT,
    validate_residual_manifest,
    GateState,
)
from saathi.llm import LLM_GENERATE_DEPRECATION, LLMResult, generate
from saathi.model_router import ModelLabel, ModelRouter, ProviderSpec


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs" / "M21_3_RESIDUAL_EXCEPTION_MANIFEST.json"


# ── Inventory / invariants ─────────────────────────────────────────────────


def test_unknown_and_bypass_zero():
    snap = residual_paths_snapshot()
    assert snap["unknown_count"] == 0
    assert snap["direct_provider_bypass_count"] == 0
    assert snap.get("explicit_legacy_exception_count", 0) == 0
    assert snap["production_certified"] is False


def test_m22_migrated_paths_not_legacy_exception():
    for path_id in (
        "legacy_llm_generate",
        "agent_runtime_governed",
        "tools_research",
        "http_providers_transport",
        "agent_provider_adapter",
        "research_grounding_adapter",
    ):
        ctrl = get_residual_control(path_id)
        assert ctrl is not None, path_id
        assert ctrl.disposition is not ResidualDisposition.EXPLICIT_LEGACY_EXCEPTION
        assert ctrl.disposition is not ResidualDisposition.UNKNOWN
        assert ctrl.disposition is not ResidualDisposition.DIRECT_PROVIDER_BYPASS


def test_manifest_exception_count_shrunk():
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert data["unknown_count"] == 0
    assert data["direct_provider_bypass_count"] == 0
    assert data["production_certified"] is False
    assert len(data["exceptions"]) == EXPECTED_EXCEPTION_COUNT
    migrated = set(data.get("m22_migrated_path_ids") or [])
    assert "legacy_llm_generate_execution" in migrated
    assert "agent_sdk_clients" in migrated
    assert "tools_research_grounding" in migrated
    for ex in data["exceptions"]:
        assert ex["path_id"] not in {
            "legacy_llm_generate_execution",
            "agent_sdk_clients",
            "tools_research_grounding",
        }


def test_validate_residual_manifest_pass():
    st, ev, blockers = validate_residual_manifest()
    assert st is GateState.PASS, blockers
    assert ev["exception_count"] == EXPECTED_EXCEPTION_COUNT


# ── Facade purity ──────────────────────────────────────────────────────────


def _src(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_llm_py_has_no_provider_urls():
    src = _src("saathi/llm.py")
    for sub in (
        "api.openai.com",
        "api.anthropic.com",
        "api.groq.com",
        "generativelanguage.googleapis.com",
        "openrouter.ai/api",
    ):
        assert sub not in src


def test_agent_py_has_no_sdk_imports():
    src = _src("saathi/agent.py")
    assert "from openai" not in src
    assert "import anthropic" not in src
    assert "api.groq.com" not in src
    assert "generativelanguage.googleapis.com" not in src
    assert "agent_provider" in src


def test_research_py_has_no_direct_gemini_http():
    src = _src("saathi/tools/research.py")
    assert "generativelanguage.googleapis.com" not in src
    assert "httpx" not in src
    assert "grounded_generate" in src or "adapters.grounding" in src


def test_http_providers_owns_transports():
    assert "anthropic" in hp.DEFAULT_FAMILY_CALLERS
    assert "gemini" in hp.DEFAULT_FAMILY_CALLERS
    inv = hp.transport_inventory()
    assert len(inv) >= 8
    assert all(i["classification"] == "CANONICAL_TRANSPORT" for i in inv)


def test_sdk_allowlist_excludes_migrated_facades():
    assert "saathi/llm.py" not in PROVIDER_SDK_ALLOWLIST
    assert "saathi/agent.py" not in PROVIDER_SDK_ALLOWLIST
    assert "saathi/tools/research.py" not in PROVIDER_SDK_ALLOWLIST


# ── llm.generate facade ────────────────────────────────────────────────────


def test_llm_generate_deprecation_m22():
    assert LLM_GENERATE_DEPRECATION["deprecated"] is True
    assert LLM_GENERATE_DEPRECATION["migrated"] == "M22"
    assert LLM_GENERATE_DEPRECATION["classification"] == "COMPATIBILITY_FACADE"
    assert "http_providers" in LLM_GENERATE_DEPRECATION["provider_http"]


def test_llm_generate_injected_caller(monkeypatch):
    monkeypatch.delenv("SAATHI_INFERENCE_KILL_ALL", raising=False)

    def avail(name: str) -> bool:
        return name.startswith("groq/")

    router = ModelRouter(is_available=avail)
    original_route = router.route

    def route(label, privacy=None, prefer=None):
        chain = original_route(label, privacy=privacy, prefer=prefer)
        if chain:
            return chain
        return [
            ProviderSpec(
                name="groq/test",
                capabilities=frozenset({ModelLabel.STANDARD}),
                cost_per_1k=0.0,
                latency_tier=1,
                is_local=False,
                quality_tier=1,
            )
        ]

    router.route = route  # type: ignore[method-assign]
    res = generate(
        ModelLabel.STANDARD,
        "hi",
        router=router,
        callers={"groq": lambda p, s, m, t: ("ok-m22", "model-x", {})},
        trace=False,
        caller_id="legacy_llm_generate",
    )
    assert isinstance(res, LLMResult)
    assert res.text == "ok-m22"


def test_llm_generate_kill(monkeypatch):
    monkeypatch.setenv("SAATHI_INFERENCE_KILL_ALL", "1")
    with pytest.raises(RuntimeError):
        generate(
            ModelLabel.STANDARD,
            "hi",
            callers={"groq": lambda p, s, m, t: ("x", "m", {})},
            trace=False,
        )
    monkeypatch.delenv("SAATHI_INFERENCE_KILL_ALL", raising=False)


def test_misconfigured_credential_message(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "YOUR_KEY_HERE")
    with pytest.raises(RuntimeError, match="MISCONFIGURED"):
        hp.call_anthropic("p", "s", 10, 5)


# ── Research grounding ─────────────────────────────────────────────────────


def test_grounding_injectable_transport(monkeypatch):
    monkeypatch.delenv("SAATHI_INFERENCE_KILL_ALL", raising=False)
    monkeypatch.setenv("GOOGLE_API_KEY", "test-fake-key-not-real")

    def fake_transport(**kwargs):
        return GroundingResult(text="grounded-ok", model="fake-model")

    out = grounded_generate("topic", transport=fake_transport)
    assert out.text == "grounded-ok"
    assert out.capability == "google_search_grounding"


def test_research_uses_adapter(monkeypatch):
    monkeypatch.delenv("SAATHI_INFERENCE_KILL_ALL", raising=False)

    def fake_grounded(prompt, max_tokens=800):
        return "facts"

    monkeypatch.setattr("saathi.tools.research._grounded", fake_grounded)
    from saathi.tools.research import research

    out = research("kathmandu weather")
    assert out.get("findings") == "facts"
    assert out.get("caller_id") == "research_tools"
    assert out.get("privacy") == "public_web"


def test_research_error_redacted(monkeypatch):
    monkeypatch.delenv("SAATHI_INFERENCE_KILL_ALL", raising=False)

    def boom(prompt, max_tokens=800):
        raise RuntimeError("SECRET_BODY_SHOULD_NOT_LEAK")

    monkeypatch.setattr("saathi.tools.research._grounded", boom)
    from saathi.tools.research import research

    out = research("t")
    assert "error" in out
    assert "SECRET" not in str(out.get("error", ""))


def test_research_kill(monkeypatch):
    monkeypatch.setenv("SAATHI_INFERENCE_KILL_ALL", "1")
    from saathi.tools import research as research_mod

    with pytest.raises(RuntimeError):
        research_mod._preflight("t", 100)
    monkeypatch.delenv("SAATHI_INFERENCE_KILL_ALL", raising=False)


# ── Agent ──────────────────────────────────────────────────────────────────


def test_agent_preflight_kill(monkeypatch):
    monkeypatch.setenv("SAATHI_INFERENCE_KILL_ALL", "1")
    from saathi.agent import SaathiAgent

    a = object.__new__(SaathiAgent)
    with pytest.raises(RuntimeError):
        a._m21_preflight("hi", "sys", 100)
    monkeypatch.delenv("SAATHI_INFERENCE_KILL_ALL", raising=False)


def test_agent_uses_build_session():
    src = _src("saathi/agent.py")
    assert "build_agent_session" in src
    tree = ast.parse(src)
    # No OpenAI() constructor in agent.py
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in {"OpenAI", "Anthropic"}:
                pytest.fail("agent.py must not construct OpenAI/Anthropic")


# ── Release check ──────────────────────────────────────────────────────────


def test_release_check_pass():
    rep = run_release_check()
    assert rep.ok is True, [f.to_dict() for f in rep.findings if f.severity == "blocking"]
    assert rep.production_certified is False
    assert rep.summary.get("m22_facade_check") is True


def test_cloud_engines_use_http_providers():
    src = _src("saathi/inference/adapters/cloud.py")
    assert "http_providers" in src
    assert "from saathi import llm" not in src


# ── Trading guardian ───────────────────────────────────────────────────────


def test_trading_untouched():
    for ex in json.loads(MANIFEST.read_text(encoding="utf-8"))["exceptions"]:
        assert "trading" not in ex["path_id"].lower()
        assert "withdrawal" not in ex["path_id"].lower()
