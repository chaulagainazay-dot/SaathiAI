"""M216–M223 — Broker Integration Sandbox Architecture & Trust Framework.

PAPER ONLY. No live brokers. No API credentials. No exchange auth.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from saathi.platform.tg.broker_sandbox import (
    BROKER_CREDENTIAL_SUPPORT,
    LIVE_ORDER_CAPABLE,
    LIVE_TRADING_AUTHORIZED,
    LLM_BOUNDARY,
    PAPER_POSTURE,
    REAL_BROKER_CONNECTION_CAPABLE,
    TERMINAL_VERDICT,
    reset_broker_sandbox_for_tests,
)
from saathi.platform.tg.broker_sandbox.credentials import CredentialTrustError
from saathi.platform.tg.broker_sandbox.emulator import SandboxBrokerError
from saathi.platform.tg.broker_sandbox.models import REQUIRED_TRUST_STAGES, TrustApprovalStage
from saathi.platform.tg.broker_sandbox.trust_pipeline import TrustPipelineError
from saathi.platform.tg import (
    LIVE_TRADING_AUTHORIZED as TG_LIVE,
    LIVE_ORDER_CAPABLE as TG_ORDER,
    BROKER_CREDENTIAL_SUPPORT as TG_CRED,
)


def _svc(tmp_path: Path):
    return reset_broker_sandbox_for_tests(tmp_path / "broker_sandbox.db")


# ── authority / posture ──────────────────────────────────────────────────────
def test_paper_only_constants_and_posture(tmp_path):
    assert LIVE_TRADING_AUTHORIZED is False
    assert LIVE_ORDER_CAPABLE is False
    assert BROKER_CREDENTIAL_SUPPORT is False
    assert REAL_BROKER_CONNECTION_CAPABLE is False
    assert TG_LIVE is False
    assert TG_ORDER is False
    assert TG_CRED is False
    svc = _svc(tmp_path)
    p = svc.posture()
    assert p["paper_only"] is True
    assert p["live_trading_authorized"] is False
    assert p["sandbox_only"] is True
    assert p["exchange_connected"] is False
    assert p["llm_boundary"]["llm_may_connect_brokers"] is False
    assert p["llm_boundary"]["llm_may_store_credentials"] is False
    assert p["llm_boundary"]["llm_may_execute_orders"] is False
    assert p["llm_boundary"]["llm_may_enable_live_mode"] is False
    v = svc.terminal_verdict()
    assert v["verdict"] == TERMINAL_VERDICT
    assert v["verdict"] == "BROKER_SANDBOX_ARCHITECTURE_CERTIFIED_WITH_LIMITATIONS"
    assert "THE SYSTEM REMAINS PAPER ONLY." in v["statements"]
    assert "NO BROKER CONNECTIONS EXIST." in v["statements"]
    assert "NO API CREDENTIALS WERE CREATED." in v["statements"]
    assert "NO LIVE TRADING IS AUTHORIZED." in v["statements"]
    assert "THE SANDBOX CANNOT EXECUTE REAL ORDERS." in v["statements"]
    assert v["broker_connections_exist"] is False
    assert v["api_credentials_created"] is False
    assert v["sandbox_can_execute_real_orders"] is False


def test_llm_boundary_forbidden_and_allowed():
    assert LLM_BOUNDARY["llm_may_explain"] is True
    assert LLM_BOUNDARY["llm_may_recommend"] is True
    assert LLM_BOUNDARY["llm_may_simulate"] is True
    for k in (
        "llm_may_connect_brokers",
        "llm_may_store_credentials",
        "llm_may_approve_credentials",
        "llm_may_approve_brokers",
        "llm_may_execute_orders",
        "llm_may_enable_live_mode",
        "llm_may_authorize_trading",
        "llm_may_bypass_approval",
    ):
        assert LLM_BOUNDARY[k] is False, k


# ── M216 abstraction ─────────────────────────────────────────────────────────
def test_m216_abstraction_surface(tmp_path):
    svc = _svc(tmp_path)
    a = svc.abstraction()
    assert a["milestone"] == "M216"
    for concept in (
        "Broker", "Account", "Portfolio", "Position", "Order", "Trade",
        "ExecutionReport", "MarketData", "Asset", "Balance", "Connection", "Capability",
    ):
        assert concept in a["concepts"]
    assert a["real_brokers_implemented"] == []
    assert a["live_capable"] is False
    assert a["network_io"] is False


# ── M217 capability registry ─────────────────────────────────────────────────
def test_m217_registry_all_not_connected(tmp_path):
    svc = _svc(tmp_path)
    brokers = svc.list_brokers()["brokers"]
    assert len(brokers) >= 8
    for b in brokers:
        assert b["live_capable"] is False
        assert b["real_connection"] is False
        if b["is_emulator"]:
            assert b["connection_status"] in ("SANDBOX_ONLY", "NOT_CONNECTED")
        else:
            assert b["connection_status"] == "NOT_CONNECTED"
    caps = svc.list_capabilities()
    assert caps["connection_invariant"]["ok"] is True
    assert caps["connection_invariant"]["all_not_connected"] is True
    # each capability tracks required fields
    for c in caps["capabilities"]:
        assert "paper_support" in c
        assert "market_orders" in c
        assert "limit_orders" in c
        assert "stop_orders" in c
        assert "margin" in c
        assert "options" in c
        assert "futures" in c
        assert "crypto" in c
        assert "equities" in c
        assert "rate_limits" in c
        assert "authentication_method" in c
        assert "streaming_support" in c
        assert "order_events" in c
        assert "time_zones" in c
        assert "status" in c
        assert c["connected"] is False
        assert c["live_capable"] is False


def test_m217_connect_always_refused(tmp_path):
    svc = _svc(tmp_path)
    for bid in (
        "catalog.binance", "catalog.alpaca", "catalog.interactive_brokers",
        "catalog.zerodha", "catalog.bybit", "catalog.coinbase", "catalog.kraken",
    ):
        r = svc.refuse_connect(bid)
        assert r["ok"] is False
        assert r["error"] == "BROKER_CONNECT_FORBIDDEN"
        assert r["connection_status"] == "NOT_CONNECTED"


# ── M218 credential trust ────────────────────────────────────────────────────
def test_m218_metadata_only_no_secrets(tmp_path):
    svc = _svc(tmp_path)
    ref = svc.create_credential_ref(
        broker_id="catalog.binance",
        label="test-meta",
        provider_metadata={"provider": "BINANCE", "env": "SANDBOX"},
        permission_scopes=["read:metadata"],
        actor="operator:test",
    )["reference"]
    assert ref["usable"] is False
    assert ref["secret_material_present"] is False
    assert ref["status"] in ("PLACEHOLDER", "METADATA_ONLY", "APPROVED_METADATA")

    use = svc.attempt_use_credential(ref["id"])
    assert use["ok"] is False
    assert use["error"] == "CREDENTIAL_UNUSABLE"

    # Reject real secrets
    with pytest.raises(Exception) as ei:
        svc.create_credential_ref(
            broker_id="catalog.alpaca",
            provider_metadata={"api_key": "AKIA_LIVE_SECRET"},
            actor="operator:test",
        )
    assert "SECRET" in str(ei.value).upper() or "secret" in str(ei.value).lower()

    fw = svc.list_credential_refs()["framework"]
    assert fw["stores_real_credentials"] is False
    assert fw["accepts_api_keys"] is False
    assert fw["secrets_usable"] is False


def test_m218_revocation_and_approval_chain(tmp_path):
    svc = _svc(tmp_path)
    ref = svc.create_credential_ref(
        broker_id="catalog.kraken", label="chain", actor="op",
    )["reference"]
    approved = svc.approve_credential_metadata(
        ref["id"], stage="CREDENTIAL", actor="sec:op", decision="approve",
    )["reference"]
    assert approved["usable"] is False  # still unusable after approval
    assert len(approved["approval_chain"]) >= 1
    revoked = svc.revoke_credential_ref(ref["id"], actor="op", reason="test")["reference"]
    assert revoked["status"] == "REVOKED"
    assert revoked["usable"] is False


# ── M219 emulator ────────────────────────────────────────────────────────────
def test_m219_market_and_limit_orders(tmp_path):
    svc = _svc(tmp_path)
    sess = svc.emulator_session(seed=7)["session"]
    mkt = svc.emulator_place_order(
        sess["id"], symbol="AAA", side="BUY", order_type="MARKET", quantity="10",
    )["order"]
    assert mkt["state"] == "FILLED"
    assert mkt["simulated"] is True
    assert mkt["live_order"] is False
    assert float(mkt["filled_qty"]) == 10

    lim = svc.emulator_place_order(
        sess["id"], symbol="AAA", side="BUY", order_type="LIMIT",
        quantity="5", limit_price="1",  # far below market → OPEN
    )["order"]
    assert lim["state"] == "OPEN"


def test_m219_partial_reject_timeout_invalid_disconnect(tmp_path):
    svc = _svc(tmp_path)
    sess = svc.emulator_session()["session"]
    partial = svc.emulator_place_order(
        sess["id"], symbol="AAA", side="BUY", order_type="MARKET",
        quantity="10", partial_fill_ratio="0.3",
    )["order"]
    assert partial["state"] == "PARTIALLY_FILLED"

    svc.emulator_set_mode(sess["id"], "REJECT")
    rej = svc.emulator_place_order(
        sess["id"], symbol="AAA", side="BUY", order_type="MARKET", quantity="1",
    )["order"]
    assert rej["state"] == "REJECTED"

    svc.emulator_set_mode(sess["id"], "TIMEOUT")
    to = svc.emulator_place_order(
        sess["id"], symbol="AAA", side="BUY", order_type="MARKET", quantity="1",
    )["order"]
    assert to["state"] == "TIMED_OUT"

    svc.emulator_set_mode(sess["id"], "")
    inv = svc.emulator_place_order(
        sess["id"], symbol="FAKE_XYZ", side="BUY", order_type="MARKET", quantity="1",
    )["order"]
    assert inv["state"] == "REJECTED"
    assert inv["reject_reason"] == "INVALID_SYMBOL"

    # disconnect
    from saathi.platform.tg.broker_sandbox.emulator import SandboxEmulator
    em = svc.emulator
    em.set_connected(sess["id"], False)
    with pytest.raises(SandboxBrokerError) as ei:
        em.place_order(sess["id"], symbol="AAA", side="BUY", order_type="MARKET", quantity="1")
    assert ei.value.code == "DISCONNECTED"


# ── M220 trust pipeline ──────────────────────────────────────────────────────
def test_m220_full_approval_required_no_auto(tmp_path):
    svc = _svc(tmp_path)
    auto = svc.trust_auto_activate_refused("catalog.binance")
    assert auto["ok"] is False
    assert auto["error"] == "APPROVAL_REQUIRED"
    assert auto["live_authorized"] is False

    pipe = svc.trust_create(
        broker_id="catalog.alpaca", created_by="operator:test",
    )["pipeline"]
    assert pipe["status"] == "DRAFT"
    assert set(pipe["required_stages"]) == {s.value for s in REQUIRED_TRUST_STAGES}

    gate = svc.trust_gate(pipe["id"])
    assert gate["allowed_sandbox"] is False
    assert gate["allowed_live"] is False
    assert len(gate["missing_stages"]) == 8

    for stage in REQUIRED_TRUST_STAGES:
        out = svc.trust_decide(
            pipe["id"], stage=stage.value, decision="approve",
            actor=f"human:{stage.value.lower()}", actor_role=stage.value,
            reason="sandbox architecture test",
        )["pipeline"]

    assert out["status"] == "FULLY_APPROVED_SANDBOX"
    assert out["all_approved"] is True
    assert out["live_authorized"] is False
    assert out["auto_activated"] is False
    gate2 = svc.trust_gate(pipe["id"])
    assert gate2["allowed_sandbox"] is True
    assert gate2["allowed_live"] is False


def test_m220_llm_cannot_approve(tmp_path):
    svc = _svc(tmp_path)
    pipe = svc.trust_create(broker_id="catalog.bybit", created_by="op")["pipeline"]
    with pytest.raises(Exception) as ei:
        svc.trust_decide(
            pipe["id"], stage="OWNER", decision="approve",
            actor="llm:assistant", actor_role="LLM",
        )
    assert "LLM" in str(ei.value).upper()


# ── M221 failure suite ───────────────────────────────────────────────────────
def test_m221_failure_suite_fail_closed(tmp_path):
    svc = _svc(tmp_path)
    suite = svc.failure_suite()
    assert suite["scenarios"] >= 15
    assert suite["all_fail_closed"] is True
    assert suite["passed"] is True
    assert suite["live_impact"] is False
    assert suite["paper_only"] is True


def test_m221_individual_scenarios(tmp_path):
    svc = _svc(tmp_path)
    for sc in (
        "NETWORK_LOSS", "BROKER_OUTAGE", "DUPLICATE_FILLS", "LATE_FILLS",
        "CLOCK_SKEW", "ORDER_REPLAY", "SEQUENCE_GAPS", "CONNECTION_LOSS",
        "CREDENTIAL_EXPIRY", "RECOVERY", "ROLLBACK",
    ):
        r = svc.failure_run(sc)
        assert r["fail_closed"] is True, sc
        assert r["result"].get("ok") is True, (sc, r)


# ── M222 security ────────────────────────────────────────────────────────────
def test_m222_security_validation_all_pass(tmp_path):
    svc = _svc(tmp_path)
    result = svc.security_validate()
    assert result["all_passed"] is True
    assert result["passed_count"] == result["total"]
    assert result["total"] >= 8
    names = {c["check_name"] for c in result["checks"]}
    for expected in (
        "broker_isolation",
        "credential_isolation",
        "approval_isolation",
        "audit_integrity",
        "llm_authority_boundaries",
        "environment_separation",
        "sandbox_separation",
        "no_approval_bypass",
    ):
        assert expected in names


# ── M223 control center ──────────────────────────────────────────────────────
def test_m223_dashboard_surfaces(tmp_path):
    svc = _svc(tmp_path)
    dash = svc.dashboard()
    assert dash["labels"]["sandbox_only"] == "SANDBOX ONLY"
    assert dash["labels"]["no_live_broker"] == "NO LIVE BROKER"
    assert dash["paper_only"] is True
    assert dash["no_live_broker"] is True
    assert "broker_registry" in dash
    assert "capability_viewer" in dash
    assert "sandbox_emulator" in dash
    assert "trust_center" in dash
    assert "approval_pipeline" in dash
    assert "credential_metadata" in dash
    assert "recovery_center" in dash
    assert "audit_timeline" in dash
    assert "security_dashboard" in dash
    assert dash["broker_registry"]["all_not_connected"] is True
    assert dash["sandbox_emulator"]["real_network"] is False
    assert "THE SYSTEM REMAINS PAPER ONLY." in dash["disclaimer"]


# ── negative / authority ─────────────────────────────────────────────────────
def test_negative_no_real_broker_login_paths(tmp_path):
    """Ensure no live login surfaces exist for prohibited brokers."""
    svc = _svc(tmp_path)
    prohibited = [
        "binance", "alpaca", "interactive_brokers", "zerodha",
        "bybit", "coinbase", "kraken",
    ]
    for name in prohibited:
        bid = f"catalog.{name}"
        b = svc.get_broker(bid)
        assert b["broker"]["connection_status"] == "NOT_CONNECTED"
        assert svc.refuse_connect(bid)["ok"] is False


def test_audit_timeline_populated(tmp_path):
    svc = _svc(tmp_path)
    svc.list_brokers()
    svc.emulator_session()
    audit = svc.audit_timeline(limit=50)
    assert len(audit["events"]) >= 1
    assert audit["paper_only"] is True


def test_paper_posture_disclaimer():
    d = PAPER_POSTURE["disclaimer"]
    assert "PAPER ONLY" in d
    assert "NO BROKER CONNECTIONS" in d
    assert "NO API CREDENTIALS" in d
    assert "NO LIVE TRADING" in d
    assert "CANNOT EXECUTE REAL ORDERS" in d
