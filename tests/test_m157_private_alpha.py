"""M157–M165 SaathiOS Private Alpha — focused certification tests."""
from __future__ import annotations

import json
import os
import re
import sqlite3
import tarfile
from pathlib import Path

import pytest

from saathi.platform.context import PlatformContextError
from saathi.platform.core_os import SaathiCoreService, reset_core_service_for_tests
from saathi.platform.private_alpha import (
    AutomationExecutionService,
    apply_local_upgrade,
    build_release_manifest,
    compatibility_matrix,
    config_diff,
    create_system_backup,
    disaster_recovery_drill,
    doctor,
    dry_run_restore,
    export_support_bundle,
    init_first_run,
    load_config,
    migrate_config,
    prepare,
    restore_system_backup,
    rollback_config,
    run_private_alpha_certification,
    run_synthetic_operator_validation,
    save_config,
    upgrade_preflight,
    validate_config,
    verify_system_backup,
)
from saathi.platform.private_alpha.config import AlphaConfig, CONFIG_HISTORY
from saathi.platform.private_alpha.incidents import INCIDENT_PLAYBOOKS, playbook_for
from saathi.platform.private_alpha.lifecycle import may_terminate, safety_contract
from saathi.platform.service import reset_platform_for_tests
from saathi.tool_runtime.registry import reset_registry_for_tests

REPO = Path(__file__).resolve().parents[1]
ALPHA_CLI = REPO / "bin" / "saathi-alpha"
LOCAL_CLI = REPO / "bin" / "saathi-local"


@pytest.fixture()
def env(tmp_path: Path, monkeypatch):
    reset_registry_for_tests()
    # Isolate alpha config/data under tmp
    cfg_dir = tmp_path / "alpha_config"
    cfg_dir.mkdir()
    monkeypatch.setattr(
        "saathi.platform.private_alpha.config.CONFIG_DIR", cfg_dir
    )
    monkeypatch.setattr(
        "saathi.platform.private_alpha.config.CONFIG_PATH", cfg_dir / "alpha_config.json"
    )
    monkeypatch.setattr(
        "saathi.platform.private_alpha.config.CONFIG_HISTORY", cfg_dir / "history"
    )
    platform = reset_platform_for_tests(tmp_path / "pa.db")
    boot = platform.bootstrap_owner_secure(
        email="alpha-owner@local",
        name="Alpha Owner",
        password="AlphaOwnerPass1!",
        org_name="Alpha Org",
        workspace_name="Alpha WS",
    )
    ctx = platform.require_context(boot["token"])
    core = SaathiCoreService(platform)
    yield platform, boot["token"], ctx, core, tmp_path
    reset_core_service_for_tests(platform)
    reset_platform_for_tests()
    reset_registry_for_tests()


# ── M157 manifest ────────────────────────────────────────────────────────────
def test_release_manifest_safety_and_fields():
    m = build_release_manifest()
    assert m["saathios_release_version"]
    assert m["production_authorized"] is False
    assert m["public_exposure_authorized"] is False
    assert m["financial_execution_authorized"] is False
    assert m["required_local_ports"]["backend"] == 8765
    assert "known_limitations" in m
    matrix = compatibility_matrix()
    assert matrix["matrix"]["backup"] in (
        "CERTIFIED",
        "CERTIFIED_WITH_LIMITATIONS",
    )
    assert matrix["matrix"]["production"] == "NOT_CLAIMED"


# ── M158 prepare / init ──────────────────────────────────────────────────────
def test_prepare_idempotent_and_no_secrets(tmp_path, monkeypatch):
    # use real repo dirs but ensure prepare is re-runnable
    r1 = prepare(install_deps=False)
    r2 = prepare(install_deps=False)
    assert r1["ok"] is True
    assert r2["ok"] is True
    assert r1["production_authorized"] is False
    blob = json.dumps(r1).lower()
    assert "sk-" not in blob
    assert "api_key_value" not in blob


def test_init_requires_local_ack():
    r = init_first_run(acknowledge_local_only=False)
    assert r["ok"] is False
    assert r["error"] == "LOCAL_ONLY_ACK_REQUIRED"


def test_init_with_platform(env):
    platform, token, ctx, core, tmp = env
    r = init_first_run(
        acknowledge_local_only=True,
        platform=platform,
        enable_hcg_demo=False,
        enable_ielts_demo=False,
    )
    assert r["ok"] is True
    assert r["config"]["production_authorized"] is False
    assert r["config"]["automation_execution_enabled"] is False


