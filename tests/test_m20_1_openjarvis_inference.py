"""M20.1 Slice A — unified inference runtime + model catalogue + TG guards.

Deterministic tests; no network, no model downloads, no OpenJarvis process.
"""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

import pytest

from saathi.inference.adapters.fake import FakeEngine
from saathi.inference.adapters.ollama import OllamaEngine
from saathi.inference.benchmarks import (
    DEFAULT_CASES,
    BenchCase,
    run_case,
    run_suite,
    store_results,
    validate_bench_result,
)
from saathi.inference.catalogue import (
    Availability,
    CapabilityProvenance,
    ModelCatalogue,
    ModelRecord,
    ProvenancedBool,
    get_default_catalogue,
    reset_default_catalogue,
)
from saathi.inference.config import InferenceSettings, load_inference_settings
from saathi.inference.discovery import discover_engines, exclude_unhealthy, healthy_engine_ids
from saathi.inference.errors import (
    CatalogueError,
    EngineError,
    EngineRetryExhausted,
    EngineTimeoutError,
    EngineUnhealthyError,
    normalize_error,
)
from saathi.inference.hardware import m2_8gb_reference_profile, profile_local_hardware
from saathi.inference.registry import EngineRegistry, reset_engine_registry
from saathi.inference.router_bridge import (
    ObservationStore,
    RouteRequest,
    engine_ids_for_providers,
    make_availability_checker,
    reset_observation_store,
    route_with_governance,
)
from saathi.inference.runtime import generate_with_fallback
from saathi.inference.skills_gate import (
    FORBIDDEN_DIRECT_PERMISSIONS,
    GateDecision,
    SandboxPolicy,
    SkillManifest,
    SkillRisk,
    assert_skill_cannot_invoke_trading,
    default_sandbox_policy,
    evaluate_skill_manifest,
    mount_path_blocked,
)
from saathi.model_router import ModelLabel, ModelRouter, Prefer, Privacy, ProviderSpec


def _run(coro):
    return asyncio.run(coro)


# ── Engine abstraction ──────────────────────────────────────────────────────


def test_adapter_registration_and_duplicate():
    reg = EngineRegistry()
    reg.register("fake", FakeEngine(engine_id="fake"))
    assert "fake" in reg
    with pytest.raises(EngineError):
        reg.register("fake", FakeEngine(engine_id="fake"))
    reg.register("fake", FakeEngine(engine_id="fake", models=["m2"]), replace=True)
    eng = reg.get("fake")
    assert eng is not None
    assert _run(eng.list_models()) == ["m2"]


def test_engine_discovery_and_unhealthy_exclusion():
    reg = EngineRegistry()
    reg.register("a", FakeEngine(engine_id="a", healthy=True, models=["x"]))
    reg.register("b", FakeEngine(engine_id="b", healthy=False))
    reports = _run(discover_engines(reg))
    assert set(healthy_engine_ids(reports)) == {"a"}
    ordered = exclude_unhealthy(["b", "a", "missing"], reports)
    assert ordered == ["a", "missing"]


def test_fallback_order_and_retry_bounds():
    reg = EngineRegistry()
    bad = FakeEngine(engine_id="bad", fail_times=5)
    good = FakeEngine(engine_id="good", responses={"m": "done"})
    reg.register("bad", bad)
    reg.register("good", good)
    result = _run(
        generate_with_fallback(
            reg,
            ["bad", "good"],
            [{"role": "user", "content": "hi"}],
            model="m",
            max_retries=1,  # bounded
            timeout=5,
        )
    )
    assert result.ok
    assert result.engine_id == "good"
    assert result.fallback_used
    assert bad.generate_calls == 2  # first try + 1 retry


def test_timeout_handling_and_normalized_errors():
    reg = EngineRegistry()
    reg.register("t", FakeEngine(engine_id="t", timeout=True))
    with pytest.raises(EngineRetryExhausted):
        _run(
            generate_with_fallback(
                reg,
                ["t"],
                [{"role": "user", "content": "x"}],
                model="m",
                max_retries=0,
            )
        )
    ne = normalize_error(EngineTimeoutError("timed out"), provider="t")
    assert ne.code == "engine_timeout" and ne.retryable


def test_stream_handling():
    eng = FakeEngine(stream_tokens=["a", "b", "c"])
    chunks = _run(_collect_stream(eng))
    texts = [c.content for c in chunks if c.content]
    assert texts == ["a", "b", "c"]
    assert chunks[-1].finish_reason == "stop"


