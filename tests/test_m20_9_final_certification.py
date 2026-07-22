"""M20.9 — Integration, authority-boundary, config, TG, recovery certification."""
from __future__ import annotations

import ast
import inspect
import time
from pathlib import Path

import pytest

from saathi.engineering.models import Checkpoint
from saathi.engineering.recovery import SessionRecovery, recover_store
from saathi.engineering.session_ledger import SessionLedger
from saathi.engineering.settings import load_settings
from saathi.engineering.store import EngineeringStore
from saathi.inference.caller_rollout import (
    CALLER_CHEAP_ASK,
    CALLER_PROSE_CLEAN,
    InfRolloutMode,
    resolve_mode,
)
from saathi.m20_console.flags import FLAG_CATALOG, disable_procedure, domains_isolated, flag_snapshot
from saathi.m20_console.status import m20_console_status

ROOT = Path(__file__).resolve().parents[1]


# ── M20.8 status ─────────────────────────────────────────────────────────

def test_m20_8_status_intentionally_skipped():
    p = ROOT / "docs" / "M20_8_STATUS.md"
    assert p.is_file()
    text = p.read_text(encoding="utf-8")
    assert "INTENTIONALLY_SKIPPED" in text
    assert "NOT" in text or "not" in text  # not falsely complete
    assert "cheap_ask" in text and "prose_clean" in text


# ── Authority boundaries ─────────────────────────────────────────────────

def test_console_cannot_mutate_engineering_store(tmp_path, monkeypatch):
    monkeypatch.setenv("SAATHI_ENG_ORCH_STORE", str(tmp_path / "eng"))
    st = EngineeringStore(tmp_path / "eng")
    st.put_session({"session_id": "s1", "status": "running"})
    before = st.get_session("s1")
    # console status must not change sessions
    m20_console_status()
    after = st.get_session("s1")
    assert before["status"] == after["status"]
    assert before.get("updated_at") == after.get("updated_at")


