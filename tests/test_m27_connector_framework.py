"""M27 — Governed connector framework tests."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from saathi.connectors.gov.adapters.http import HttpAdapter
from saathi.connectors.gov.adapters.local_tool import LocalToolAdapter
from saathi.connectors.gov.adapters.mcp import McpAdapter
from saathi.connectors.gov.adapters.browser import BrowserAdapter
from saathi.connectors.gov.auth import resolve_auth
from saathi.connectors.gov.models import (
    AuthMode,
    ConnectorKind,
    ConnectorLifecycle,
    ConnectorManifest,
    ConnectorRequest,
    VALID_LIFECYCLE_TRANSITIONS,
)
from saathi.connectors.gov.policy import ConnectorPolicy
from saathi.connectors.gov.redaction import redact_payload
from saathi.connectors.gov.registry import (
    ConnectorRegistry,
    IllegalLifecycleTransition,
)
from saathi.connectors.gov.runtime import GovernedConnectorRuntime
from saathi.inference.ops.models import RolloutMode

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def reg():
    return ConnectorRegistry()


@pytest.fixture()
def runtime(tmp_path, reg):
    return GovernedConnectorRuntime(
        registry=reg,
        rollout_mode=RolloutMode.OFF,
        production_certified_probe=lambda: True,
        evidence_dir=tmp_path / "ev",
        use_m26_incidents=False,
        clock=lambda: 1000.0,
    )


def _http_manifest(**kw):
    base = dict(
        connector_id="gov.http",
        kind=ConnectorKind.HTTP,
        capabilities=("get", "post", "put", "patch", "delete", "health", "validate", "http_request"),
        supported_operations=("get", "post", "put", "patch", "delete", "health", "validate", "http_request"),
        allowed_domains=("127.0.0.1", "localhost", "example.com"),
        timeout_seconds=5.0,
        max_retries=1,
        rate_limit_per_minute=100,
    )
    base.update(kw)
    return ConnectorManifest(**base)


def _transport_ok(method, url, headers, body, timeout):
    return {"status_code": 200, "ok": True, "body_preview": "ok", "headers": {"content-type": "text/plain"}}


def _transport_timeout(method, url, headers, body, timeout):
    raise TimeoutError("timeout")


# ── Lifecycle ──────────────────────────────────────────────────────────────


def test_lifecycle_register_validate_ready(reg):
    m = _http_manifest()
    reg.register(m, adapter=HttpAdapter(transport=_transport_ok))
    assert reg.get("gov.http").lifecycle is ConnectorLifecycle.REGISTERED
    assert reg.validate("gov.http")["ok"]
    assert reg.get("gov.http").lifecycle is ConnectorLifecycle.VALIDATED
    reg.mark_ready("gov.http")
    assert reg.get("gov.http").lifecycle is ConnectorLifecycle.READY


def test_lifecycle_transitions_deterministic():
    for src, dests in VALID_LIFECYCLE_TRANSITIONS.items():
        assert src in ConnectorLifecycle
        for d in dests:
            assert d in ConnectorLifecycle


def test_illegal_transition_raises(reg):
    reg.register(_http_manifest(), adapter=HttpAdapter(transport=_transport_ok))
    with pytest.raises(IllegalLifecycleTransition):
        reg.transition("gov.http", ConnectorLifecycle.READY)


def test_disable_and_recover(reg):
    reg.register(_http_manifest(), adapter=HttpAdapter(transport=_transport_ok))
    reg.validate("gov.http")
    reg.mark_ready("gov.http")
    reg.disable("gov.http")
    assert reg.get("gov.http").lifecycle is ConnectorLifecycle.DISABLED
    reg.recover("gov.http")
    assert reg.get("gov.http").lifecycle is ConnectorLifecycle.READY


# ── Validation / policy ────────────────────────────────────────────────────


def test_policy_denies_secret_payload():
    pol = ConnectorPolicy()
    m = _http_manifest()
    req = ConnectorRequest(connector_id="gov.http", operation="get", payload={"api_key": "sk-x"})
    d = pol.evaluate(m, req)
    assert d.allowed is False
    assert "forbidden_payload" in d.reason or "secret" in d.reason


def test_policy_domain_allowlist():
    pol = ConnectorPolicy()
    m = _http_manifest(allowed_domains=("example.com",))
    req = ConnectorRequest(
        connector_id="gov.http", operation="get", url="https://evil.example.org/x"
    )
    d = pol.evaluate(m, req)
    assert d.allowed is False


def test_policy_https_required_for_remote():
    pol = ConnectorPolicy()
    m = _http_manifest(allowed_domains=("example.com",))
    req = ConnectorRequest(
        connector_id="gov.http", operation="get", url="http://example.com/x"
    )
    d = pol.evaluate(m, req)
    assert d.allowed is False
    assert "http" in d.reason or "https" in d.reason


def test_auth_env_var_presence(monkeypatch):
    m = _http_manifest(auth_mode=AuthMode.ENV_VAR, auth_env_names=("SAATHI_TEST_CONN_KEY",))
    monkeypatch.delenv("SAATHI_TEST_CONN_KEY", raising=False)
    r = resolve_auth(m, environ={})
    assert r.ok is False
    r2 = resolve_auth(m, environ={"SAATHI_TEST_CONN_KEY": "secret-value"})
    assert r2.ok is True
    assert "secret-value" not in str(r2.to_public_dict())


# ── Rollout ────────────────────────────────────────────────────────────────


def test_default_mode_off_blocks(runtime, reg):
    reg.register(_http_manifest(), adapter=HttpAdapter(transport=_transport_ok))
    reg.validate("gov.http")
    reg.mark_ready("gov.http")
    res = runtime.execute(ConnectorRequest(connector_id="gov.http", operation="health"))
    assert res.ok is False
    assert "OFF" in res.detail


def test_shadow_no_side_effect(runtime, reg):
    reg.register(_http_manifest(), adapter=HttpAdapter(transport=_transport_ok))
    reg.validate("gov.http")
    reg.mark_ready("gov.http")
    runtime.set_mode(RolloutMode.SHADOW)
    res = runtime.execute(ConnectorRequest(
        connector_id="gov.http", operation="post", method="POST",
        url="https://example.com/x", payload={"a": 1},
    ))
    assert res.status == "shadow"
    assert res.data.get("shadow") is True


def test_active_requires_certification(tmp_path, reg):
    rt = GovernedConnectorRuntime(
        registry=reg,
        rollout_mode=RolloutMode.OFF,
        production_certified_probe=lambda: False,
        evidence_dir=tmp_path / "ev",
        use_m26_incidents=False,
    )
    out = rt.set_mode(RolloutMode.ACTIVE)
    assert out["ok"] is False
    assert "production_certification" in out["error"]


def test_active_executes_when_ready(runtime, reg):
    reg.register(_http_manifest(), adapter=HttpAdapter(transport=_transport_ok))
    reg.validate("gov.http")
    reg.mark_ready("gov.http")
    assert runtime.set_mode(RolloutMode.ACTIVE)["ok"]
    res = runtime.execute(ConnectorRequest(
        connector_id="gov.http",
        operation="get",
        method="GET",
        url="https://example.com/health",
    ))
    assert res.ok is True
    assert res.bypass is False
    assert res.privacy_safe is True


def test_draining_blocks(runtime, reg):
    reg.register(_http_manifest(), adapter=HttpAdapter(transport=_transport_ok))
    reg.validate("gov.http")
    reg.mark_ready("gov.http")
    runtime.set_mode(RolloutMode.ACTIVE)
    reg.drain("gov.http")
    res = runtime.execute(ConnectorRequest(connector_id="gov.http", operation="health"))
    assert res.ok is False
    assert res.status in ("draining", "denied")


# ── HTTP adapter ───────────────────────────────────────────────────────────


def test_http_methods(runtime, reg):
    reg.register(_http_manifest(), adapter=HttpAdapter(transport=_transport_ok))
    reg.validate("gov.http")
    reg.mark_ready("gov.http")
    runtime.set_mode(RolloutMode.ACTIVE)
    for method in ("GET", "POST", "PUT", "PATCH", "DELETE"):
        token = f"tok-{method}"
        runtime.grant_approval(token)
        res = runtime.execute(ConnectorRequest(
            connector_id="gov.http",
            operation=method.lower(),
            method=method,
            url="https://example.com/r",
            payload={"x": 1} if method != "GET" else {},
            approval_token=token if method != "GET" else "",
        ))
        assert res.ok is True, (method, res.detail)


def test_http_timeout_incident(runtime, reg):
    reg.register(_http_manifest(), adapter=HttpAdapter(transport=_transport_timeout))
    reg.validate("gov.http")
    reg.mark_ready("gov.http")
    runtime.set_mode(RolloutMode.ACTIVE)
    res = runtime.execute(ConnectorRequest(
        connector_id="gov.http",
        operation="get",
        method="GET",
        url="https://example.com/slow",
    ))
    assert res.ok is False
    assert res.status == "timeout"
    assert res.incident_id


def test_http_retries(runtime, reg):
    calls = {"n": 0}

    def flaky(method, url, headers, body, timeout):
        calls["n"] += 1
        if calls["n"] < 2:
            raise TimeoutError("t")
        return {"status_code": 200, "ok": True, "body_preview": "ok", "headers": {}}

    reg.register(
        _http_manifest(max_retries=2),
        adapter=HttpAdapter(transport=flaky),
    )
    reg.validate("gov.http")
    reg.mark_ready("gov.http")
    runtime.set_mode(RolloutMode.ACTIVE)
    res = runtime.execute(ConnectorRequest(
        connector_id="gov.http", operation="get", method="GET", url="https://example.com/r",
    ))
    assert res.ok is True
    assert res.attempts >= 2


# ── Approval ───────────────────────────────────────────────────────────────


def test_approval_required_for_post(runtime, reg):
    reg.register(_http_manifest(), adapter=HttpAdapter(transport=_transport_ok))
    reg.validate("gov.http")
    reg.mark_ready("gov.http")
    runtime.set_mode(RolloutMode.ACTIVE)
    res = runtime.execute(ConnectorRequest(
        connector_id="gov.http",
        operation="post",
        method="POST",
        url="https://example.com/x",
        payload={"a": 1},
    ))
    assert res.ok is False
    assert "approval" in res.detail


# ── MCP / browser / local ──────────────────────────────────────────────────


def test_mcp_adapter_health(runtime, reg):
    reg.register(
        ConnectorManifest(
            connector_id="gov.mcp",
            kind=ConnectorKind.MCP,
            capabilities=("health", "validate", "inventory"),
            supported_operations=("health", "validate", "inventory"),
        ),
        adapter=McpAdapter(),
    )
    reg.validate("gov.mcp")
    reg.mark_ready("gov.mcp")
    runtime.set_mode(RolloutMode.ACTIVE)
    res = runtime.execute(ConnectorRequest(connector_id="gov.mcp", operation="health"))
    assert res.ok is True
    assert res.bypass is False


def test_browser_reuse_policy(runtime, reg):
    reg.register(
        ConnectorManifest(
            connector_id="gov.browser",
            kind=ConnectorKind.BROWSER,
            capabilities=("health", "validate", "policy_check", "navigate"),
            supported_operations=("health", "validate", "policy_check", "navigate"),
        ),
        adapter=BrowserAdapter(),
    )
    reg.validate("gov.browser")
    reg.mark_ready("gov.browser")
    runtime.set_mode(RolloutMode.ACTIVE)
    res = runtime.execute(ConnectorRequest(connector_id="gov.browser", operation="health"))
    assert res.ok is True
    assert "browser" in (res.detail or "") or res.data


def test_local_tool_allowlist(runtime, reg):
    reg.register(
        ConnectorManifest(
            connector_id="gov.local_tool",
            kind=ConnectorKind.LOCAL_TOOL,
            capabilities=("echo_safe", "python_version", "health"),
            supported_operations=("echo_safe", "python_version", "health"),
        ),
        adapter=LocalToolAdapter(),
    )
    reg.validate("gov.local_tool")
    reg.mark_ready("gov.local_tool")
    runtime.set_mode(RolloutMode.ACTIVE)
    res = runtime.execute(ConnectorRequest(
        connector_id="gov.local_tool",
        operation="echo_safe",
        payload={"message": "hi"},
    ))
    assert res.ok is True
    assert res.data.get("message") == "hi"

    bad = runtime.execute(ConnectorRequest(
        connector_id="gov.local_tool",
        operation="rm_rf",
    ))
    assert bad.ok is False
    assert "allowlist" in bad.detail or "unsupported" in bad.detail


# ── Evidence / redaction / incidents ───────────────────────────────────────


def test_redaction_strips_secrets():
    p = redact_payload({"authorization": "Bearer x", "status": "ok", "token": "t"})
    assert "authorization" not in p
    assert "token" not in p
    assert p["status"] == "ok"
    assert p.get("privacy_safe") is True


def test_evidence_written(runtime, reg, tmp_path):
    reg.register(_http_manifest(), adapter=HttpAdapter(transport=_transport_ok))
    reg.validate("gov.http")
    reg.mark_ready("gov.http")
    runtime.set_mode(RolloutMode.ACTIVE)
    res = runtime.execute(ConnectorRequest(
        connector_id="gov.http", operation="get", method="GET", url="https://example.com/a",
    ))
    assert res.evidence_id
    files = list((tmp_path / "ev").glob("evidence_*.json"))
    assert files
    raw = files[0].read_text()
    assert "Bearer" not in raw
    assert "sk-" not in raw
    assert "privacy_safe" in raw


def test_incident_dedup(runtime, reg):
    reg.register(_http_manifest(), adapter=HttpAdapter(transport=_transport_timeout))
    reg.validate("gov.http")
    reg.mark_ready("gov.http")
    runtime.set_mode(RolloutMode.ACTIVE)
    a = runtime.execute(ConnectorRequest(
        connector_id="gov.http", operation="get", method="GET", url="https://example.com/t",
    ))
    b = runtime.execute(ConnectorRequest(
        connector_id="gov.http", operation="get", method="GET", url="https://example.com/t",
    ))
    assert a.incident_id
    assert a.incident_id == b.incident_id


# ── Registration / bootstrap ───────────────────────────────────────────────


def test_register_builtin_adapters(runtime):
    ids = runtime.register_builtin_adapters()
    assert "gov.http" in ids
    assert "gov.mcp" in ids
    assert "gov.browser" in ids
    assert "gov.local_tool" in ids
    for cid in ids:
        assert runtime.registry.get(cid).lifecycle is ConnectorLifecycle.READY


def test_connector_disable_event(runtime, reg):
    reg.register(_http_manifest(), adapter=HttpAdapter(transport=_transport_ok))
    reg.validate("gov.http")
    reg.mark_ready("gov.http")
    reg.disable("gov.http")
    runtime.set_mode(RolloutMode.ACTIVE)
    res = runtime.execute(ConnectorRequest(connector_id="gov.http", operation="health"))
    assert res.ok is False
    assert "DISABLED" in res.detail


def test_no_bypass_flag(runtime, reg):
    reg.register(_http_manifest(), adapter=HttpAdapter(transport=_transport_ok))
    reg.validate("gov.http")
    reg.mark_ready("gov.http")
    runtime.set_mode(RolloutMode.ACTIVE)
    res = runtime.execute(ConnectorRequest(
        connector_id="gov.http", operation="get", method="GET", url="https://example.com/",
    ))
    assert res.bypass is False


def test_trading_connector_forbidden(reg):
    with pytest.raises(ValueError):
        reg.register(ConnectorManifest(
            connector_id="evil.trade",
            trading=True,
            capabilities=("trade.execute",),
        ))


def test_cloud_live_blocked_by_policy():
    pol = ConnectorPolicy()
    m = ConnectorManifest(
        connector_id="cloud.x",
        cloud=True,
        capabilities=("fetch",),
        supported_operations=("fetch",),
    )
    d = pol.evaluate(m, ConnectorRequest(connector_id="cloud.x", operation="fetch"))
    assert d.allowed is False


def test_rate_limit(runtime, reg):
    reg.register(
        _http_manifest(rate_limit_per_minute=2),
        adapter=HttpAdapter(transport=_transport_ok),
    )
    reg.validate("gov.http")
    reg.mark_ready("gov.http")
    runtime.set_mode(RolloutMode.ACTIVE)
    # clock fixed at 1000 — all in same window
    r1 = runtime.execute(ConnectorRequest(
        connector_id="gov.http", operation="get", method="GET", url="https://example.com/1",
    ))
    r2 = runtime.execute(ConnectorRequest(
        connector_id="gov.http", operation="get", method="GET", url="https://example.com/2",
    ))
    r3 = runtime.execute(ConnectorRequest(
        connector_id="gov.http", operation="get", method="GET", url="https://example.com/3",
    ))
    assert r1.ok and r2.ok
    assert r3.ok is False
    assert "rate_limit" in r3.detail


def test_m25_cert_package_untouched(runtime):
    p = ROOT / "docs" / "evidence" / "m25" / "cert" / "full_suite_evidence.json"
    before = p.read_text() if p.is_file() else None
    runtime.register_builtin_adapters()
    after = p.read_text() if p.is_file() else None
    assert before == after


def test_trading_guardian_status_field(runtime):
    s = runtime.status()
    assert s["trading_guardian"] == "UNCHANGED_UNENGAGED"
    assert s["cloud_fallback"] is False


def test_canary_mode_allows_when_certified(runtime, reg):
    reg.register(_http_manifest(), adapter=HttpAdapter(transport=_transport_ok))
    reg.validate("gov.http")
    reg.mark_ready("gov.http")
    runtime.set_mode(RolloutMode.CANARY)
    res = runtime.execute(ConnectorRequest(
        connector_id="gov.http", operation="get", method="GET", url="https://example.com/c",
    ))
    assert res.ok is True
