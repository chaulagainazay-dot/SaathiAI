"""M18.4 — Governed InsForge migration planning + approval-gated write pilot."""
from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from saathi.connectors.platform.store import ConnectorStore
from saathi.providers.insforge.config import InsForgeConfig
from saathi.providers.insforge.migration import MigrationService, TOOL_ID
from saathi.providers.insforge.migration_policy import (
    build_request_from_dict,
    plan_migration,
    reject_raw_sql,
)
from saathi.providers.insforge.migration_store import MigrationLedger
from saathi.providers.insforge.migration_types import (
    ExecutionOutcome,
    MigrationRisk,
    PreflightStrength,
)
from saathi.providers.insforge.provider import WRITE_DENYLIST, InsForgeProvider

ROOT = Path(__file__).resolve().parents[1]

CREATE_TABLE = {
    "provider": "insforge",
    "project_id": "pilot",
    "environment": "dev",
    "migration_name": "create_widgets",
    "version": "1",
    "requestor": "operator",
    "operations": [
        {
            "op": "create_table",
            "table": "pilot_widgets",
            "columns": [
                {"name": "id", "type": "text", "nullable": False, "primary_key": True},
                {"name": "title", "type": "text", "nullable": True},
            ],
        }
    ],
}


def _cfg(**over) -> InsForgeConfig:
    base = dict(
        enabled=True,
        base_url="http://127.0.0.1:7130",
        api_key="ik_test_key_not_real",
        timeout_sec=5.0,
        max_response_bytes=50_000,
        max_log_records=10,
        tls_verify=True,
        allow_loopback=True,
        writes_enabled=True,
    )
    base.update(over)
    return InsForgeConfig(**base)


def _svc(tmp_path, **cfg_over) -> MigrationService:
    store = ConnectorStore(db_path=tmp_path / "appr.db")
    ledger = MigrationLedger(tmp_path / "ledger.sqlite")
    cfg = _cfg(**cfg_over)

    def write_exec(req, plan):
        return {
            "applied": True,
            "simulated": True,
            "verify_override": True,
            "verify_detail": "simulated_ok",
        }

    return MigrationService(
        config=cfg,
        provider=InsForgeProvider(config=cfg, audit=False),
        ledger=ledger,
        approval_store=store,
        write_executor=write_exec,
    )


def _approve_flow(svc: MigrationService, raw: dict, owner: str = "owner1") -> tuple[str, str]:
    plan = svc.plan(raw)
    assert plan.ok, plan.denied_reason
    svc.preflight(raw)
    ar = svc.request_approval(raw, owner=owner)
    assert ar["ok"], ar
    aid = ar["approval_id"]
    # human resolves (not agent self-approve)
    r = svc.approve(aid, actor="human_approver", approved=True)
    assert r["ok"]
    return aid, plan.fingerprint


# ── planning / normalization ────────────────────────────────────────────────


def test_01_deterministic_fingerprint():
    r1, e1 = build_request_from_dict(CREATE_TABLE)
    r2, e2 = build_request_from_dict(CREATE_TABLE)
    assert not e1 and not e2
    assert r1.fingerprint() == r2.fingerprint()
    assert len(r1.fingerprint()) == 64


def test_02_fingerprint_changes_on_meaningful_edit():
    r1, _ = build_request_from_dict(CREATE_TABLE)
    alt = json.loads(json.dumps(CREATE_TABLE))
    alt["operations"][0]["table"] = "pilot_gadgets"
    r2, _ = build_request_from_dict(alt)
    assert r1.fingerprint() != r2.fingerprint()


def test_03_whitespace_equivalent_ops_same_fp():
    a = dict(CREATE_TABLE)
    b = json.loads(json.dumps(CREATE_TABLE))
    b["operations"][0]["table"] = "PILOT_WIDGETS"  # normalized lower
    r1, _ = build_request_from_dict(a)
    r2, _ = build_request_from_dict(b)
    assert r1.fingerprint() == r2.fingerprint()


def test_04_raw_sql_rejected():
    assert reject_raw_sql("DROP TABLE users") != ""
    assert reject_raw_sql("SELECT 1") != ""  # even "safe" SQL denied
    assert reject_raw_sql("") == ""
    req, err = build_request_from_dict({**CREATE_TABLE, "sql": "CREATE TABLE x(a text)"})
    assert err and req is None


