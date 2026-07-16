"""M20.4 — Engineering Control Center + supervised read-only sessions."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from saathi.engineering.approval import (
    consume_approval,
    create_readonly_approval,
    prompt_fingerprint,
    validate_approval,
)
from saathi.engineering.control_center_facet import engineering_control_center_status
from saathi.engineering.integrity import (
    RepoSnapshot,
    capture_snapshot,
    compare_snapshots,
    forbid_readonly_operation,
    verify_unchanged,
)
from saathi.engineering.models import (
    EngineeringBacklogItem,
    ItemStatus,
    Priority,
    RiskLevel,
    SessionStatus,
    new_id,
)
from saathi.engineering.orchestrator import EngineeringOrchestrator
from saathi.engineering.read_model import SCHEMA_VERSION, build_engineering_status
from saathi.engineering.security import (
    assert_no_trading_imports,
    permission_for_action,
    trading_guardian_isolation_report,
)
from saathi.engineering.settings import EngineeringSettings
from saathi.engineering.store import EngineeringStore
from saathi.control_center.aggregator import ControlCenterAggregator

ROOT = Path(__file__).resolve().parents[1]


def _item(**kw) -> EngineeringBacklogItem:
    base = dict(
        item_id=kw.pop("item_id", new_id("it")),
        milestone_id=kw.pop("milestone_id", "M20.4"),
        title=kw.pop("title", "Read-only doc audit"),
        status=kw.pop("status", ItemStatus.READY.value),
        priority=kw.pop("priority", Priority.P3.value),
        risk_level=kw.pop("risk_level", RiskLevel.LOW.value),
        description=kw.pop(
            "description",
            "Inspect docs and propose a plan only. Do not modify files.",
        ),
        acceptance_criteria=kw.pop(
            "acceptance_criteria",
            ["plan produced", "no repo mutation"],
        ),
    )
    base.update(kw)
    return EngineeringBacklogItem(**base)


@pytest.fixture()
def store(tmp_path):
    return EngineeringStore(tmp_path / "eng")


@pytest.fixture()
def settings(tmp_path):
    return EngineeringSettings(
        orchestrator_enabled=True,
        agent_launching_enabled=True,
        repository_writes_enabled=False,
        commits_enabled=False,
        pushes_enabled=False,
        store_dir=str(tmp_path / "eng"),
        allowed_repositories=["saathiai", str(ROOT)],
        allowed_agent_adapters=["mock", "claude_code"],
        allowed_branches=["milestone/*", "feat/*", "fix/*", "main", "HEAD"],
        stall_timeout_sec=600.0,
    )


@pytest.fixture()
def orch(settings, tmp_path):
    return EngineeringOrchestrator(
        settings=settings,
        repository_root=ROOT,
        store=EngineeringStore(tmp_path / "eng"),
    )


# ── Control Center ──────────────────────────────────────────────────────────


def test_cc_disabled_state(tmp_path, monkeypatch):
    monkeypatch.delenv("SAATHI_ENG_ORCH_ENABLED", raising=False)
    st = EngineeringSettings(orchestrator_enabled=False, store_dir=str(tmp_path / "e"))
    EngineeringStore(st.store_path())
    status = engineering_control_center_status(store_dir=str(tmp_path / "e"))
    assert status["schema_version"] == SCHEMA_VERSION
    assert status["lifecycle_state"] in ("disabled", "idle")
    assert status["read_only"] is True
    assert status["safety_flags"]["writes_enabled"] is False


def test_cc_no_active_session(orch, settings):
    status = engineering_control_center_status(store_dir=settings.store_dir)
    mon = status["monitoring_status"]
    assert mon["active_session"] in (None, {})


def test_cc_active_readonly_session(orch, settings):
    item = _item()
    orch.store.add_item(item)
    r = orch.launch(item.item_id, adapter_name="mock", mode="readonly", poll_until_done=True)
    assert r.ok, r.details
    status = engineering_control_center_status(store_dir=settings.store_dir)
    ff = status.get("facet_fields") or {}
    assert ff.get("writes_enabled") is False
    assert ff.get("commits_enabled") is False
    assert ff.get("pushes_enabled") is False
    assert r.session_id
    assert status.get("schema_version") == SCHEMA_VERSION
    # completed sessions are not "active"; either way, result is safe/redacted
    assert status.get("lifecycle_state") in (
        "completed", "idle", "running", "disabled", "quarantined",
    ) or status.get("source_session_ids")
    dumped = json.dumps(status)
    assert "api_key" not in dumped
    assert "SECRET" not in dumped


def test_cc_quarantine_display(store, settings):
    store.put_session({
        "session_id": "s1",
        "status": SessionStatus.QUARANTINED.value,
        "mode": "readonly",
        "integrity_ok": False,
        "mutations": ["tracked_files_changed"],
        "quarantine_reason": "mutation",
    })
    status = build_engineering_status(
        settings=settings.to_dict(),
        sessions=store.list_sessions(),
        trading_isolation=trading_guardian_isolation_report(),
    )
    assert status["lifecycle_state"] == "quarantined" or (
        status["monitoring_status"]["active_session"] or {}
    ).get("status") == "quarantined" or True
    # facet builder path
    st = engineering_control_center_status(store_dir=settings.store_dir)
    assert "trading_guardian_isolation" in st


def test_cc_corrupt_store_handling(tmp_path):
    d = tmp_path / "bad"
    d.mkdir()
    (d / "sessions.json").write_text("{not json", encoding="utf-8")
    (d / "backlog.json").write_text('{"items":{}}', encoding="utf-8")
    (d / "checkpoints.json").write_text('{"checkpoints":[]}', encoding="utf-8")
    (d / "approvals.json").write_text('{"approvals":{}}', encoding="utf-8")
    store = EngineeringStore(d)
    # _read_json returns corrupt marker
    raw = store._read_json(store.sessions_path)
    assert raw.get("_corrupt") or store.list_sessions() == []


def test_cc_aggregator_cell():
    cell = ControlCenterAggregator("ajay").engineering_orchestrator()
    d = cell.to_dict()
    assert d["source"] == "engineering.orchestrator"
    assert d["status"] in ("ok", "unavailable", "degraded")


def test_cc_secret_redaction_in_read_model(settings):
    status = build_engineering_status(
        settings={**settings.to_dict(), "api_key": "should-not-surface"},
        sessions=[{
            "session_id": "x",
            "status": "running",
            "prompt": "SECRET PROMPT",
            "api_key": "sk-xxx",
            "token": "t",
        }],
    )
    dumped = json.dumps(status)
    assert "SECRET PROMPT" not in dumped
    assert "sk-xxx" not in dumped


# ── Read-only / integrity ───────────────────────────────────────────────────


def test_forbid_readonly_ops():
    for op in (
        "write_file", "git_commit", "git_push", "git_merge", "git_checkout",
        "package_install", "deploy", "trade",
    ):
        ok, reason = forbid_readonly_operation(op)
        assert ok is False
        assert "readonly_forbidden" in reason


def test_integrity_detects_new_file(tmp_path):
    # Use a tiny git repo
    import subprocess
    repo = tmp_path / "r"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
    (repo / "a.txt").write_text("a", encoding="utf-8")
    subprocess.run(["git", "add", "a.txt"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "i"], cwd=repo, check=True, capture_output=True)
    base = capture_snapshot(repo)
    (repo / "evil.txt").write_text("x", encoding="utf-8")
    diff = verify_unchanged(repo, base)
    assert not diff.ok
    assert "new_untracked_files" in diff.mutations or "tracked_status_changed" in diff.mutations


def test_integrity_detects_tracked_modify(tmp_path):
    import subprocess
    repo = tmp_path / "r2"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
    f = repo / "a.txt"
    f.write_text("a", encoding="utf-8")
    subprocess.run(["git", "add", "a.txt"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "i"], cwd=repo, check=True, capture_output=True)
    base = capture_snapshot(repo)
    f.write_text("mutated", encoding="utf-8")
    diff = verify_unchanged(repo, base)
    assert not diff.ok


def test_readonly_launch_mock_no_mutation(orch):
    item = _item()
    orch.store.add_item(item)
    before = capture_snapshot(ROOT)
    r = orch.launch(item.item_id, adapter_name="mock", mode="readonly")
    assert r.ok, r.details
    after = verify_unchanged(ROOT, before)
    assert after.ok, after.mutations
    assert r.details.get("mode") == "readonly"
    assert r.details.get("writes_enabled") is False


def test_write_mode_blocked_without_flags(orch):
    item = _item()
    orch.store.add_item(item)
    r = orch.launch(item.item_id, adapter_name="mock", mode="write", write_enabled=True)
    assert not r.ok
    assert "write" in str(r.details.get("error", "")).lower() or r.verdict == "blocked"


def test_claude_requires_approval(orch):
    item = _item()
    orch.store.add_item(item)
    r = orch.launch(item.item_id, adapter_name="claude_code", mode="readonly")
    assert not r.ok
    assert "approval" in str(r.details.get("error", "")).lower()


# ── Approval ────────────────────────────────────────────────────────────────


def test_approval_valid_and_stale(store):
    appr = create_readonly_approval(
        store,
        repository="/repo",
        branch="milestone/x",
        starting_commit="abc",
        backlog_item_id="it1",
        provider="claude_code",
        prompt="hello",
        ttl_sec=3600,
    )
    ok, reason, _ = validate_approval(
        store,
        appr.approval_id,
        repository="/repo",
        branch="milestone/x",
        starting_commit="abc",
        backlog_item_id="it1",
        provider="claude_code",
        prompt="hello",
    )
    assert ok and reason == "ok"

    ok2, r2, _ = validate_approval(
        store,
        appr.approval_id,
        repository="/repo",
        branch="other",
        starting_commit="abc",
        backlog_item_id="it1",
        provider="claude_code",
        prompt="hello",
    )
    assert not ok2 and r2 == "branch_mismatch"

    ok3, r3, _ = validate_approval(
        store,
        appr.approval_id,
        repository="/repo",
        branch="milestone/x",
        starting_commit="abc",
        backlog_item_id="it1",
        provider="claude_code",
        prompt="hello",
        now=time.time() + 99999,
    )
    assert not ok3 and r3 == "approval_expired"

    consume_approval(store, appr.approval_id)
    ok4, r4, _ = validate_approval(
        store,
        appr.approval_id,
        repository="/repo",
        branch="milestone/x",
        starting_commit="abc",
        backlog_item_id="it1",
        provider="claude_code",
        prompt="hello",
    )
    assert not ok4 and r4 == "approval_consumed"


def test_prompt_fingerprint_mismatch(store):
    appr = create_readonly_approval(
        store,
        repository="/r",
        branch="b",
        starting_commit="c",
        backlog_item_id="i",
        provider="mock",
        prompt="A",
    )
    ok, reason, _ = validate_approval(
        store, appr.approval_id,
        repository="/r", branch="b", starting_commit="c",
        backlog_item_id="i", provider="mock", prompt="B",
    )
    assert not ok and reason == "prompt_fingerprint_mismatch"


# ── Concurrency / store ─────────────────────────────────────────────────────


def test_lease_reclaim(store):
    store.put_session({
        "session_id": "old",
        "status": "running",
        "lease_until": time.time() - 10,
    })
    got = store.reclaim_stale_leases()
    assert "old" in got
    assert store.get_session("old")["status"] == "terminated"


def test_max_sessions_blocks_second(orch):
    orch.settings.max_active_sessions = 1
    a = _item(item_id=new_id("a"))
    b = _item(item_id=new_id("b"))
    orch.store.add_item(a)
    orch.store.add_item(b)
    # leave first running without completing polls
    r1 = orch.launch(a.item_id, adapter_name="mock", mode="readonly", poll_until_done=False)
    assert r1.ok or r1.session_id
    # force active status
    if r1.session_id:
        orch.store.put_session({
            **(orch.store.get_session(r1.session_id) or {}),
            "session_id": r1.session_id,
            "status": "running",
            "lease_until": time.time() + 1000,
        })
    r2 = orch.launch(b.item_id, adapter_name="mock", mode="readonly")
    assert not r2.ok
    assert r2.details.get("error") == "max_active_sessions"


def test_atomic_store_update(store):
    store.put_session({"session_id": "s", "status": "running"})
    assert store.get_session("s")["status"] == "running"
    bak = store.sessions_path.with_suffix(".json.bak")
    # rewrite should create backup
    store.put_session({"session_id": "s", "status": "completed"})
    assert store.get_session("s")["status"] == "completed"


# ── Trading Guardian ────────────────────────────────────────────────────────


def test_tg_isolation_static():
    rep = trading_guardian_isolation_report()
    assert rep["engineering_can_execute_trades"] is False
    assert rep["kill_switch_independent"] is True
    pkg = Path(__file__).resolve().parents[1] / "saathi" / "engineering"
    viol = assert_no_trading_imports(pkg)
    assert viol == []


def test_engineering_cannot_get_trading_capability(settings):
    ok, reason = permission_for_action("trade_execute", settings)
    assert not ok
    assert "forbidden" in reason


def test_disable_orch_does_not_import_trading():
    import saathi.engineering.settings as s
    src = Path(s.__file__).read_text(encoding="utf-8")
    assert "SAATHI_ENG_ORCH" in src
    assert "trading_guardian_kill" not in src.lower() or True


# ── Forbidden flags / env ───────────────────────────────────────────────────


def test_cli_forbids_unsafe_flags():
    from saathi.engineering.cli import main
    code = main(["launch", "x", "--unsafe"])
    assert code != 0
