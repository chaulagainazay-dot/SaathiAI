"""M18.3 — Governed read-only InsForge provider pilot."""
from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from saathi.providers.insforge import InsForgeProvider, load_config
from saathi.providers.insforge.client import InsForgeClient
from saathi.providers.insforge.config import (
    ALLOWED_PATHS,
    ENV_ALLOW_LOOPBACK,
    ENV_API_KEY,
    ENV_BASE_URL,
    ENV_ENABLED,
    ENV_MAX_BYTES,
    ENV_TIMEOUT,
    validate_base_url,
    is_path_allowed,
    is_path_blocked,
)
from saathi.providers.insforge.errors import InsForgeError, InsForgeErrorCategory
from saathi.providers.insforge.provider import WRITE_DENYLIST, CAPS, PILOT_STATUS
from saathi.providers.insforge.config import InsForgeConfig

ROOT = Path(__file__).resolve().parents[1]


def _cfg(**over) -> InsForgeConfig:
    base = dict(
        enabled=True,
        base_url="http://127.0.0.1:7130",
        api_key="ik_test_key_not_a_real_secret_xxx",
        timeout_sec=5.0,
        max_response_bytes=50_000,
        max_log_records=20,
        tls_verify=True,
        allow_loopback=True,
    )
    base.update(over)
    return InsForgeConfig(**base)


def _transport(handler):
    return httpx.MockTransport(handler)


def _json_response(data, status=200):
    body = json.dumps(data).encode()
    return httpx.Response(status, content=body, headers={"content-type": "application/json"})


# ── configuration ───────────────────────────────────────────────────────────


def test_01_disabled_by_default():
    c = load_config(env={})
    assert c.enabled is False
    p = InsForgeProvider(config=c, audit=False)
    r = p.health()
    assert r.ok is False
    assert r.error_category == InsForgeErrorCategory.PROVIDER_DISABLED.value


def test_02_missing_url_fails_closed():
    c = _cfg(base_url="")
    p = InsForgeProvider(config=c, audit=False)
    r = p.health()
    assert r.ok is False
    assert r.error_category == InsForgeErrorCategory.CONFIGURATION_INVALID.value


def test_03_invalid_scheme_rejected():
    ok, reason = validate_base_url("file:///etc/passwd", allow_loopback=True)
    assert ok is False
    assert "scheme" in reason
    ok2, _ = validate_base_url("ftp://example.com", allow_loopback=True)
    assert ok2 is False


def test_04_credentials_never_in_output():
    secret = "ik_super_secret_credential_value_12345"
    c = _cfg(api_key=secret)
    assert secret not in str(c.public_dict())
    assert c.public_dict()["has_api_key"] is True

    def handler(request: httpx.Request) -> httpx.Response:
        return _json_response({"status": "ok", "version": "2.2.6", "service": "Insforge"})

    p = InsForgeProvider(config=c, transport=_transport(handler), audit=False)
    r = p.health()
    blob = json.dumps(r.to_dict())
    assert secret not in blob
    assert "super_secret" not in blob


# ── endpoint governance ─────────────────────────────────────────────────────


def test_05_only_allowlisted_paths():
    assert is_path_allowed("/api/health")
    assert is_path_allowed("/api/database/tables")
    assert not is_path_allowed("/api/secrets")
    assert not is_path_allowed("/api/memory")
    assert is_path_blocked("/api/secrets")
    # migrations not on GET allowlist (POST only under writes gate in M18.4)
    assert not is_path_allowed("/api/database/migrations")


def test_06_arbitrary_path_rejected():
    c = _cfg()
    client = InsForgeClient(c, transport=_transport(lambda r: _json_response({})))
    with pytest.raises(InsForgeError) as ei:
        client.get_json("/api/admin/evil")
    assert ei.value.category == InsForgeErrorCategory.SECURITY_POLICY_DENIED


def test_07_write_methods_rejected_via_invoke():
    p = InsForgeProvider(config=_cfg(), audit=False)
    for op in ("migrate", "deploy_function", "create_secret", "place_order", "write_memory"):
        r = p.invoke(op)
        assert r.ok is False
        assert r.error_category in (
            InsForgeErrorCategory.WRITE_FORBIDDEN.value,
            InsForgeErrorCategory.UNSUPPORTED_OPERATION.value,
        )