def test_05_too_many_ops_rejected():
    ops = [
        {"op": "create_table", "table": f"t{i}", "columns": [{"name": "id", "type": "text"}]}
        for i in range(20)
    ]
    req, err = build_request_from_dict({**CREATE_TABLE, "operations": ops})
    assert err.startswith("too_many")


# ── allow / deny ────────────────────────────────────────────────────────────


def test_06_allowed_create_table():
    plan = plan_migration(build_request_from_dict(CREATE_TABLE)[0])
    assert plan.ok
    assert plan.risk == MigrationRisk.LOW


def test_07_allowed_add_nullable_column():
    raw = {
        **CREATE_TABLE,
        "operations": [{
            "op": "add_column",
            "table": "pilot_widgets",
            "column": {"name": "note", "type": "text", "nullable": True},
        }],
    }
    plan = plan_migration(build_request_from_dict(raw)[0])
    assert plan.ok


def test_08_allowed_index():
    raw = {
        **CREATE_TABLE,
        "operations": [{
            "op": "create_index",
            "table": "pilot_widgets",
            "index_name": "idx_pilot_widgets_title",
            "index_columns": ["title"],
            "unique": False,
        }],
    }
    plan = plan_migration(build_request_from_dict(raw)[0])
    assert plan.ok


def test_09_destructive_denied():
    req, err = build_request_from_dict({
        **CREATE_TABLE,
        "operations": [{"op": "drop_table", "table": "x"}],
    })
    assert err or (req and not plan_migration(req).ok)


def test_10_dml_via_sql_denied():
    assert "denied" in reject_raw_sql("DELETE FROM users") or reject_raw_sql("DELETE FROM users")


def test_11_unknown_op_denied():
    req, err = build_request_from_dict({
        **CREATE_TABLE,
        "operations": [{"op": "grant_all", "table": "x"}],
    })
    assert err


def test_12_production_environment_denied():
    raw = {**CREATE_TABLE, "environment": "prod"}
    plan = plan_migration(build_request_from_dict(raw)[0])
    assert plan.ok is False
    assert "environment" in plan.denied_reason


def test_13_non_nullable_add_column_denied():
    raw = {
        **CREATE_TABLE,
        "operations": [{
            "op": "add_column",
            "table": "pilot_widgets",
            "column": {"name": "req", "type": "text", "nullable": False},
        }],
    }
    req, err = build_request_from_dict(raw)
    assert err


# ── risk / approval ─────────────────────────────────────────────────────────


def test_14_approval_required_and_bound(tmp_path):
    svc = _svc(tmp_path)
    plan = svc.plan(CREATE_TABLE)
    assert plan.approval_level == "L3"
    ar = svc.request_approval(CREATE_TABLE, owner="owner1")
    assert ar["ok"]
    assert ar["fingerprint"] == plan.fingerprint
    # missing approval
    r = svc.execute(CREATE_TABLE, approval_id="", owner="owner1", actor_id="owner1")
    assert r.ok is False
    assert r.error_category == "approval_invalid"


def test_15_fingerprint_mismatch_denied(tmp_path):
    svc = _svc(tmp_path)
    aid, fp = _approve_flow(svc, CREATE_TABLE)
    alt = json.loads(json.dumps(CREATE_TABLE))
    alt["operations"][0]["table"] = "other_table"
    # preflight alt so we pass preflight gate and hit approval fingerprint check
    assert svc.preflight(alt).ok
    r = svc.execute(alt, approval_id=aid, owner="owner1", actor_id="owner1")
    assert r.ok is False
    assert "fingerprint" in r.detail or r.error_category == "approval_invalid"


def test_16_environment_mismatch_denied(tmp_path):
    svc = _svc(tmp_path)
    aid, _ = _approve_flow(svc, CREATE_TABLE)
    alt = {**CREATE_TABLE, "environment": "staging"}
    # re-plan different env → different fp → mismatch
    r = svc.execute(alt, approval_id=aid, owner="owner1", actor_id="owner1")
    assert r.ok is False