def test_console_source_has_no_store_writers():
    """m20_console modules must not call EngineeringStore mutators."""
    for name in ("status.py", "flags.py", "cli.py"):
        src = (ROOT / "saathi" / "m20_console" / name).read_text(encoding="utf-8")
        tree = ast.parse(src)
        # ban direct put_session / set_status calls in AST as attributes
        banned = {"put_session", "set_status", "add_item", "upsert_item", "put_approval"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                assert node.func.attr not in banned, f"{name} calls {node.func.attr}"


def test_engineering_does_not_import_ollama_engine():
    eng_root = ROOT / "saathi" / "engineering"
    for p in eng_root.rglob("*.py"):
        t = p.read_text(encoding="utf-8")
        assert "OllamaEngine" not in t
        assert "from saathi.inference.adapters" not in t


def test_inference_cannot_approve_engineering():
    # inference package must not create engineering approvals
    inf = ROOT / "saathi" / "inference"
    for p in inf.rglob("*.py"):
        t = p.read_text(encoding="utf-8")
        assert "create_readonly_approval" not in t
        assert "put_approval" not in t


def test_caller_flags_do_not_enable_engineering_writes(monkeypatch):
    monkeypatch.setenv("SAATHI_INF_ROLLOUT_CHEAP_ASK", "governed_local_only")
    monkeypatch.delenv("SAATHI_ENG_ORCH_WRITES", raising=False)
    s = load_settings()
    assert s.repository_writes_enabled is False
    assert resolve_mode(CALLER_CHEAP_ASK) == InfRolloutMode.GOVERNED_LOCAL_ONLY


def test_engineering_write_flag_does_not_change_rollout_default(monkeypatch):
    monkeypatch.setenv("SAATHI_ENG_ORCH_WRITES", "1")
    monkeypatch.setenv("SAATHI_ENG_ORCH_ENABLED", "1")
    monkeypatch.delenv("SAATHI_INF_ROLLOUT", raising=False)
    monkeypatch.delenv("SAATHI_INF_ROLLOUT_CHEAP_ASK", raising=False)
    # clear runtime overrides
    from saathi.inference.caller_rollout import clear_runtime_overrides
    clear_runtime_overrides()
    assert resolve_mode(CALLER_CHEAP_ASK) == InfRolloutMode.LEGACY
    assert resolve_mode(CALLER_PROSE_CLEAN) == InfRolloutMode.LEGACY


def test_no_direct_ollama_in_selected_callers():
    for rel in ("saathi/tools/cheap_llm.py", "saathi/tools/prose.py"):
        t = (ROOT / rel).read_text(encoding="utf-8")
        assert "11434" not in t
        assert "OllamaEngine" not in t


def test_chat_still_legacy_generate():
    # M21.3: chat compatibility adapter; legacy sink remains llm.generate inside adapter
    t = (ROOT / "saathi" / "chat" / "engine.py").read_text(encoding="utf-8")
    assert (
        "llm_mod.generate" in t
        or "chat_generate" in t
        or "chat_adapter" in t
    )


def test_domains_isolated_machine_checkable():
    d = domains_isolated()
    assert d["merged_store"] is False
    assert d["second_model_router"] is False
    assert d["second_execution_gateway"] is False
    assert d["trading_guardian_coupled"] is False


# ── Configuration ────────────────────────────────────────────────────────

def test_flag_catalog_required_keys():
    keys = {f.key for f in FLAG_CATALOG}
    for k in (
        "SAATHI_ENG_ORCH_ENABLED",
        "SAATHI_ENG_ORCH_WRITES",
        "SAATHI_ENG_ORCH_COMMITS",
        "SAATHI_ENG_ORCH_PUSHES",
        "SAATHI_INFERENCE_ENABLED",
        "SAATHI_INFERENCE_GATEWAY_ENABLED",
        "SAATHI_INF_ROLLOUT",
        "SAATHI_ALLOW_CLOUD_FALLBACK",
    ):
        assert k in keys


def test_defaults_safe_snapshot(monkeypatch):
    for f in FLAG_CATALOG:
        monkeypatch.delenv(f.key, raising=False)
    snap = flag_snapshot()
    # sensitive should not be "on" when unset
    assert snap["security_sensitive_enabled"] == [] or all(
        # if somehow present, fail
        False for _ in snap["security_sensitive_enabled"]
    )
    disable = disable_procedure()
    assert "SAATHI_ENG_ORCH_ENABLED" in disable["engineering_keys"]


def test_unknown_rollout_fails_closed():
    from saathi.inference.caller_rollout import set_runtime_mode
    with pytest.raises(ValueError):
        set_runtime_mode(CALLER_CHEAP_ASK, "totally_invalid_mode")


# ── Ledger / recovery ────────────────────────────────────────────────────

def test_ledger_chain_and_invalid_transition(tmp_path):
    led = SessionLedger(tmp_path)
    a = led.append("session_created", session_id="x")
    b = led.append("session_status", session_id="x", payload={"to": "running"})
    assert b.prev_hash == a.entry_hash
    assert led.verify_chain()["ok"] is True
    store = EngineeringStore(tmp_path)
    from saathi.engineering.models import EngineeringBacklogItem, ItemStatus
    store.add_item(EngineeringBacklogItem(
        item_id="i1", milestone_id="M20.9", title="t", status=ItemStatus.PROPOSED.value,
    ))
    store.set_status("i1", ItemStatus.READY)
    with pytest.raises(ValueError, match="invalid_status"):
        store.set_status("i1", ItemStatus.COMPLETED)


def test_recovery_stale_lease_and_resume(tmp_path):
    store = EngineeringStore(tmp_path)
    store.put_session({
        "session_id": "st", "status": "running",
        "lease_until": time.time() - 5, "owner_pid": 0,
    })
    rep = recover_store(store, apply=True)
    assert any(a["action"] == "reclaim_lease" for a in rep["actions"])
    store.put_session({"session_id": "p1", "status": "paused"})
    store.add_checkpoint(Checkpoint(task_id="t", session_id="p1", phase="intake_complete"))
    plan = SessionRecovery(store).resume_plan("p1")
    assert plan["auto_launch"] is False
    assert plan["ok"] is True


def test_integrity_evidence_linked(tmp_path):
    import subprocess
    repo = tmp_path / "r"
    repo.mkdir()
    (repo / "a.txt").write_text("a", encoding="utf-8")
    subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=repo, capture_output=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True)
    subprocess.run(["git", "commit", "-m", "i"], cwd=repo, capture_output=True)
    from saathi.engineering.evidence import IntegrityEvidenceStore
    store = EngineeringStore(tmp_path / "eng")
    ev = IntegrityEvidenceStore(store.root, store.ledger())
    base = ev.record_baseline("sess", repo)
    assert base.ok
    types = [e.event_type for e in store.ledger().list_events(session_id="sess", limit=20)]
    assert "integrity_baseline" in types