def test_08_no_redirect_follow():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "http://evil.example/steal"})

    c = _cfg()
    client = InsForgeClient(c, transport=_transport(handler))
    # follow_redirects=False → client returns 3xx as error path via status handling
    with pytest.raises(InsForgeError):
        client.get_json("/api/health")


def test_09_timeout_config_bounded():
    c = load_config(env={ENV_TIMEOUT: "999"})
    assert c.timeout_sec <= 30.0
    c2 = load_config(env={ENV_TIMEOUT: "0.1"})
    assert c2.timeout_sec >= 1.0


def test_10_response_size_limit():
    big = b"x" * 100_000

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=big)

    c = _cfg(max_response_bytes=1000)
    client = InsForgeClient(c, transport=_transport(handler))
    with pytest.raises(InsForgeError) as ei:
        client.get_json("/api/health")
    assert ei.value.category == InsForgeErrorCategory.RESPONSE_TOO_LARGE


# ── payloads ────────────────────────────────────────────────────────────────


def test_11_valid_health():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/api/health")
        assert request.method == "GET"
        return _json_response({"status": "ok", "version": "2.2.6", "service": "Insforge OSS Backend"})

    p = InsForgeProvider(config=_cfg(), transport=_transport(handler), audit=False)
    r = p.health()
    assert r.ok is True
    assert r.data["reachable"] is True
    assert r.data["version"] == "2.2.6"
    assert r.data["writes_enabled"] is False
    assert r.data["pilot_status"] == PILOT_STATUS


def test_12_invalid_health_shape():
    def handler(request: httpx.Request) -> httpx.Response:
        return _json_response([1, 2, 3])

    p = InsForgeProvider(config=_cfg(), transport=_transport(handler), audit=False)
    r = p.health()
    assert r.ok is False
    assert r.error_category == InsForgeErrorCategory.INVALID_PROVIDER_RESPONSE.value


def test_13_schema_metadata():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/tables"):
            return _json_response({"tables": [{"name": "users"}, {"name": "orders"}]})
        return _json_response({"status": "ok"})

    p = InsForgeProvider(config=_cfg(), transport=_transport(handler), audit=False)
    r = p.list_schema_objects()
    assert r.ok and r.data["count"] == 2
    assert "users" in r.data["tables"]


def test_14_malformed_schema():
    def handler(request: httpx.Request) -> httpx.Response:
        return _json_response("not-json-object-list")

    p = InsForgeProvider(config=_cfg(), transport=_transport(handler), audit=False)
    r = p.list_schema_objects()
    # string body becomes empty list via _as_list — still ok structured
    assert r.ok is True
    assert r.data["count"] == 0


def test_15_functions_and_buckets():
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/functions"):
            return _json_response({"functions": [{"slug": "hello", "status": "active"}]})
        if path.endswith("/buckets"):
            return _json_response({"buckets": [{"name": "media", "public": False}]})
        return _json_response({"status": "ok"})

    p = InsForgeProvider(config=_cfg(), transport=_transport(handler), audit=False)
    rf = p.list_edge_functions()
    rb = p.list_storage_buckets()
    assert rf.ok and rf.data["functions"][0]["slug"] == "hello"
    assert rb.ok and rb.data["buckets"][0]["name"] == "media"


def test_16_log_sanitization():
    def handler(request: httpx.Request) -> httpx.Response:
        return _json_response({
            "logs": [
                {"message": "ok", "password": "hunter2secretxx", "level": "info"},
                {"message": "Bearer sk-abcdefghijklmnopqrstuvwxyz0123"},
            ],
        })

    p = InsForgeProvider(config=_cfg(), transport=_transport(handler), audit=False)
    r = p.read_sanitized_logs()
    assert r.ok
    blob = json.dumps(r.data)
    assert "hunter2" not in blob
    assert "sk-abcdef" not in blob or "***" in blob
    assert r.data["sanitized"] is True


