"""M224–M231 Read-Only Broker Connectivity Readiness — focused tests.

SIMULATION ONLY. No real brokers. No real credentials. No order submission.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from saathi.platform.tg.broker_readiness.service import (
    BrokerReadinessError,
    BrokerReadinessService,
    reset_broker_readiness_for_tests,
    TERMINAL_VERDICT,
)
from saathi.platform.tg.broker_readiness.models import (
    CredentialLifecycleState,
    ConnectionState,
    PolicyDecision,
    ScopeOutcome,
    CREDENTIAL_USABLE_FOR_REAL_CONNECTION,
    LIVE_TRADING_AUTHORIZED,
    REAL_BROKER_CONNECTION_CAPABLE,
)
from saathi.platform.tg.broker_readiness.transport import REAL_PROVIDER_TRANSPORT_FORBIDDEN
from saathi.platform.tg.broker_readiness.secrets import SecretRejectionError, reject_secrets_in_payload


@pytest.fixture()
def svc(tmp_path: Path):
    db = tmp_path / "br_test.db"
    return reset_broker_readiness_for_tests(db_path=db)


# ── M224 adapter ─────────────────────────────────────────────────────────────

def test_m224_adapter_contract_and_connection_state(svc: BrokerReadinessService):
    ops = svc.list_adapter_ops()
    assert ops["connection_state"] == "SIMULATED_NOT_CONNECTED"
    assert ops["real_provider_implementation"] is False
    available = [o for o in ops["operations"] if o["available_in_m224"]]
    assert all(o["authority_class"] in ("PUBLIC_DATA", "READ_ONLY_ACCOUNT") for o in available)
    unavailable = [o for o in ops["operations"] if not o["available_in_m224"]]
    assert any(o["operation"] == "place_order" for o in unavailable)

    r = svc.invoke_adapter("balances")
    assert r["ok"] is True
    assert r["connection_state"] == "SIMULATED_NOT_CONNECTED"
    assert r["real_transport"] is False

    with pytest.raises(BrokerReadinessError) as ei:
        svc.invoke_adapter("place_order")
    assert ei.value.code == "DENY_WRITE_SCOPE"


def test_m224_providers_not_connected(svc: BrokerReadinessService):
    p = svc.list_providers()
    assert p["all_simulated_not_connected"] is True


# ── M225 policy ───────────────────────────────────────────────────────────────

def test_m225_policy_allows_simulation_denies_write(svc: BrokerReadinessService):
    ok = svc.policy_check("balances", scopes=["BALANCE_READ"], environment="SIMULATION")
    assert ok["decision"] == PolicyDecision.ALLOW_SIMULATION_ONLY.value
    assert ok["allowed"] is True
    assert ok["connected"] is False

    deny = svc.policy_check(
        "place_order", scopes=["ORDER_CREATE"], trading_permission=True,
    )
    assert deny["allowed"] is False
    assert deny["decision"] in (
        PolicyDecision.DENY_WRITE_SCOPE.value,
        PolicyDecision.DENY_EXCESS_PERMISSION.value,
    )

    real = svc.policy_check("balances", real_connection_requested=True)
    assert real["decision"] == PolicyDecision.DENY_REAL_CONNECTION.value

    prod = svc.policy_check("balances", environment="PRODUCTION")
    assert prod["decision"] == PolicyDecision.DENY_WRONG_ENVIRONMENT.value


def test_m225_mixed_permissions_no_silent_downgrade(svc: BrokerReadinessService):
    r = svc.policy_check(
        "balances",
        permissions=["read balances", "trading", "withdrawal"],
        scopes=["BALANCE_READ"],
    )
    assert r["allowed"] is False
    assert r["decision"] == PolicyDecision.DENY_EXCESS_PERMISSION.value


# ── M226 credential lifecycle ────────────────────────────────────────────────

def test_m226_lifecycle_and_unusable(svc: BrokerReadinessService):
    prop = svc.propose_credential(provider_id="sim.readonly.fixture")
    c = prop["credential"]
    assert c["lifecycle_state"] == "proposed"
    assert c["credential_usable_for_real_connection"] is False
    assert c["secret_material_present"] is False
    assert CREDENTIAL_USABLE_FOR_REAL_CONNECTION is False

    adv = svc.advance_credential(c["id"])
    assert adv["credential"]["lifecycle_state"] == "activated-in-simulation"
    assert adv["credential"]["credential_usable_for_real_connection"] is False

    use = svc.attempt_real_use(c["id"])
    assert use["ok"] is False
    assert use["credential_usable_for_real_connection"] is False


def test_m226_secret_rejection_api_key_jwt_pem(svc: BrokerReadinessService):
    with pytest.raises(BrokerReadinessError):
        svc.propose_credential(metadata={"api_key": "sk-live-abcdefghijklmnopqrstuvwxyz0123"})

    with pytest.raises(BrokerReadinessError):
        svc.propose_credential(metadata={
            "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.payload.signature",
        })

    with pytest.raises(BrokerReadinessError):
        svc.propose_credential(metadata={
            "private_key": "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA",
        })

    with pytest.raises(BrokerReadinessError):
        svc.propose_credential(metadata={
            "bearer": "Bearer supersecrettokenvalue1234567890",
        })

    with pytest.raises(SecretRejectionError):
        reject_secrets_in_payload({"password": "hunter2hunter2hunter2xx"})


def test_m226_write_scope_on_propose_rejected(svc: BrokerReadinessService):
    with pytest.raises(BrokerReadinessError):
        svc.propose_credential(declared_scopes=["BALANCE_READ", "ORDER_CREATE"])


def test_m226_no_restoration_after_revocation(svc: BrokerReadinessService):
    c = svc.propose_credential()["credential"]
    svc.credentials.transition(c["id"], CredentialLifecycleState.REVOKED.value, force=True)
    with pytest.raises(Exception):
        svc.credentials.transition(
            c["id"], CredentialLifecycleState.ACTIVATED_IN_SIMULATION.value,
        )


# ── M227 scope ────────────────────────────────────────────────────────────────

def test_m227_least_privilege_and_rejects(svc: BrokerReadinessService):
    ok = svc.scope_check(
        requested=["BALANCE_READ", "POSITION_READ"],
        declared=["BALANCE_READ", "POSITION_READ"],
        provider_reported=["BALANCE_READ", "POSITION_READ"],
        approved=["BALANCE_READ", "POSITION_READ", "PORTFOLIO_READ"],
    )
    assert ok["outcome"] == ScopeOutcome.LEAST_PRIVILEGE_CONFIRMED_IN_SIMULATION.value
    assert ok["ok"] is True

    write = svc.scope_check(
        requested=["ORDER_CREATE"], declared=["ORDER_CREATE"], approved=["ORDER_CREATE"],
    )
    assert write["ok"] is False
    assert write["outcome"] == ScopeOutcome.WRITE_PERMISSION_REJECTED.value

    mixed = svc.scope_check(
        requested=["BALANCE_READ", "WITHDRAWAL_CREATE"],
        declared=["BALANCE_READ", "WITHDRAWAL_CREATE"],
        approved=["BALANCE_READ", "WITHDRAWAL_CREATE"],
    )
    assert mixed["ok"] is False

    unknown = svc.scope_check(
        requested=["TELEPORT_READ"], declared=["TELEPORT_READ"], approved=["TELEPORT_READ"],
    )
    assert unknown["outcome"] == ScopeOutcome.UNKNOWN_SCOPE_REJECTED.value

    excess = svc.scope_check(
        requested=["BALANCE_READ", "POSITION_READ"],
        declared=["BALANCE_READ"],
        approved=["BALANCE_READ"],
    )
    assert excess["outcome"] == ScopeOutcome.EXCESS_SCOPE_REJECTED.value


# ── M228 connection + transport ──────────────────────────────────────────────

def test_m228_simulated_connection_state_machine(svc: BrokerReadinessService):
    s = svc.session_create()["session"]
    assert s["state"] == ConnectionState.NOT_CONFIGURED.value
    out = svc.session_simulate(s["id"])
    assert out["session"]["state"] == ConnectionState.SIMULATED_CONNECTED_READ_ONLY.value
    assert out["session"]["real_transport"] is False


def test_m228_real_transport_blocked(svc: BrokerReadinessService):
    probe = svc.transport_probe("https://api.binance.com/api/v3/account")
    assert probe["ok"] is False
    assert probe["result"] == REAL_PROVIDER_TRANSPORT_FORBIDDEN

    s = svc.session_create()["session"]
    with pytest.raises(BrokerReadinessError) as ei:
        svc.session_simulate(s["id"], real_url="https://api.alpaca.markets/v2/account")
    assert REAL_PROVIDER_TRANSPORT_FORBIDDEN in ei.value.code or "FORBIDDEN" in ei.value.code


def test_m228_no_auto_reconnect_after_security_failure(svc: BrokerReadinessService):
    s = svc.session_create()["session"]
    svc.session_simulate(s["id"])
    svc.session_event(s["id"], "credential_revocation")
    with pytest.raises(Exception):
        svc.connections.transition(s["id"], ConnectionState.SIMULATED_CONNECTING.value)


# ── M229 snapshots + reconciliation ──────────────────────────────────────────

def test_m229_snapshot_and_reconcile_no_mutation(svc: BrokerReadinessService):
    p = svc.snapshot_load()["snapshot"]
    l = svc.snapshot_load()["snapshot"]
    assert p["read_model_only"] is True
    assert p["execution_commands"] is False
    rec = svc.reconcile_run(p["id"], l["id"])["reconciliation"]
    assert rec["mutated_provider"] is False
    assert rec["mutated_portfolio"] is False
    assert "classifications" in rec


# ── M230 drills ───────────────────────────────────────────────────────────────

def test_m230_expiry_and_revocation_drills(svc: BrokerReadinessService):
    exp = svc.expiry_drill()
    assert exp["fail_closed"] is True
    assert exp["session_invalidated"] is True
    assert exp["live_systems_affected"] is False

    rev = svc.revocation_drill()
    assert rev["fail_closed"] is True
    assert rev["auto_reconnect_prohibited"] is True


def test_m230_incident_suite(svc: BrokerReadinessService):
    suite = svc.drill_suite()
    assert suite["count"] >= 20
    assert suite["live_systems_affected"] is False


# ── M231 control + security + authority ─────────────────────────────────────

def test_m231_dashboard_and_certify(svc: BrokerReadinessService):
    dash = svc.dashboard()
    assert dash["labels"]["simulation_only"] == "SIMULATION ONLY"
    assert dash["ui_constraints"]["accepts_raw_secrets"] is False
    assert dash["ui_constraints"]["enable_trading_button"] is False

    cert = svc.certify()
    assert cert["verdict"] == TERMINAL_VERDICT
    assert cert["live_trading_authorized"] is False
    assert LIVE_TRADING_AUTHORIZED is False
    assert REAL_BROKER_CONNECTION_CAPABLE is False


def test_m231_llm_boundary(svc: BrokerReadinessService):
    for action in (
        "approve_credentials", "activate_sessions", "connect_brokers",
        "authorize_live_trading", "submit_orders",
    ):
        r = svc.llm_refuse(action)
        assert r["ok"] is False
        assert r["error"] == "LLM_AUTHORITY_DENIED"


def test_m231_security_scan(svc: BrokerReadinessService):
    sec = svc.security_scan()
    assert sec["all_pass"] is True
    assert sec["failed"] == 0


def test_storage_restart_safe(tmp_path: Path):
    db = tmp_path / "restart.db"
    s1 = BrokerReadinessService(db_path=db)
    c = s1.propose_credential()["credential"]
    cid = c["id"]
    s1.store.close()

    s2 = BrokerReadinessService(db_path=db)
    got = s2.credentials.get(cid)
    assert got["id"] == cid
    assert got["credential_usable_for_real_connection"] is False
    s2.store.close()


def test_posture_flags(svc: BrokerReadinessService):
    p = svc.posture()
    assert p["paper_only"] is True
    assert p["simulation_only"] is True
    assert p["live_trading_authorized"] is False
    assert p["SIMULATION_ONLY"] is True


def test_cli_verdict_importable():
    from saathi.platform.tg.cli import main
    # smoke: br-verdict path exists
    assert callable(main)