# ── Approval binding ─────────────────────────────────────────────────────

def test_readonly_approval_binds_and_rejects_wrong_branch(tmp_path):
    from saathi.engineering.approval import (
        create_readonly_approval,
        validate_approval,
    )
    store = EngineeringStore(tmp_path)
    ap = create_readonly_approval(
        store,
        repository="saathiai",
        branch="milestone/m7-security-engine",
        starting_commit="abc123",
        backlog_item_id="item1",
        provider="mock",
        prompt="plan only",
        validation_plan=["secret_scan"],
        ttl_sec=3600,
    )
    ok, reason, _ = validate_approval(
        store, ap.approval_id,
        repository="saathiai",
        branch="milestone/m7-security-engine",
        starting_commit="abc123",
        backlog_item_id="item1",
        provider="mock",
        prompt="plan only",
    )
    assert ok, reason
    bad, reason2, _ = validate_approval(
        store, ap.approval_id,
        repository="saathiai",
        branch="other-branch",
        starting_commit="abc123",
        backlog_item_id="item1",
        provider="mock",
        prompt="plan only",
    )
    assert not bad
    assert "branch" in reason2


# ── Fallback / blocked model ─────────────────────────────────────────────

def test_m20_6_blocked_documented_and_defaults_legacy():
    doc = (ROOT / "docs" / "M20_6_LIVE_CERT_RESULT.md").read_text(encoding="utf-8")
    assert "BLOCKED" in doc
    from saathi.inference.caller_rollout import clear_runtime_overrides
    clear_runtime_overrides()
    assert resolve_mode(CALLER_CHEAP_ASK).value == "legacy"


def test_hard_denials_never_fallback():
    from saathi.inference.caller_rollout import can_fallback, FALLBACK_DENIED
    for c in FALLBACK_DENIED:
        assert can_fallback(c) is False


# ── Trading Guardian ─────────────────────────────────────────────────────

def test_trading_guardian_isolation_report():
    from saathi.engineering.security import (
        assert_no_trading_imports,
        trading_guardian_isolation_report,
    )
    rep = trading_guardian_isolation_report()
    assert rep["engineering_can_execute_trades"] is False
    assert rep["kill_switch_independent"] is True
    assert assert_no_trading_imports(ROOT / "saathi" / "engineering") == []
    assert assert_no_trading_imports(ROOT / "saathi" / "m20_console") == []
    # inference must not import trade execution (denylist strings in skills_gate OK)
    for p in (ROOT / "saathi" / "inference").rglob("*.py"):
        t = p.read_text(encoding="utf-8")
        assert "from saathi.execution.trade" not in t
        assert "ExecutionService" not in t


def test_console_tg_unengaged():
    st = m20_console_status()
    assert st["trading_guardian"]["engaged"] is False


# ── Integration smoke ────────────────────────────────────────────────────

def test_m20_console_posture_schema():
    st = m20_console_status()
    assert st["schema"] == "m20_console_status.v1"
    assert "engineering" in st and "inference" in st
    assert st["domains_isolated"]["second_run_ledger"] is False