def test_17_denied_approval_rejected(tmp_path):
    svc = _svc(tmp_path)
    svc.preflight(CREATE_TABLE)
    ar = svc.request_approval(CREATE_TABLE, owner="owner1")
    svc.approve(ar["approval_id"], actor="human", approved=False)
    r = svc.execute(CREATE_TABLE, approval_id=ar["approval_id"], owner="owner1", actor_id="owner1")
    assert r.ok is False


def test_18_single_use_approval(tmp_path):
    svc = _svc(tmp_path)
    aid, _ = _approve_flow(svc, CREATE_TABLE)
    r1 = svc.execute(CREATE_TABLE, approval_id=aid, owner="owner1", actor_id="owner1")
    assert r1.ok and r1.outcome == ExecutionOutcome.APPLIED_AND_VERIFIED
    # second use — either duplicate suppressed or approval consumed
    r2 = svc.execute(CREATE_TABLE, approval_id=aid, owner="owner1", actor_id="owner1")
    assert r2.duplicate or r2.outcome == ExecutionOutcome.DUPLICATE_ALREADY_APPLIED or (
        r2.ok is False and "consum" in r2.detail
    )


# ── preflight ───────────────────────────────────────────────────────────────


def test_19_preflight_local_strength(tmp_path):
    svc = _svc(tmp_path, enabled=False)
    # plan works offline; preflight strength local
    cfg = _cfg(enabled=False, writes_enabled=False)
    svc2 = MigrationService(config=cfg, ledger=MigrationLedger(tmp_path / "l2.sqlite"),
                            approval_store=ConnectorStore(db_path=tmp_path / "a2.db"),
                            write_executor=lambda r, p: {"applied": True, "simulated": True,
                                                         "verify_override": True})
    pf = svc2.preflight(CREATE_TABLE)
    assert pf.ok
    assert pf.strength == PreflightStrength.LOCAL_POLICY_ONLY
    assert pf.provider_contacted is False


def test_20_preflight_required_before_execute(tmp_path):
    svc = _svc(tmp_path)
    plan = svc.plan(CREATE_TABLE)
    store = svc._get_approval_store()
    aid = store.add_approval(
        owner="owner1", connector_id="insforge", account_id="pilot",
        tool_id=TOOL_ID, capability_id="insforge_migration_apply",
        input_hash=plan.fingerprint, risk=3, environment="dev",
        target="insforge:pilot", max_uses=1,
    )
    store.resolve_approval(aid, approved=True, actor="human")
    # no preflight cached
    svc._last_preflight.clear()
    r = svc.execute(CREATE_TABLE, approval_id=aid, owner="owner1", actor_id="owner1")
    assert r.ok is False
    assert "preflight" in r.detail


# ── execution ───────────────────────────────────────────────────────────────


def test_21_disabled_provider_blocks_write(tmp_path):
    svc = _svc(tmp_path, enabled=False, writes_enabled=True)
    aid, _ = _approve_flow(svc, CREATE_TABLE)
    r = svc.execute(CREATE_TABLE, approval_id=aid, owner="owner1", actor_id="owner1")
    assert r.ok is False
    assert r.error_category == "provider_disabled"


def test_22_writes_flag_required(tmp_path):
    svc = _svc(tmp_path, writes_enabled=False)
    aid, _ = _approve_flow(svc, CREATE_TABLE)
    r = svc.execute(CREATE_TABLE, approval_id=aid, owner="owner1", actor_id="owner1")
    assert r.ok is False
    assert r.error_category == "writes_disabled"


def test_23_approved_migration_executes_once(tmp_path):
    svc = _svc(tmp_path)
    aid, fp = _approve_flow(svc, CREATE_TABLE)
    r = svc.execute(CREATE_TABLE, approval_id=aid, owner="owner1", actor_id="owner1")
    assert r.ok
    assert r.outcome == ExecutionOutcome.APPLIED_AND_VERIFIED
    assert r.fingerprint == fp
    assert r.verified
    st = svc.status(fp)
    assert st["ok"] and st["record"]["status"] == "verified"


