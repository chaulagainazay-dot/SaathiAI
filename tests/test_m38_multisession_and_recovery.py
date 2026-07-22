"""M38 — Multi-session coordinator, state machine, recovery (offline)."""
from __future__ import annotations

import json

import pytest

from saathi.credentials.backends import InMemoryTestSecretBackend
from saathi.credentials.m38 import (
    M38Error,
    MultiSessionCoordinator,
    SessionState,
    assert_transition,
    state_machine_spec,
    run_offline_multisession_validation,
    run_recovery_matrix,
    SYNTH_SECRET,
)
from saathi.credentials.m37 import fixture_transport


def test_valid_transitions():
    assert_transition(SessionState.CREATED.value, SessionState.AUTHORIZATION_PENDING.value)
    assert_transition(SessionState.RUNNING.value, SessionState.COMPLETED.value)
    assert_transition(SessionState.CLEANUP_PENDING.value, SessionState.CLEANED.value)


def test_invalid_transition_fails():
    with pytest.raises(M38Error) as e:
        assert_transition(SessionState.CREATED.value, SessionState.RUNNING.value)
    assert e.value.code == "invalid_state_transition"


def test_state_machine_spec_complete():
    spec = state_machine_spec()
    assert "CREATED" in spec["states"]
    assert "TERMINAL_FAILED" in spec["states"]
    assert "CLEANED" in spec["terminal"]


def test_start_session_success():
    c = MultiSessionCoordinator(clock=lambda: 1.0)
    out = c.start_session(credential_ref_id="cred1", session_id="s1")
    assert out["ok"] is True
    assert out["state"] == SessionState.CLEANED.value
    assert out["session"]["handle_closed"] is True
    assert out["session"]["credential_fingerprint"]


def test_no_secret_in_session_status():
    c = MultiSessionCoordinator(clock=lambda: 1.0)
    c.start_session(credential_ref_id="cred1", session_id="s1")
    st = c.session_status("s1")
    blob = json.dumps(st)
    assert SYNTH_SECRET not in blob
    assert "Bearer " not in blob


def test_concurrency_limit():
    c = MultiSessionCoordinator(concurrency_limit=1, clock=lambda: 1.0)
    with c._lock:  # noqa: SLF001
        c._active.add("held")  # noqa: SLF001
    with pytest.raises(M38Error) as e:
        c.start_session(credential_ref_id="x", session_id="s")
    assert e.value.code == "concurrency_limit"


def test_aggregate_budget():
    c = MultiSessionCoordinator(aggregate_call_budget=2, clock=lambda: 1.0)
    c.aggregate_calls_used = 2
    with pytest.raises(M38Error) as e:
        c.start_session(credential_ref_id="x", call_budget=2)
    assert e.value.code == "aggregate_call_budget_exhausted"


def test_session_id_collision():
    c = MultiSessionCoordinator(clock=lambda: 1.0)
    c.start_session(credential_ref_id="a", session_id="dup")
    with pytest.raises(M38Error) as e:
        c.start_session(credential_ref_id="b", session_id="dup")
    assert e.value.code == "session_id_collision"


def test_isolation_success_vs_failure():
    c = MultiSessionCoordinator(concurrency_limit=2, aggregate_call_budget=8, clock=lambda: 1.0)
    ok = c.start_session(credential_ref_id="ok", session_id="ok")
    bad = c.start_session(
        credential_ref_id="bad", session_id="bad",
        transport=fixture_transport(identity_status=401),
    )
    assert ok["ok"] is True
    assert bad["ok"] is False
    assert ok["session"]["state"] == SessionState.CLEANED.value


def test_independent_cleanup():
    c = MultiSessionCoordinator(clock=lambda: 1.0)
    c.start_session(credential_ref_id="a", session_id="a")
    c.start_session(credential_ref_id="b", session_id="b")
    c.cleanup_session("a")
    st_b = c.session_status("b")
    assert st_b["found"] is True
    assert st_b["session"]["state"] == SessionState.CLEANED.value


def test_duplicate_cleanup_idempotent():
    c = MultiSessionCoordinator(clock=lambda: 1.0)
    c.start_session(credential_ref_id="a", session_id="a")
    assert c.cleanup_session("a")["ok"]
    assert c.cleanup_session("a")["ok"]


def test_interrupt_recovery():
    c = MultiSessionCoordinator(clock=lambda: 1.0)
    out = c.start_session(credential_ref_id="a", session_id="int", interrupt_after="identity")
    assert out["session"]["handle_closed"] is True
    assert out["session"]["recovery_attempts"] >= 1
    assert out["session"]["state"] == SessionState.CLEANED.value


def test_recovery_no_secret_reopen():
    c = MultiSessionCoordinator(clock=lambda: 1.0)
    c.start_session(credential_ref_id="a", session_id="r", interrupt_after="authorization")
    rec = c.recover_session("r")
    assert rec.get("reauthorization_required_for_resume") is True or rec.get("idempotent")


def test_orphan_recovery():
    c = MultiSessionCoordinator(clock=lambda: 1.0)
    out = c.recover_session("missing")
    assert out["operator_action"] == "REVOKE_ORPHAN_LEASE_IF_PRESENT"


def test_reconcile():
    c = MultiSessionCoordinator(clock=lambda: 1.0)
    c.start_session(credential_ref_id="a", session_id="s", interrupt_after="qualification")
    r = c.reconcile()
    assert r["ok"] is True


def test_list_sessions():
    c = MultiSessionCoordinator(clock=lambda: 1.0)
    c.start_session(credential_ref_id="a", session_id="s1")
    lst = c.list_sessions()
    assert len(lst) == 1
    assert lst[0]["session_id"] == "s1"


def test_offline_multisession_validation_suite():
    rep = run_offline_multisession_validation()
    assert rep["failed"] == 0, json.dumps([r for r in rep["results"] if not r.get("pass")], indent=2)
    assert rep["leak_clean"] is True


def test_recovery_matrix():
    rep = run_recovery_matrix()
    assert rep["failed"] == 0, json.dumps([c for c in rep["cases"] if not c.get("pass")], indent=2)