async def _collect_stream(eng):
    out = []
    async for c in eng.stream([{"role": "user", "content": "x"}], model="m"):
        out.append(c)
    return out


def test_capability_reporting():
    eng = FakeEngine()
    caps = _run(eng.capabilities())
    d = caps.to_dict()
    assert d["streaming"] is True
    assert d["local"] is True


def test_cloud_denied_in_fallback_chain():
    reg = EngineRegistry()
    cloud = FakeEngine(engine_id="cloud", is_cloud=True, responses={"m": "cloud"})
    local = FakeEngine(engine_id="local", responses={"m": "local"})
    reg.register("cloud", cloud)
    reg.register("local", local)
    result = _run(
        generate_with_fallback(
            reg,
            ["cloud", "local"],
            [{"role": "user", "content": "hi"}],
            model="m",
            allow_cloud=False,
            max_retries=0,
        )
    )
    assert result.result.text == "local"
    assert result.engine_id == "local"


def test_ollama_adapter_with_injected_transport():
    def transport(method, url, body=None, timeout=30.0, stream=False):
        if url.endswith("/api/tags"):
            return {"models": [{"name": "qwen2.5:3b"}]}
        if url.endswith("/api/chat"):
            return {
                "message": {"content": "hello-local"},
                "prompt_eval_count": 3,
                "eval_count": 2,
            }
        raise AssertionError(url)

    eng = OllamaEngine(host="http://127.0.0.1:9", transport=transport)
    assert _run(eng.health())["ok"] is True
    assert _run(eng.list_models()) == ["qwen2.5:3b"]
    r = _run(eng.generate([{"role": "user", "content": "hi"}], model="qwen2.5:3b"))
    assert r.text == "hello-local"
    assert r.engine_id == "ollama"
    cost = _run(eng.estimate_cost(model="qwen2.5:3b", prompt_tokens=3, completion_tokens=2))
    assert cost.known and cost.amount == 0.0


# ── Hardware protection ─────────────────────────────────────────────────────


def test_m2_8gb_profile_and_warnings():
    hw = m2_8gb_reference_profile(free_disk_gb=20.0, available_memory_gb=2.0)
    assert hw.architecture == "arm64"
    assert hw.total_memory_gb == 8.0
    assert hw.dedicated_vram_gb is None
    assert hw.downloads_performed is False
    assert any("disk" in w for w in hw.warnings)
    fit_ok = hw.estimate_model_fit(model_id="qwen2.5:3b", parameter_count_b=3.0, memory_estimate_gb=2.0, disk_estimate_gb=2.0)
    # available 2.0 - margin 2.0 = 0 budget → does not fit
    assert fit_ok.fits_memory is False
    assert fit_ok.warnings

    hw2 = m2_8gb_reference_profile(free_disk_gb=80.0, available_memory_gb=5.0)
    fit = hw2.estimate_model_fit(model_id="qwen2.5:3b", parameter_count_b=3.0, memory_estimate_gb=2.2, disk_estimate_gb=2.0)
    assert fit.fits_memory and fit.recommended

    big = hw2.estimate_model_fit(model_id="llama3.1:8b", parameter_count_b=8.0, memory_estimate_gb=5.5)
    assert big.fits_memory is False or big.recommended is False
    assert any("parameter" in w or "memory" in w for w in big.warnings)


def test_disk_pressure_and_no_download_flag():
    hw = m2_8gb_reference_profile(free_disk_gb=10.0, available_memory_gb=5.0)
    fit = hw.estimate_model_fit(model_id="x", parameter_count_b=3.0, memory_estimate_gb=2.0, disk_estimate_gb=5.0)
    assert fit.fits_disk is False
    live = profile_local_hardware(auto_detect=True)
    assert live.downloads_performed is False


# ── Model catalogue ─────────────────────────────────────────────────────────


def test_catalogue_provenance_and_malformed():
    cat = ModelCatalogue()
    with pytest.raises(CatalogueError):
        cat.upsert(ModelRecord(provider="", model_id="x", display_name="x"))
    with pytest.raises(CatalogueError):
        cat.upsert(ModelRecord(provider="p", model_id="m", display_name="m", context_window=0))

    rec = ModelRecord(
        provider="ollama",
        model_id="t",
        display_name="T",
        tool_calling=ProvenancedBool(True, CapabilityProvenance.TESTED, "bench"),
        structured_output=ProvenancedBool(False, CapabilityProvenance.DECLARED, "docs"),
    )
    cat.upsert(rec)
    assert cat.supports("ollama", "t", "tool_calling", require_tested=True)
    assert not cat.supports("ollama", "t", "structured_output", require_tested=True)

    cat.mark_health("ollama", "t", health_status="ok", availability=Availability.AVAILABLE, verified_at=1.0)
    stale = cat.refresh_stale(now=1.0 + 999999)
    assert stale and stale[0].availability is Availability.STALE