# ── M159 lifecycle ───────────────────────────────────────────────────────────
def test_lifecycle_contract_and_unrelated_refuse():
    c = safety_contract()
    assert c["exists"] is True
    assert c["localhost_only"] is True
    assert c["refuses_unrelated_kill"] is True
    assert c["no_broad_pkill"] is True
    decision = may_terminate(
        99999,
        "backend",
        pidfile_pid=None,
        cmd="nginx: master process",
    )
    assert decision["may_terminate"] is False
    owned = may_terminate(
        42,
        "backend",
        pidfile_pid=42,
        cmd="/x/.venv/bin/python -m uvicorn saathi.server:app --host 127.0.0.1",
    )
    assert owned["may_terminate"] is True


def test_alpha_cli_exists_and_delegates():
    assert ALPHA_CLI.is_file()
    assert os.access(ALPHA_CLI, os.X_OK)
    src = ALPHA_CLI.read_text(encoding="utf-8")
    assert "saathi-local" in src
    assert "0.0.0.0" not in src
    assert LOCAL_CLI.is_file()


# ── M160 config ──────────────────────────────────────────────────────────────
def test_config_validation_migration_rollback(env):
    platform, token, ctx, core, tmp = env
    cfg = AlphaConfig(host="127.0.0.1", automation_execution_enabled=False)
    saved = save_config(cfg)
    assert saved.host == "127.0.0.1"
    with pytest.raises(ValueError):
        validate_config({"host": "0.0.0.0", "backend_port": 8765, "frontend_port": 3000})
    with pytest.raises(ValueError):
        validate_config(
            {
                "host": "127.0.0.1",
                "backend_port": 8765,
                "frontend_port": 3000,
                "api_key": "sk-secretvalue12345",
            }
        )
    with pytest.raises(ValueError):
        validate_config(
            {
                "host": "127.0.0.1",
                "backend_port": 8765,
                "frontend_port": 3000,
                "production_authorized": True,
            }
        )
    migrated = migrate_config({"schema_version": "m160.alpha_config.v0", "host": "127.0.0.1"})
    assert migrated["schema_version"].startswith("m160")
    # change + rollback
    save_config(AlphaConfig(backend_port=8765, frontend_port=3000, retention_days=10))
    save_config(AlphaConfig(backend_port=8765, frontend_port=3000, retention_days=20))
    rolled = rollback_config()
    assert isinstance(rolled.retention_days, int)
    d = config_diff(AlphaConfig(retention_days=1), AlphaConfig(retention_days=2))
    assert d["count"] >= 1


def test_upgrade_preflight_and_local_fixture(env, tmp_path):
    pre = upgrade_preflight()
    assert pre["remote_fetch"] is False
    assert pre["production_authorized"] is False
    fix = tmp_path / "fixture"
    fix.mkdir()
    (fix / "release_fixture.json").write_text(
        json.dumps({"target_version": "0.1.0-private-alpha.1-fixture"}),
        encoding="utf-8",
    )
    db = tmp_path / "upgrade.db"
    r = apply_local_upgrade(fixture_dir=fix, work_db=db)
    assert r["ok"] is True
    assert r["remote_fetch"] is False


# ── M161 backup/restore ──────────────────────────────────────────────────────
def test_system_backup_restore_dr_and_gates(env, tmp_path):
    platform, token, ctx, core, tmp = env
    db = Path(platform.store.db_path)
    bak = tmp_path / "backups"
    b = create_system_backup(
        dest_dir=bak, label="test", db_path=db, include_legacy_app_dbs=False
    )
    assert b["excludes_secrets"] is True
    assert Path(b["archive"]).is_file()
    v = verify_system_backup(b["archive"])
    assert v["ok"] is True
    d = dry_run_restore(b["archive"])
    assert d["would_restore"] is True
    assert d["live_data_touched"] is False

    isolated = tmp_path / "restore"
    r = restore_system_backup(b["archive"], target=isolated)
    assert r["ok"] is True
    assert r["isolated"] is True

    # corrupt reject
    corrupt = bak / "bad.tar.gz"
    corrupt.write_bytes(b"nope")
    assert verify_system_backup(corrupt)["ok"] is False

    # wrong version
    bad = restore_system_backup(
        b["archive"], target=tmp_path / "wv", expect_format_version="nope.v0"
    )
    assert bad.get("error") == "WRONG_VERSION"

    # destructive without approval
    live = tmp_path / "live.db"
    live.write_bytes(db.read_bytes())
    with pytest.raises(RuntimeError):
        restore_system_backup(
            b["archive"],
            target=live,
            live_db=live,
            destructive_overwrite=True,
            approval_token="wrong",
        )

    drill = disaster_recovery_drill(work_dir=tmp_path / "dr", db_path=db)
    assert drill["ok"] is True
    assert drill["verdict"] == "PRIVATE_ALPHA_DR_DRILL_PASSED"


