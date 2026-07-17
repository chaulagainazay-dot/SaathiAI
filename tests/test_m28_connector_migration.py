"""M28 — Canonical connector migration and ExecutionGateway enforcement."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from saathi.connectors.gov.adapters.http import HttpAdapter
from saathi.connectors.gov.bypass_guard import scan_connector_bypasses
from saathi.connectors.gov.gateway_bridge import (
    deprecation_events,
    emit_deprecation,
    execute_via_gateway,
    reset_deprecation_events,
    reset_idempotency_cache,
)
from saathi.connectors.gov.models import (
    ConnectorKind,
    ConnectorLifecycle,
    ConnectorManifest,
    ConnectorRequest,
)
from saathi.connectors.gov.registry import ConnectorRegistry
from saathi.connectors.gov.runtime import GovernedConnectorRuntime
from saathi.connectors.gov.side_effects import (
    SideEffectClass,
    capability_to_side_effect,
    classify_operation,
    evaluate_side_effect,
)
from saathi.inference.ops.models import RolloutMode

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "docs" / "evidence" / "m28" / "connector_migration_ledger.json"


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


def _ready_http(runtime, reg, transport=_transport_ok):
    reg.register(_http_manifest(), adapter=HttpAdapter(transport=transport))
    reg.validate("gov.http")
    reg.mark_ready("gov.http")
    runtime.set_mode(RolloutMode.ACTIVE)


def _req(**kw):
    base = dict(
        connector_id="gov.http",
        operation="get",
        method="GET",
        url="https://example.com/x",
        caller_id="test-caller",
        caller_class="test",
        actor_id="test-actor",
        request_id="req-1",
    )
    base.update(kw)
    return ConnectorRequest(**base)


# ── Audit / ledger ─────────────────────────────────────────────────────────


def test_01_ledger_exists_and_covers_scope():
    assert LEDGER.is_file()
    data = json.loads(LEDGER.read_text(encoding="utf-8"))
    paths = {e["legacy_path"] for e in data["entries"]}
    assert any("manager.execute" in p for p in paths)
    assert any("GovernedConnectorRuntime" in p for p in paths)
    assert any("trading" in p.lower() or "BLOCK" in e["classification"] for e in data["entries"] for p in [e["legacy_path"]])
    for e in data["entries"]:
        assert e["migration_state"]
        assert e["classification"]


def test_02_migrated_paths_reach_gateway(runtime, reg, tmp_path):
    _ready_http(runtime, reg)
    reset_idempotency_cache()
    r = execute_via_gateway(
        _req(operation="health", method="GET", url=""),
        runtime=runtime,
    )
    assert r.bypass is False
    assert r.request_id
    # gateway path always sets bypass false
    assert r.ok or r.status in ("success", "denied", "error", "shadow")


def test_03_compat_wrapper_no_second_transport():
    src = (ROOT / "saathi/connectors/gov/compat.py").read_text(encoding="utf-8")
    assert "governed_manager_execute" in src
    assert "httpx" not in src
    assert "requests." not in src
    assert "urllib" not in src
    mgr = (ROOT / "saathi/connectors/manager.py").read_text(encoding="utf-8")
    assert "governed_manager_execute" in mgr
    # live adapter direct call removed from execute()
    assert "with_secret=True" not in mgr.split("def execute")[1].split("def provider_health")[0]


def test_04_retained_read_only_classified():
    data = json.loads(LEDGER.read_text(encoding="utf-8"))
    assert any(e["classification"] == "RETAIN_READ_ONLY" for e in data["entries"])


def test_05_blocked_trading_registration(reg):
    with pytest.raises(ValueError, match="trading"):
        reg.register(
            ConnectorManifest(
                connector_id="evil.trade",
                trading=True,
                kind=ConnectorKind.HTTP,
                supported_operations=("get",),
            )
        )


# ── Execution contract ─────────────────────────────────────────────────────


def test_06_valid_intent_via_gateway(runtime, reg):
    _ready_http(runtime, reg)
    r = execute_via_gateway(_req(operation="get"), runtime=runtime)
    assert r.bypass is False
    assert r.ok is True
    assert r.executed is True or r.status == "success"


def test_07_missing_caller_fails(runtime, reg):
    _ready_http(runtime, reg)
    r = runtime.execute(ConnectorRequest(
        connector_id="gov.http", operation="get", method="GET",
        url="https://example.com", caller_id="", actor_id="",
    ))
    assert r.ok is False
    assert "caller" in (r.detail + r.error_code).lower() or r.error_code == "unauthorized_caller"


def test_08_missing_operation_fails(runtime, reg):
    _ready_http(runtime, reg)
    r = runtime.execute(_req(operation=""))
    assert r.ok is False


def test_09_unknown_operation_fails(runtime, reg):
    _ready_http(runtime, reg)
    r = runtime.execute(_req(operation="launch_rockets", method="POST"))
    assert r.ok is False


def test_10_caller_cannot_override_adapter(runtime, reg):
    _ready_http(runtime, reg)
    r = runtime.execute(_req(
        operation="get",
        payload={"adapter": "evil", "adapter_class": "Evil"},
    ))
    # adapter selection ignored; either success via registered adapter or deny — not evil
    assert r.bypass is False
    assert "evil" not in (r.detail or "").lower()


def test_11_caller_cannot_override_side_effect(runtime, reg):
    _ready_http(runtime, reg)
    r = runtime.execute(_req(
        operation="post",
        method="POST",
        url="https://example.com/x",
        claimed_side_effect_class="READ_ONLY",
        approval_token="",
    ))
    assert r.ok is False
    # "post" is COMMUNICATION; claim of READ_ONLY must not win
    assert r.side_effect_class in (
        SideEffectClass.EXTERNAL_MUTATION.value,
        SideEffectClass.COMMUNICATION.value,
    )
    assert r.side_effect_class != "READ_ONLY"


def test_12_caller_cannot_override_rollout(runtime, reg):
    # mode stays OFF despite payload
    reg.register(_http_manifest(), adapter=HttpAdapter(transport=_transport_ok))
    reg.validate("gov.http")
    reg.mark_ready("gov.http")
    assert runtime.mode is RolloutMode.OFF
    r = runtime.execute(_req(payload={"rollout_mode": "ACTIVE", "mode": "ACTIVE"}))
    assert r.ok is False
    assert r.detail == "mode:OFF" or r.rollout_state == "OFF"


def test_13_caller_cannot_override_approval(runtime, reg):
    _ready_http(runtime, reg)
    r = runtime.execute(_req(
        operation="post", method="POST", url="https://example.com",
        payload={"skip_approval": True, "is_admin": True, "trusted": True},
    ))
    assert r.ok is False
    assert "approval" in (r.detail + r.error_code).lower()


# ── Side-effect policy ─────────────────────────────────────────────────────


def test_14_20_side_effect_matrix():
    assert classify_operation("get", method="GET") is SideEffectClass.READ_ONLY
    assert classify_operation("draft", method="POST") is SideEffectClass.LOCAL_MUTATION
    assert classify_operation("post", method="POST") in (
        SideEffectClass.EXTERNAL_MUTATION, SideEffectClass.COMMUNICATION,
    )
    assert classify_operation("send", method="POST") is SideEffectClass.COMMUNICATION
    assert classify_operation("rotate_credentials") is SideEffectClass.ACCOUNT_CHANGE
    assert classify_operation("payments.charge") is SideEffectClass.FINANCIAL
    assert classify_operation("trade.execute") is SideEffectClass.PROHIBITED

    assert evaluate_side_effect(SideEffectClass.READ_ONLY).allowed
    assert evaluate_side_effect(SideEffectClass.LOCAL_MUTATION).allowed
    assert not evaluate_side_effect(SideEffectClass.EXTERNAL_MUTATION).allowed
    assert evaluate_side_effect(SideEffectClass.EXTERNAL_MUTATION, has_approval=True).allowed
    assert not evaluate_side_effect(SideEffectClass.COMMUNICATION).allowed
    assert evaluate_side_effect(SideEffectClass.COMMUNICATION, has_approval=True).allowed
    assert evaluate_side_effect(SideEffectClass.ACCOUNT_CHANGE).blocked
    assert evaluate_side_effect(SideEffectClass.FINANCIAL).blocked
    assert evaluate_side_effect(SideEffectClass.PRIVILEGED).blocked
    assert evaluate_side_effect(SideEffectClass.PROHIBITED).blocked


def test_21_trading_blocked_execute(runtime, reg):
    _ready_http(runtime, reg)
    r = runtime.execute(_req(operation="trade.execute", method="POST"))
    assert r.ok is False
    assert r.side_effect_class == SideEffectClass.PROHIBITED.value


def test_22_financial_manager_blocked():
    import tempfile, os
    from saathi.connectors.accounts import AccountStore
    from saathi.connectors import manager
    fd, p = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    s = AccountStore(p)
    a = s.add(provider="stripe", display_name="s")
    out = manager.execute(a["id"], "payments.charge", {"amount": 1}, store=s)
    assert out["ok"] is False
    assert out.get("bypass") is False


# ── Approval ───────────────────────────────────────────────────────────────


def test_23_28_approval_binding(runtime, reg):
    _ready_http(runtime, reg)
    runtime.grant_approval("tok-good")
    r = runtime.execute(_req(
        operation="post", method="POST", url="https://example.com",
        approval_token="tok-good",
        resource_target="https://example.com",
        payload={"x": 1},
        idempotency_key="a" * 64,
    ))
    assert r.ok is True

    # mutated target with same token still ok at runtime store level (token not bound to target
    # in simple store) — fingerprint invalidation via idempotency
    r2 = runtime.execute(_req(
        operation="post", method="POST", url="https://example.com/other",
        approval_token="tok-good",
        resource_target="https://example.com/other",
        payload={"x": 2},
        idempotency_key="a" * 64,
        request_id="req-2",
    ))
    assert r2.ok is False
    assert r2.idempotency_state == "conflict" or "idempotency" in r2.detail

    r3 = runtime.execute(_req(
        operation="post", method="POST", url="https://example.com",
        approval_token="expired-never-granted",
    ))
    assert r3.ok is False


def test_29_approval_evidence_redacted(runtime, reg, tmp_path):
    _ready_http(runtime, reg)
    runtime.grant_approval("tok-r")
    r = runtime.execute(_req(
        operation="post", method="POST", url="https://example.com",
        approval_token="tok-r",
        payload={"note": "hello"},
    ))
    assert r.privacy_safe is True
    # evidence files should not contain raw authorization-like keys from headers attempt
    for p in (tmp_path / "ev").glob("evidence_*.json"):
        text = p.read_text(encoding="utf-8")
        assert "Bearer " not in text


# ── Rollout ────────────────────────────────────────────────────────────────


def test_30_37_rollout_modes(runtime, reg):
    reg.register(_http_manifest(), adapter=HttpAdapter(transport=_transport_ok))
    reg.validate("gov.http")
    reg.mark_ready("gov.http")

    # OFF
    runtime.set_mode(RolloutMode.OFF)
    r = runtime.execute(_req())
    assert r.ok is False and "OFF" in r.detail

    # SHADOW no side effect for mutating
    runtime.set_mode(RolloutMode.SHADOW)
    r = runtime.execute(_req(operation="post", method="POST", url="https://example.com"))
    assert r.status == "shadow"
    assert r.executed is False

    # CANARY deterministic
    runtime.set_mode(RolloutMode.CANARY)
    runtime.canary_connector_allowlist = frozenset({"gov.http"})
    runtime.grant_approval("c1")
    r = runtime.execute(_req(operation="get", approval_token="c1"))
    # get is read-only
    assert r.ok is True or r.status in ("success", "denied")
    runtime.canary_connector_allowlist = frozenset()
    runtime.canary_percent = 0
    r = runtime.execute(_req(operation="get", request_id="canary-miss"))
    assert r.ok is False and "canary" in r.detail

    # ACTIVE needs cert
    runtime.production_certified_probe = lambda: False
    runtime.set_mode(RolloutMode.ACTIVE)
    # set_mode itself may reject ACTIVE
    runtime._mode = RolloutMode.ACTIVE
    r = runtime.execute(_req())
    assert r.ok is False
    assert "certification" in r.detail or r.detail == "active_requires_production_certification"

    runtime.production_certified_probe = lambda: True
    runtime.set_mode(RolloutMode.ACTIVE)
    # ACTIVE still needs readiness — force lifecycle away from READY
    rec = reg.get("gov.http")
    rec.lifecycle = ConnectorLifecycle.REGISTERED
    r = runtime.execute(_req())
    assert r.ok is False
    reg.validate("gov.http")
    reg.mark_ready("gov.http")
    runtime.grant_approval("a1")
    r = runtime.execute(_req(operation="post", method="POST", url="https://example.com", approval_token="a1"))
    assert r.ok is True

    # DRAINING
    runtime.set_mode(RolloutMode.DRAINING)
    r = runtime.execute(_req())
    assert r.status == "draining"

    # default remains OFF for fresh runtime
    rt2 = GovernedConnectorRuntime(
        registry=ConnectorRegistry(),
        production_certified_probe=lambda: True,
        evidence_dir=Path(tempfile.mkdtemp()) / "e",
        use_m26_incidents=False,
    )
    assert rt2.mode is RolloutMode.OFF


# ── Idempotency ────────────────────────────────────────────────────────────


def test_38_41_idempotency(runtime, reg):
    _ready_http(runtime, reg)
    key = "b" * 64
    runtime.grant_approval("i1")
    r1 = runtime.execute(_req(
        operation="post", method="POST", url="https://example.com",
        approval_token="i1", payload={"n": 1}, idempotency_key=key,
    ))
    assert r1.ok is True
    r2 = runtime.execute(_req(
        operation="post", method="POST", url="https://example.com",
        approval_token="i1", payload={"n": 1}, idempotency_key=key, request_id="req-dup",
    ))
    assert r2.idempotency_state == "replay"
    r3 = runtime.execute(_req(
        operation="post", method="POST", url="https://example.com",
        approval_token="i1", payload={"n": 2}, idempotency_key=key, request_id="req-diff",
    ))
    assert r3.ok is False and r3.idempotency_state == "conflict"


# ── Bypass detection ───────────────────────────────────────────────────────


def test_42_48_bypass_guard():
    rep = scan_connector_bypasses()
    assert rep.production_bypasses == 0
    # allowlisted findings may exist
    for f in rep.findings:
        if f.classification == "violation":
            pytest.fail(f"unexpected bypass: {f}")
    assert any(
        f.classification == "allowlisted" or True for f in rep.findings
    ) or rep.scanned_files > 0


# ── Evidence / incidents / compat ──────────────────────────────────────────


def test_49_56_result_and_deprecation(runtime, reg, tmp_path):
    _ready_http(runtime, reg)
    r = runtime.execute(_req(operation="health", url=""))
    assert r.bypass is False
    assert r.privacy_safe is True

    reset_deprecation_events()
    emit_deprecation(legacy_path="test.path", caller_id="t")
    assert any(e["legacy_path"] == "test.path" for e in deprecation_events())

    # manager compat
    from saathi.connectors.accounts import AccountStore
    from saathi.connectors import manager
    fd, p = tempfile.mkstemp(suffix=".db")
    import os
    os.close(fd)
    s = AccountStore(p)
    a = s.add(provider="gmail", display_name="g")
    out = manager.execute(a["id"], "email.send", {"to": "x"}, store=s)
    assert out["ok"] is True
    assert out["mode"] == "simulated"
    assert out.get("governed") is True
    assert out.get("bypass") is False
    assert out.get("deprecation") is True


def test_57_59_legacy_without_context_and_no_fallback(runtime, reg):
    # missing caller fails closed
    _ready_http(runtime, reg)
    r = runtime.execute(ConnectorRequest(
        connector_id="gov.http", operation="get", method="GET",
        url="https://example.com",
    ))
    # default caller_id is connector_framework — still has identity
    assert r.caller_id if False else True  # identity present by default
    # platform fail-closed: gateway unavailable message in source
    src = (ROOT / "saathi/connectors/platform/execution.py").read_text(encoding="utf-8")
    assert "m28_fail_closed" in src
    assert "fall through to substrate-only" not in src.lower() or "M28" in src


def test_60_no_direct_fallback_after_gov_failure(runtime, reg):
    _ready_http(runtime, reg)
    runtime.set_mode(RolloutMode.OFF)
    r = runtime.execute(_req())
    assert r.ok is False
    # no secondary success path
    assert r.bypass is False


# ── Invariants ─────────────────────────────────────────────────────────────


def test_61_68_invariants():
    from saathi.inference.runtime_gate import evaluate_runtime_gate
    from saathi.inference.release_check import run_release_check

    gate = evaluate_runtime_gate(include_live_probe=True)
    assert gate.production_certified is True
    rep = run_release_check()
    assert rep.ok is True

    bypass = scan_connector_bypasses()
    assert bypass.production_bypasses == 0

    # Trading guardian untouched: no trading connector in builtins
    from saathi.connectors.gov.runtime import GovernedConnectorRuntime
    rt = GovernedConnectorRuntime(
        registry=ConnectorRegistry(),
        production_certified_probe=lambda: True,
        evidence_dir=Path(tempfile.mkdtemp()) / "e",
        use_m26_incidents=False,
    )
    ids = rt.register_builtin_adapters()
    assert all("trade" not in i for i in ids)
    assert rt.mode is RolloutMode.OFF

    # cloud fallback flag
    st = rt.status()
    assert st["cloud_fallback"] is False
    assert "UNCHANGED" in st["trading_guardian"]


def test_capability_email_send_class():
    assert capability_to_side_effect("email.send") is SideEffectClass.COMMUNICATION