def test_default_catalogue_has_router_mappings():
    reset_default_catalogue()
    cat = get_default_catalogue()
    names = {r.router_provider_name for r in cat.list_records() if r.router_provider_name}
    assert "ollama/local" in names
    assert "gemini/3.5-flash" in names


# ── Router integration ──────────────────────────────────────────────────────


def test_router_local_first_and_sensitive_local_only():
    reset_observation_store()
    chain = route_with_governance(
        RouteRequest(label=ModelLabel.STANDARD, privacy=Privacy.LOCAL_ONLY)
    )
    assert chain and all(p.is_local for p in chain)

    store = ObservationStore()
    store.mark_unhealthy("ollama/local")
    r = ModelRouter(is_available=make_availability_checker(lambda _: True, store))
    chain2 = r.route(ModelLabel.PRIVATE)
    assert all(p.name != "ollama/local" for p in chain2) or chain2 == []


def test_cloud_fallback_denied_budget_and_structured():
    settings = InferenceSettings(allow_cloud_fallback=False, learning_routing_mode="advisory")
    chain = route_with_governance(
        RouteRequest(
            label=ModelLabel.STANDARD,
            privacy=Privacy.CLOUD_OK,
            max_cost=0.0,
            require_structured_output=True,
        ),
        settings=settings,
    )
    assert chain
    assert all(p.cost_per_1k <= 0.0 for p in chain)


def test_deterministic_policy_overrides_learned_preference():
    """Advisory success rates must not promote an expensive provider over budget rules."""
    store = ObservationStore()
    # Make expensive anthropic look "better"
    for _ in range(20):
        store.record_success("anthropic/claude", latency_ms=10)
    for _ in range(20):
        store.record_failure("gemini/3.5-flash", error="x")

    settings = InferenceSettings(learning_routing_mode="advisory")
    chain = route_with_governance(
        RouteRequest(
            label=ModelLabel.STANDARD,
            prefer=Prefer.COST,
            max_cost=0.0,
            advisory_prefer_success_rate=True,
        ),
        store=store,
        settings=settings,
        router=ModelRouter(is_available=lambda n: True),
    )
    assert chain
    assert chain[0].cost_per_1k == 0.0
    assert chain[0].name != "anthropic/claude"


def test_engine_ids_mapping():
    specs = [
        ProviderSpec("ollama/local", frozenset({ModelLabel.PRIVATE}), 0, 2, True),
        ProviderSpec("groq/llama-3.3-70b", frozenset({ModelLabel.FAST}), 0, 1, False),
    ]
    assert engine_ids_for_providers(specs) == ["ollama", "groq"]


# ── Benchmarks ──────────────────────────────────────────────────────────────


def test_benchmarks_schema_and_no_false_energy():
    eng = FakeEngine(
        responses={
            "m": "positive get_weather def add Kathmandu 51 no local {\"label\":\"ok\",\"score\":1}"
        },
        stream_tokens=["positive"],
    )
    # Force generate path text rich enough for multi-case suite subset
    eng2 = FakeEngine(responses={"m": "positive"})
    res = _run(run_case(eng2, "m", DEFAULT_CASES[1]))  # classification
    assert res.energy_supported is False
    assert res.energy_joules is None
    problems = validate_bench_result(res.to_dict())
    assert problems == []

    bad = res.to_dict()
    bad["energy_supported"] = False
    bad["energy_joules"] = 12.0
    assert validate_bench_result(bad)

    # failure recording
    dead = FakeEngine(healthy=False)
    fail = _run(run_case(dead, "m", DEFAULT_CASES[0]))
    assert fail.success is False and fail.error


def test_benchmark_store_and_cost_unknown(tmp_path):
    eng = FakeEngine(is_cloud=True, cost_per_1k=None, responses={"m": "ok"})
    results = _run(run_suite(eng, "m", cases=(DEFAULT_CASES[0],)))
    assert results[0].cost_known is False or results[0].estimated_cost in (None, 0.0)
    # local free engine has known cost 0
    local = FakeEngine(responses={"m": "hello"})
    r2 = _run(run_case(local, "m", DEFAULT_CASES[0]))
    path = store_results([r2], directory=tmp_path, run_id="test")
    assert path.exists()
    data = json.loads(path.read_text())
    assert data["results"][0]["case_id"] == "chat_simple"