# ── M162 automations ─────────────────────────────────────────────────────────
def test_automations_disabled_by_default_and_bounded_exec(env):
    platform, token, ctx, core, tmp = env
    auto = core.create_automation(
        ctx,
        name="Daily HCG",
        schedule="daily",
        action="hcg_daily_summary",
        app_scope="hcg",
        requires_approval=True,
    )["automation"]
    assert auto["enabled"] is False
    assert auto["bypass_gateway"] is False
    assert auto["self_approve"] is False
    assert auto["direct_tool_execution"] is False

    svc = AutomationExecutionService(platform, core)
    posture = svc.security_posture()
    assert posture["default_enabled"] is False
    assert posture["self_approve"] is False
    assert posture["arbitrary_shell"] is False

    # global off → blocked
    cfg = load_config()
    cfg.automation_execution_enabled = False
    save_config(cfg)
    svc.enable(ctx, auto["automation_id"])
    blocked_global = svc.execute(ctx, auto["automation_id"], approve=True)
    assert blocked_global["state"] == "BLOCKED_POLICY"

    cfg.automation_execution_enabled = True
    save_config(cfg)

    need_appr = svc.execute(ctx, auto["automation_id"], approve=False)
    assert need_appr["state"] == "BLOCKED_APPROVAL"

    ok = svc.execute(ctx, auto["automation_id"], approve=True, idempotency_suffix="t1")
    assert ok["ok"] is True
    assert ok["plan_validator"] is True
    assert ok["execution_gateway"] is True
    assert ok["self_approve"] is False

    # overlap prevention while forced RUNNING
    runs = svc.list_runs(ctx)["runs"]
    # inject running
    from saathi.platform.private_alpha.automations import RUNS_KEY

    running = dict(runs[0])
    running["run_id"] = "arun_overlap"
    running["state"] = "RUNNING"
    running["automation_id"] = auto["automation_id"]
    platform.store.set_config(RUNS_KEY, [running], updated_by="test")
    overlap = svc.execute(ctx, auto["automation_id"], approve=True, idempotency_suffix="t2")
    assert overlap["error"] == "OVERLAP_PREVENTED"

    # cancel
    cancelled = svc.cancel_run(ctx, "arun_overlap")
    assert cancelled["run"]["state"] == "CANCELLED"

    # forbidden action via validate path
    bad = core.create_automation(
        ctx, name="Shell", schedule="manual", action="arbitrary_shell"
    )["automation"]
    v = svc.validate(ctx, bad["automation_id"])
    assert v["valid"] is False


# ── M163 operator validation ─────────────────────────────────────────────────
def test_synthetic_operator_validation(env):
    platform, token, ctx, core, tmp = env
    report = run_synthetic_operator_validation(platform, token)
    assert report["synthetic_validation"] is True
    assert report["human_feedback"] is False
    assert report["ok"] is True
    assert report["journeys"]["search"] is True
    assert report["journeys"]["yeti"] is True
    assert report["journeys"]["automation"] is True


# ── M164 support + incidents ─────────────────────────────────────────────────
def test_support_bundle_privacy_and_playbooks(tmp_path):
    r = export_support_bundle(dest_dir=tmp_path / "sup")
    assert r["privacy_scan_clean"] is True
    assert r["includes_secrets"] is False
    assert Path(r["archive"]).is_file()
    with tarfile.open(r["archive"], "r:gz") as tar:
        names = tar.getnames()
        assert any(n.endswith("PRIVACY.txt") for n in names)
        for m in tar.getmembers():
            if m.isfile():
                f = tar.extractfile(m)
                assert f is not None
                data = f.read().decode("utf-8", errors="replace")
                assert "sk-" not in data.lower() or "[REDACTED]" in data
    assert len(INCIDENT_PLAYBOOKS) >= 15
    pb = playbook_for("unexpected_public_listener")
    assert pb["severity"] == "critical"
    assert "detection" in pb and "escalation_boundary" in pb


# ── M165 certification gate ──────────────────────────────────────────────────
def test_private_alpha_certification_gate(env):
    platform, token, ctx, core, tmp = env
    report = run_private_alpha_certification(
        platform=platform, token=token, write_evidence=False
    )
    assert report["production_authorized"] is False
    assert report["public_exposure_authorized"] is False
    assert report["fail_count"] == 0
    assert report["verdict"] == "PRIVATE_ALPHA_READY_WITH_LIMITATIONS"
    assert report["trading_guardian"] == "UNCHANGED / UNENGAGED"
    assert report["disaster_recovery"] == "PRIVATE_ALPHA_DR_DRILL_PASSED"


def test_doctor_no_public_saathi_listeners():
    d = doctor()
    assert d.get("public_listener_regression") is False


def test_m148_automation_still_dry_run(env):
    platform, token, ctx, core, tmp = env
    auto = core.create_automation(
        ctx, name="Dry", schedule="daily_morning", action="summarize"
    )
    dry = core.run_automation_dry(ctx, auto["automation"]["automation_id"])
    assert dry["proposal"]["executed"] is False
    assert dry["proposal"]["bypass_gateway"] is False