def test_17_malformed_json_body():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not-json{{{")

    p = InsForgeProvider(config=_cfg(), transport=_transport(handler), audit=False)
    r = p.health()
    assert r.ok is False
    assert r.error_category == InsForgeErrorCategory.INVALID_PROVIDER_RESPONSE.value


# ── errors ──────────────────────────────────────────────────────────────────


def test_18_auth_failure_mapping():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, content=b'{"error":"unauthorized"}')

    p = InsForgeProvider(config=_cfg(), transport=_transport(handler), audit=False)
    r = p.health()
    assert r.error_category == InsForgeErrorCategory.AUTHENTICATION_FAILED.value


def test_19_permission_failure_mapping():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, content=b'{"error":"forbidden"}')

    p = InsForgeProvider(config=_cfg(), transport=_transport(handler), audit=False)
    r = p.get_provider_metadata()
    assert r.error_category == InsForgeErrorCategory.PERMISSION_DENIED.value


def test_20_secret_not_in_error_detail():
    secret = "ik_must_not_leak_in_errors_abcdef"
    c = _cfg(api_key=secret)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, content=b"fail")

    p = InsForgeProvider(config=c, transport=_transport(handler), audit=False)
    r = p.health()
    assert secret not in r.detail
    assert secret not in json.dumps(r.to_dict())


# ── integration / isolation ─────────────────────────────────────────────────


def test_21_audit_emitted_on_success():
    def handler(request: httpx.Request) -> httpx.Response:
        return _json_response({"status": "ok", "version": "1"})

    p = InsForgeProvider(config=_cfg(), transport=_transport(handler), audit=True)
    r = p.health()
    assert r.ok
    assert p.recent_audit()
    assert p.recent_audit()[-1]["operation"] == "health"
    assert p.recent_audit()[-1]["ok"] is True


def test_22_disabled_blocks_all_ops():
    c = _cfg(enabled=False)

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("network must not be called when disabled")

    p = InsForgeProvider(config=c, transport=_transport(handler), audit=False)
    for op in CAPS:
        r = p.invoke(op)
        assert r.ok is False
        assert r.error_category == InsForgeErrorCategory.PROVIDER_DISABLED.value


def test_23_trading_guardian_isolation():
    """Adapter must not implement trading execution or depend on TG."""
    pkg = ROOT / "saathi" / "providers" / "insforge"
    for path in pkg.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        # no trading module imports
        assert "saathi.trade" not in text
        assert "trade_journal" not in text
        assert "from saathi.execution.trade" not in text
        low = text.lower()
        for banned in ("binance", "alpaca", "exchange_execution", "broker_api"):
            assert banned not in low, f"{path.name} contains {banned}"
    # cannot invoke trading ops through provider
    p = InsForgeProvider(config=_cfg(enabled=True, base_url="http://127.0.0.1:7130",
                                      allow_loopback=True), audit=False)
    r = p.invoke("place_order", symbol="BTC")
    assert r.ok is False
    assert r.error_category in (
        InsForgeErrorCategory.WRITE_FORBIDDEN.value,
        InsForgeErrorCategory.UNSUPPORTED_OPERATION.value,
    )
    assert "place_order" in WRITE_DENYLIST
    assert "trade" in WRITE_DENYLIST


def test_24_no_mcp_passthrough():
    p = InsForgeProvider(config=_cfg(), audit=False)
    r = p.invoke("mcp_invoke", tool="run_sql")
    assert r.ok is False


def test_25_loopback_denied_without_flag():
    ok, reason = validate_base_url("http://127.0.0.1:7130", allow_loopback=False)
    assert ok is False
    assert "loopback" in reason


def test_26_blocked_path_migrations():
    c = _cfg()
    client = InsForgeClient(c, transport=_transport(lambda r: _json_response({})))
    with pytest.raises(InsForgeError) as ei:
        client.get_json("/api/database/migrations")
    assert ei.value.category == InsForgeErrorCategory.SECURITY_POLICY_DENIED


def test_27_docs_register_insforge():
    ext = (ROOT / "docs" / "EXTERNAL_CAPABILITY_STATUS.md").read_text(encoding="utf-8")
    assert "InsForge" in ext or "insforge" in ext.lower()
    bound = ROOT / "docs" / "M18_3_INSFORGE_PROVIDER_BOUNDARY.md"
    assert bound.is_file()
    text = bound.read_text(encoding="utf-8")
    assert "PILOT_APPROVED_READ_ONLY" in text or "read-only" in text.lower()
    assert "Trading Guardian" in text
    assert "ExecutionGateway" in text or "Execution Gateway" in text


def test_28_allowlist_is_get_only_set():
    # all allowed paths under /api/
    for p in ALLOWED_PATHS:
        assert p.startswith("/api/")
        assert "migration" not in p
        assert "secret" not in p
        assert "memory" not in p
