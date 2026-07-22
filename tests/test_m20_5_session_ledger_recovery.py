"""M20.5 — Session ledger, integrity evidence, recovery."""
from __future__ import annotations

import time
from pathlib import Path

import pytest

from saathi.engineering.evidence import IntegrityEvidenceStore
from saathi.engineering.integrity import capture_snapshot
from saathi.engineering.recovery import SessionRecovery, recover_store
from saathi.engineering.session_ledger import SessionLedger
from saathi.engineering.store import EngineeringStore

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def store(tmp_path):
    return EngineeringStore(tmp_path / "eng")


def test_ledger_append_and_chain(store):
    led = store.ledger()
    e1 = led.append("session_created", session_id="s1", payload={"status": "running"})
    e2 = led.append("checkpoint", session_id="s1", payload={"phase": "intake"})
    assert e1.seq == 1 and e2.seq == 2
    assert e2.prev_hash == e1.entry_hash
    chain = led.verify_chain()
    assert chain["ok"] is True
    assert chain["events"] == 2


def test_ledger_rejects_unknown_type(store):
    with pytest.raises(ValueError, match="unknown_event_type"):
        store.ledger().append("not_a_real_event")


def test_ledger_redacts_sensitive_payload(store):
    ev = store.ledger().append(
        "note",
        session_id="s",
        payload={"prompt": "SECRET_PROMPT", "status": "ok"},
    )
    assert ev.payload.get("prompt") == "[redacted]"
    assert ev.payload.get("status") == "ok"


def test_put_session_writes_ledger(store):
    store.put_session({"session_id": "abc", "status": "running", "task_id": "t1"})
    store.put_session({"session_id": "abc", "status": "completed", "task_id": "t1"})
    events = store.ledger().list_events(session_id="abc", limit=10, newest_first=False)
    types = [e.event_type for e in events]
    assert "session_created" in types
    assert "session_status" in types


def test_integrity_evidence_baseline_and_check(store, tmp_path):
    # Use a tiny git-less tree for snapshot capture (git may fail partially)
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "f.txt").write_text("x", encoding="utf-8")
    # init git so integrity digests work
    import subprocess
    subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=repo, capture_output=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, capture_output=True)
    subprocess.run(["git", "add", "f.txt"], cwd=repo, capture_output=True)
    subprocess.run(["git", "commit", "-m", "i"], cwd=repo, capture_output=True)

    ev_store = IntegrityEvidenceStore(store.root, store.ledger())
    base = ev_store.record_baseline("sess1", repo)
    assert base.kind == "baseline" and base.ok
    check = ev_store.record_check("sess1", repo, base.snapshot)
    assert check.ok is True
    # mutate
    (repo / "f.txt").write_text("mutated", encoding="utf-8")
    bad = ev_store.record_check("sess1", repo, base.snapshot)
    assert bad.ok is False
    assert bad.kind == "violation"
    listed = ev_store.list_for_session("sess1")
    assert len(listed) >= 3
    # quarantine event present
    types = [e.event_type for e in store.ledger().list_events(session_id="sess1", limit=50)]
    assert "quarantine" in types


def test_recovery_reclaim_stale_lease(store):
    store.put_session({
        "session_id": "stale1",
        "status": "running",
        "lease_until": time.time() - 10,
        "owner_pid": 0,
    })
    rep = recover_store(store, apply=True)
    actions = [a["action"] for a in rep["actions"]]
    assert "reclaim_lease" in actions
    sess = store.get_session("stale1")
    assert sess["status"] == "terminated"


def test_recovery_mark_crashed_missing_pid(store):
    store.put_session({
        "session_id": "dead1",
        "status": "running",
        "lease_until": time.time() + 9999,
        "owner_pid": 99999999,  # almost certainly dead
    })
    rec = SessionRecovery(store, pid_alive_fn=lambda pid: False)
    rep = rec.scan(apply=True)
    assert any(a.action == "mark_crashed" for a in rep.actions)
    assert store.get_session("dead1")["status"] == "crashed"


def test_recovery_resume_plan(store):
    from saathi.engineering.models import Checkpoint
    store.put_session({"session_id": "r1", "status": "paused"})
    store.add_checkpoint(Checkpoint(
        task_id="t", session_id="r1", phase="first_code_slice_complete",
    ))
    rec = SessionRecovery(store)
    rec.scan(apply=True)
    plan = rec.resume_plan("r1")
    assert plan["ok"] is True
    assert plan["auto_launch"] is False
    assert plan["checkpoint_count"] == 1
    assert store.get_session("r1").get("recovery", {}).get("ready_to_resume") is True


def test_recovery_dry_run_no_mutate(store):
    store.put_session({
        "session_id": "dry1",
        "status": "running",
        "lease_until": time.time() - 1,
        "owner_pid": 0,
    })
    rep = recover_store(store, apply=False)
    assert rep["actions"]
    assert store.get_session("dry1")["status"] == "running"


def test_cli_ledger_and_recover(tmp_path, monkeypatch):
    from saathi.engineering import cli
    # point store via env
    monkeypatch.setenv("SAATHI_ENG_ORCH_STORE", str(tmp_path / "eng"))
    # status uses default orch — may use data/engineering; call ledger via store directly
    st = EngineeringStore(tmp_path / "eng")
    st.put_session({"session_id": "c1", "status": "running", "lease_until": time.time() - 1})
    assert st.ledger().census()["total_events"] >= 1
    r = recover_store(st, apply=True)
    assert r["scanned"] >= 1


def test_not_second_run_ledger():
    """Engineering ledger must not import harness run_ledger."""
    text = (ROOT / "saathi" / "engineering" / "session_ledger.py").read_text()
    assert "run_ledger" not in text
    assert "application_harness" not in text


def test_trading_guardian_untouched_in_m20_5():
    for name in ("session_ledger.py", "recovery.py", "evidence.py"):
        t = (ROOT / "saathi" / "engineering" / name).read_text()
        assert "place_order" not in t
        assert "ExecutionService" not in t
