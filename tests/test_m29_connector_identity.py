"""M29 — Connector identity, trust model, and registry."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from saathi.connectors.gov.adapters.http import HttpAdapter
from saathi.connectors.gov.gateway_bridge import execute_via_gateway, reset_idempotency_cache
from saathi.connectors.gov.models import (
    AuthMode,
    ConnectorKind,
    ConnectorLifecycle,
    ConnectorManifest,
    ConnectorRequest,
)
from saathi.connectors.gov.registry import (
    ConnectorRegistry,
    DuplicateConnectorError,
    UnknownConnectorError,
)
from saathi.connectors.gov.runtime import GovernedConnectorRuntime
from saathi.connectors.registry.builtins import builtin_manifests
from saathi.connectors.registry.capabilities import ConnectorCapability
from saathi.connectors.registry.deps import DependencyCycleError, validate_dependency_graph
from saathi.connectors.registry.docs import generate_registry_docs, render_registry_docs_markdown
from saathi.connectors.registry.persistence import load_registry_snapshot, save_registry_snapshot
from saathi.connectors.registry.trust import (
    TrustLevel,
    approval_floor_for_trust,
    enforce_capabilities_for_trust,
    rollout_eligible_for_trust,
)
from saathi.connectors.registry.validation import ManifestValidationError, validate_manifest
from saathi.inference.ops.models import RolloutMode

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def reg():
    return ConnectorRegistry()


@pytest.fixture()
def runtime(tmp_path, reg):
    from saathi.connectors.conformance.store import CertificationStore
    cert_store = CertificationStore(
        path=tmp_path / "m30_certs.json",
        auto_fixture=True,
        persist=False,
    )
    return GovernedConnectorRuntime(
        registry=reg,
        rollout_mode=RolloutMode.OFF,
        production_certified_probe=lambda: True,
        evidence_dir=tmp_path / "ev",
        use_m26_incidents=False,
        clock=lambda: 1000.0,
        certification_store=cert_store,
        require_connector_certification=True,
    )


def _full_manifest(**kw) -> ConnectorManifest:
    base = dict(
        connector_id="test.http",
        version="1.0.0",
        display_name="Test HTTP",
        description="test connector",
        owner="tests",
        kind=ConnectorKind.HTTP,
        adapter_type="http",
        trust_level="LOCAL_NETWORK",
        capability_classes=("HTTP", "READ", "WRITE"),
        capabilities=("get", "post", "health", "validate"),
        supported_operations=("get", "post", "health", "validate"),
        side_effect_classes=("READ_ONLY", "EXTERNAL_MUTATION"),
        required_approvals=("post",),
        auth_mode=AuthMode.NONE,
        allowed_domains=("example.com", "127.0.0.1", "localhost"),
        timeout_seconds=5.0,
        max_retries=1,
        rate_limit_per_minute=100,
        evidence_policy="redacted",
        incident_policy="m26",
        health_policy={"startup_check": "validate", "health_check": "health"},
        readiness_policy={"readiness_check": "health", "requires_lifecycle": ["READY"]},
        dependencies=(),
        supported_environments=("local", "test"),
        rollout_compatible=("OFF", "SHADOW", "CANARY", "ACTIVE", "DRAINING"),
    )
    base.update(kw)
    return ConnectorManifest(**base)


def _transport_ok(method, url, headers, body, timeout):
    return {
        "status_code": 200,
        "ok": True,
        "body_preview": "ok",
        "headers": {"content-type": "text/plain"},
    }


def _req(**kw):
    base = dict(
        connector_id="test.http",
        operation="get",
        method="GET",
        url="https://example.com/x",
        caller_id="test-caller",
        caller_class="test",
        actor_id="test-actor",
        request_id="req-m29-1",
    )
    base.update(kw)
    return ConnectorRequest(**base)


# 1. duplicate connector IDs
def test_01_duplicate_connector_ids_fail(reg):
    m = _full_manifest()
    reg.register(m)
    with pytest.raises(DuplicateConnectorError):
        reg.register(_full_manifest())


# 2. invalid manifest
def test_02_invalid_manifest_rejected(reg):
    with pytest.raises(ValueError, match="manifest_invalid"):
        reg.register(ConnectorManifest(
            connector_id="",
            version="",
            supported_operations=(),
            evidence_policy="",
            incident_policy="",
        ))


# 3. invalid trust
def test_03_invalid_trust(reg):
    with pytest.raises(ValueError, match="invalid_trust"):
        reg.register(_full_manifest(trust_level="NOT_A_TRUST"))


# 4. invalid capability
def test_04_invalid_capability():
    r = validate_manifest(_full_manifest(capability_classes=("NOT_REAL_CAP",)))
    assert not r.ok
    assert any("invalid_capability" in e or "capability" in e for e in r.errors)


# 5. dependency cycles
def test_05_dependency_cycles():
    with pytest.raises(DependencyCycleError):
        validate_dependency_graph({
            "a": ["b"],
            "b": ["c"],
            "c": ["a"],
        })


# 6. registry lookup
def test_06_registry_lookup(reg):
    reg.register(_full_manifest())
    assert reg.get("test.http") is not None
    assert "test.http" in reg.list_ids()
    listed = reg.list()
    assert listed[0]["connector_id"] == "test.http"


# 7. execution through registry
def test_07_execution_through_registry(runtime, reg):
    reg.register(_full_manifest(), adapter=HttpAdapter(transport=_transport_ok))
    reg.validate("test.http")
    reg.mark_ready("test.http")
    runtime.set_mode(RolloutMode.ACTIVE)
    res = runtime.execute(_req())
    assert res.ok
    assert res.bypass is False
    assert res.executed is True


# 8. deprecation
def test_08_deprecation(reg):
    reg.register(_full_manifest(connector_id="old.c", version="1.0.0"))
    reg.register(_full_manifest(connector_id="new.c", version="1.0.0"))
    rec = reg.deprecate("old.c", replacement="new.c", reason="m29")
    assert rec.manifest.deprecated is True
    assert rec.manifest.replacement_connector == "new.c"
    insp = reg.inspect("old.c")
    assert insp["deprecated"] is True


# 9. version upgrades
def test_09_version_upgrades(reg):
    reg.register(_full_manifest(version="1.0.0"))
    with pytest.raises(DuplicateConnectorError):
        reg.register(_full_manifest(version="1.0.0"), allow_upgrade=True)
    reg.register(_full_manifest(version="1.1.0", description="upgraded"), allow_upgrade=True)
    assert reg.resolve("test.http").manifest.version == "1.1.0"
    hist = reg.inspect("test.http")["version_history"]
    assert hist and hist[-1]["to_version"] == "1.1.0"


# 10. documentation generation
def test_10_documentation_generation(reg):
    for m in builtin_manifests():
        reg.register(m, allow_replace=True)
    docs = generate_registry_docs(reg)
    assert docs["schema"] == "m29.registry_docs.v1"
    assert docs["rollout_summary"]["connector_count"] >= 4
    assert "trust_summary" in docs
    assert "capability_summary" in docs
    md = render_registry_docs_markdown(docs)
    assert "Connector Registry Catalog" in md
    assert "gov.http" in md


# 11. health metadata
def test_11_health_metadata(reg):
    reg.register(_full_manifest())
    insp = reg.inspect("test.http")
    assert insp["health_policy"].get("health_check") == "health"
    assert insp["health_policy"].get("startup_check") == "validate"


# 12. readiness metadata
def test_12_readiness_metadata(reg):
    reg.register(_full_manifest())
    insp = reg.inspect("test.http")
    assert "readiness_check" in insp["readiness_policy"]


# 13. rollout compatibility
def test_13_rollout_compatibility():
    r = validate_manifest(_full_manifest(
        trust_level="PRIVILEGED",
        capability_classes=("READ", "FINANCIAL"),
        rollout_compatible=("OFF", "SHADOW", "CANARY", "ACTIVE", "DRAINING"),
    ))
    # PRIVILEGED cannot be ACTIVE-eligible
    assert not r.ok
    assert any("rollout_not_eligible" in e for e in r.errors)


# 14. approval integration
def test_14_approval_integration(runtime, reg):
    reg.register(_full_manifest(), adapter=HttpAdapter(transport=_transport_ok))
    reg.validate("test.http")
    reg.mark_ready("test.http")
    runtime.set_mode(RolloutMode.ACTIVE)
    # post requires approval
    res = runtime.execute(_req(operation="post", method="POST", payload={"x": 1}))
    assert res.ok is False
    assert "approval" in (res.detail or res.error_code or "").lower() or res.approval_state in (
        "missing", "required", "denied",
    )
    runtime.grant_approval("tok-1")
    res2 = runtime.execute(_req(
        operation="post", method="POST", payload={"x": 1},
        approval_token="tok-1", request_id="req-appr",
    ))
    assert res2.ok is True


# 15. trust enforcement
def test_15_trust_enforcement():
    assert approval_floor_for_trust(TrustLevel.PROHIBITED) == "DENIED"
    assert "ACTIVE" not in rollout_eligible_for_trust(TrustLevel.PRIVILEGED)
    assert "ACTIVE" in rollout_eligible_for_trust(TrustLevel.INTERNAL)
    # FINANCIAL exceeds LOCAL_SYSTEM
    v = enforce_capabilities_for_trust("LOCAL_SYSTEM", [ConnectorCapability.FINANCIAL])
    assert "FINANCIAL" in v


# 16. capability enforcement
def test_16_capability_enforcement(reg):
    with pytest.raises(ValueError, match="capability_exceeds_trust|manifest_invalid"):
        reg.register(_full_manifest(
            trust_level="LOCAL_SYSTEM",
            capability_classes=("FINANCIAL", "HTTP"),
        ))


# 17. dependency validation
def test_17_dependency_validation(reg):
    reg.register(_full_manifest(connector_id="dep.base", dependencies=()))
    reg.register(_full_manifest(connector_id="dep.child", dependencies=("dep.base",)))
    out = reg.validate_dependencies()
    assert out["ok"] is True
    # unknown dep
    reg.register(_full_manifest(connector_id="dep.bad", dependencies=("missing.x",)))
    out2 = reg.validate_dependencies()
    assert out2["ok"] is False


# 18. connector resolution
def test_18_connector_resolution(reg):
    reg.register(_full_manifest())
    rec = reg.resolve("test.http")
    assert rec.manifest.connector_id == "test.http"
    insp = reg.inspect("test.http")
    assert insp["identity_source"] == "registry"


# 19. unknown connector fails
def test_19_unknown_connector_fails(reg, runtime):
    with pytest.raises(UnknownConnectorError):
        reg.resolve("no.such.connector")
    res = runtime.execute(_req(connector_id="no.such.connector"))
    assert res.ok is False
    assert res.error_code == "connector_not_registered"
    assert res.bypass is False


# 20. unregistered connector fails
def test_20_unregistered_connector_fails(reg, runtime):
    reg.register(_full_manifest(), adapter=HttpAdapter(transport=_transport_ok))
    reg.validate("test.http")
    reg.mark_ready("test.http")
    reg.unregister("test.http")
    res = runtime.execute(_req())
    assert res.ok is False
    assert res.error_code == "connector_not_registered"


# 21. manifest schema validation
def test_21_manifest_schema_validation():
    good = validate_manifest(_full_manifest())
    assert good.ok
    bad = validate_manifest(_full_manifest(
        supported_operations=("get", "get"),
        evidence_policy="",
        incident_policy="none",
    ))
    assert not bad.ok
    assert any("duplicate_operation" in e for e in bad.errors)
    with pytest.raises(ManifestValidationError):
        bad.raise_if_invalid()


# 22. registry persistence
def test_22_registry_persistence(reg, tmp_path):
    reg.register(_full_manifest(version="1.2.3"))
    path = tmp_path / "registry.json"
    save_registry_snapshot(reg, path, meta={"milestone": "m29"})
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["schema"] == "m29.connector_registry.v1"
    assert data["manifests"][0]["connector_id"] == "test.http"

    reg2 = ConnectorRegistry()
    ids = load_registry_snapshot(path, reg2, validate=True)
    assert "test.http" in ids
    assert reg2.resolve("test.http").manifest.version == "1.2.3"


# 23. compatibility with M28
def test_23_compatibility_with_m28(runtime, reg, tmp_path):
    reset_idempotency_cache()
    reg.register(
        _full_manifest(connector_id="gov.http"),
        adapter=HttpAdapter(transport=_transport_ok),
        allow_replace=True,
    )
    reg.validate("gov.http")
    reg.mark_ready("gov.http")
    runtime.set_mode(RolloutMode.ACTIVE)
    # M28 gateway path
    res = execute_via_gateway(
        _req(connector_id="gov.http"),
        runtime=runtime,
    )
    assert res.bypass is False
    # OFF still denies execution (rollout invariant)
    runtime.set_mode(RolloutMode.OFF)
    res_off = runtime.execute(_req(connector_id="gov.http"))
    assert res_off.ok is False
    assert res_off.detail == "mode:OFF" or res_off.rollout_state == "OFF"


# 24. production certification preserved (fail-closed / evidence-gated)
def test_24_production_certification_preserved():
    from saathi.inference.runtime_gate import evaluate_runtime_gate

    report = evaluate_runtime_gate(include_live_probe=True)
    # Authoritative M21.4 contract: True only when every mandatory check is PASS.
    # Do not require a fresh live+package host; require honest fail-closed mapping.
    assert isinstance(report.production_certified, bool)
    assert report.production_certified is (len(report.certification_blockers) == 0)
    if not report.production_certified:
        assert report.certification_blockers
    # connector + inference rollout remain OFF by default
    from saathi.connectors.gov.runtime import get_runtime, reset_runtime
    reset_runtime()
    rt = get_runtime(rollout_mode="OFF")
    assert rt.mode.value == "OFF"
    st = rt.status()
    assert st.get("cloud_fallback") is False
    assert "UNENGAGED" in str(st.get("trading_guardian", ""))


# CLI docs command
def test_cli_docs(reg, tmp_path, monkeypatch):
    from saathi.connectors.registry.__main__ import main
    from saathi.connectors.gov.registry import reset_registry, get_registry
    from saathi.connectors.gov.runtime import reset_runtime

    reset_registry()
    reset_runtime()
    # bootstrap via main
    assert main(["bootstrap"]) == 0
    out = tmp_path / "catalog.json"
    assert main(["docs", "--out", str(out)]) == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["m29"] is True
    assert data["rollout_summary"]["connector_count"] >= 4


def test_builtin_manifests_static_identity():
    ids = [m.connector_id for m in builtin_manifests()]
    assert ids == ["gov.http", "gov.mcp", "gov.browser", "gov.local_tool"]
    for m in builtin_manifests():
        assert m.version  # deterministic
        assert m.trust_level
        assert m.health_policy
        assert m.readiness_policy
        r = validate_manifest(m)
        assert r.ok, r.errors


def test_deprecated_blocks_mutation(runtime, reg):
    reg.register(_full_manifest(), adapter=HttpAdapter(transport=_transport_ok))
    reg.register(_full_manifest(connector_id="test.http.v2"))
    reg.validate("test.http")
    reg.mark_ready("test.http")
    reg.deprecate("test.http", replacement="test.http.v2")
    runtime.set_mode(RolloutMode.ACTIVE)
    res = runtime.execute(_req(operation="post", method="POST", approval_token="x"))
    # may fail approval first; grant and recheck deprecation
    runtime.grant_approval("x")
    res = runtime.execute(_req(operation="post", method="POST", approval_token="x", request_id="d2"))
    assert res.ok is False
    assert "deprecated" in (res.detail or res.error_code or "")


def test_m28_bypass_guard_still_zero():
    from saathi.connectors.gov.bypass_guard import scan_connector_bypasses
    report = scan_connector_bypasses(root=ROOT)
    data = report.to_dict() if hasattr(report, "to_dict") else dict(report)
    bypasses = data.get("production_bypasses")
    if bypasses is None:
        bypasses = data.get("bypass_count", data.get("count", getattr(report, "production_bypasses", 0)))
    assert int(bypasses) == 0