def test_24_duplicate_suppressed(tmp_path):
    svc = _svc(tmp_path)
    aid, fp = _approve_flow(svc, CREATE_TABLE)
    svc.execute(CREATE_TABLE, approval_id=aid, owner="owner1", actor_id="owner1")
    # new approval cannot re-apply same fingerprint — ledger blocks
    ar2 = svc.request_approval(CREATE_TABLE, owner="owner1")
    if ar2["ok"]:
        svc.approve(ar2["approval_id"], actor="human", approved=True)
        r2 = svc.execute(CREATE_TABLE, approval_id=ar2["approval_id"], owner="owner1", actor_id="owner1")
        assert r2.outcome == ExecutionOutcome.DUPLICATE_ALREADY_APPLIED
        assert r2.duplicate


def test_25_concurrent_claims_one_winner(tmp_path):
    svc = _svc(tmp_path)
    aid, fp = _approve_flow(svc, CREATE_TABLE)
    results = []

    def run():
        results.append(svc.execute(CREATE_TABLE, approval_id=aid, owner="owner1", actor_id="owner1"))

    t1 = threading.Thread(target=run)
    t2 = threading.Thread(target=run)
    t1.start(); t2.start()
    t1.join(); t2.join()
    applied = [r for r in results if r.outcome == ExecutionOutcome.APPLIED_AND_VERIFIED]
    dups = [r for r in results if r.duplicate or r.outcome == ExecutionOutcome.DUPLICATE_ALREADY_APPLIED]
    unknowns = [r for r in results if r.outcome == ExecutionOutcome.OUTCOME_UNKNOWN]
    assert len(applied) + len(dups) + len(unknowns) == 2
    assert len(applied) <= 1


def test_26_verification_failure_outcome(tmp_path):
    store = ConnectorStore(db_path=tmp_path / "a.db")
    ledger = MigrationLedger(tmp_path / "l.sqlite")

    def write_exec(req, plan):
        return {"applied": True, "simulated": True, "verify_override": False,
                "verify_detail": "table_missing"}

    svc = MigrationService(
        config=_cfg(), ledger=ledger, approval_store=store, write_executor=write_exec,
        provider=InsForgeProvider(config=_cfg(), audit=False),
    )
    aid, _ = _approve_flow(svc, CREATE_TABLE)
    r = svc.execute(CREATE_TABLE, approval_id=aid, owner="owner1", actor_id="owner1")
    assert r.outcome == ExecutionOutcome.APPLIED_VERIFICATION_FAILED
    assert r.ok is False


def test_27_rollback_guidance_not_auto(tmp_path):
    svc = _svc(tmp_path)
    g = svc.rollback_guidance(CREATE_TABLE)
    assert g.get("auto_execute") is False
    assert g.get("approval_required") is True
    assert g.get("rollback_ops")


def test_28_provider_invoke_still_blocks_raw_migrate():
    p = InsForgeProvider(config=_cfg(), audit=False)
    r = p.invoke("migrate")
    assert r.ok is False
    assert "migrate" in WRITE_DENYLIST


def test_29_trading_isolation(tmp_path):
    pkg = ROOT / "saathi" / "providers" / "insforge"
    for path in pkg.rglob("*.py"):
        t = path.read_text(encoding="utf-8")
        assert "saathi.trade" not in t
        assert "from saathi.execution.trade" not in t
        low = t.lower()
        for b in ("binance", "alpaca", "exchange_execution"):
            assert b not in low
    p = InsForgeProvider(config=_cfg(), audit=False)
    assert p.invoke("place_order").ok is False
    # migration approval namespace ≠ trade approval
    assert TOOL_ID.startswith("insforge.")


def test_30_m18_3_regression():
    # disabled by default still holds
    from saathi.providers.insforge import load_config
    c = load_config(env={})
    assert c.enabled is False
    assert c.writes_enabled is False


def test_31_docs_present():
    assert (ROOT / "docs" / "M18_4_INSFORGE_MIGRATION_WRITE_PILOT.md").is_file()
    assert (ROOT / "docs" / "M18_4_VALIDATION.md").is_file()
    text = (ROOT / "docs" / "M18_4_INSFORGE_MIGRATION_WRITE_PILOT.md").read_text()
    assert "ExecutionGateway" in text or "Execution Gateway" in text
    assert "fingerprint" in text.lower()