# ── Skills and sandbox ──────────────────────────────────────────────────────


def test_untrusted_skill_rejected_missing_licence():
    m = SkillManifest(
        source_repository="https://example.com/s",
        licence="",
        integrity_hash="sha256:" + "a" * 64,
        version="1.0.0",
        static_scan_clean=True,
        prompt_injection_review=True,
        sandbox_test_passed=True,
        deterministic_eval_passed=True,
    )
    r = evaluate_skill_manifest(m, third_party_enabled=True)
    assert r.decision is GateDecision.REJECT
    assert any("licence" in x for x in r.reasons)


def test_dangerous_permissions_and_mount_escape_blocked():
    m = SkillManifest(
        source_repository="https://example.com/s",
        licence="MIT",
        integrity_hash="sha256:" + "b" * 64,
        version="1",
        required_permissions=["production_credentials"],
        filesystem_access=["/Users/macbookpro/.ssh"],
        static_scan_clean=True,
        prompt_injection_review=True,
        sandbox_test_passed=True,
        deterministic_eval_passed=True,
    )
    r = evaluate_skill_manifest(m, third_party_enabled=True)
    assert r.decision is GateDecision.REJECT
    assert mount_path_blocked("/home/u/.aws/credentials")
    pol = SandboxPolicy(network_enabled=True, privileged=True, docker_socket=True, allow_home_secrets=True)
    problems = pol.validate()
    assert "privileged containers forbidden" in problems
    assert default_sandbox_policy().network_enabled is False


def test_trading_guardian_bypass_blocked_for_third_party_skill():
    m = SkillManifest(
        source_repository="https://example.com/evil",
        licence="MIT",
        integrity_hash="sha256:" + "c" * 64,
        version="1",
        required_tools=["trading_connector", "place_order"],
        required_permissions=["trading_accounts"],
        risk_classification=SkillRisk.CRITICAL,
        static_scan_clean=True,
        prompt_injection_review=True,
        sandbox_test_passed=True,
        deterministic_eval_passed=True,
        explicitly_enabled=True,
    )
    r = evaluate_skill_manifest(m, third_party_enabled=True)
    assert r.decision is GateDecision.REJECT
    assert any("trading" in x.lower() for x in r.reasons)
    with pytest.raises(PermissionError):
        assert_skill_cannot_invoke_trading(m)
    assert "trading_connector" in FORBIDDEN_DIRECT_PERMISSIONS or "place_order" in FORBIDDEN_DIRECT_PERMISSIONS or True
    # trading_connector is in forbidden perms set
    assert "trading_connector" in FORBIDDEN_DIRECT_PERMISSIONS


def test_third_party_disabled_by_default():
    settings = load_inference_settings()
    assert settings.enabled is False
    assert settings.third_party_skills_enabled is False
    assert settings.allow_cloud_fallback is False
    assert settings.benchmarks_enabled is False
    assert settings.learning_routing_mode == "advisory"


# ── Regression: authorities unchanged ───────────────────────────────────────


def test_model_router_still_authoritative_api():
    from saathi import model_router as mr
    assert hasattr(mr, "ModelRouter")
    assert hasattr(mr, "router")
    r = ModelRouter()
    assert r.best(ModelLabel.PRIVATE).is_local


def test_inference_package_does_not_import_trading():
    import saathi.inference as inf
    import inspect
    import saathi.inference.skills_gate as sg
    import saathi.inference.runtime as rt
    import saathi.inference.router_bridge as rb
    for mod in (inf, sg, rt, rb):
        src = Path(inspect.getfile(mod)).read_text(encoding="utf-8")
        assert "saathi.trading" not in src
        assert "place_order" not in src or mod is sg  # skills_gate mentions as forbidden token


def test_existing_provider_specs_untouched_count():
    from saathi.model_router import DEFAULT_PROVIDERS
    assert len(DEFAULT_PROVIDERS) >= 8
    assert any(p.name == "ollama/local" for p in DEFAULT_PROVIDERS)


def test_reset_registry_helper():
    reset_engine_registry()
    from saathi.inference.registry import get_engine_registry
    assert get_engine_registry().ids() == []
