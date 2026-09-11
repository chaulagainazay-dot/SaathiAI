"""FM-I3 — Durable harness session, event, recovery, and inspection replay."""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from pathlib import Path

import pytest

from saathi.agent_runtime.harness import (
    PRODUCTION_CERTIFIED,
    ApprovalRefState,
    FakeInMemoryHarness,
    FakeScenario,
    HarnessBudget,
    HarnessDurableStore,
    HarnessError,
    HarnessErrorCode,
    HarnessSessionController,
    RecoveryDisposition,
    SCHEMA_VERSION,
    SOURCE_OF_TRUTH,
    TerminalOutcome,
)
from saathi.agent_runtime.harness.persistence import (
    DurableEventRecord,
    DurableSessionRecord,
    RetentionClass,
)
from saathi.agent_runtime.models import RunState


def _corr() -> str:
    return str(uuid.uuid4())


def _ctrl(tmp_path, scenario=FakeScenario.TEXT_COMPLETION, **kw):
    store = HarnessDurableStore(tmp_path / "harness.db", stale_after_sec=3600)
    fake = FakeInMemoryHarness(default_scenario=scenario)
    ctrl = HarnessSessionController(
        fake,
        durable_store=store,
        use_real_gateway=True,
        max_sessions=20,
        **kw,
    )
    return ctrl, fake, store


def _start(ctrl, **overrides):
    params = dict(
        run_id="run-d1",
        actor_id="actor-d",
        correlation_id=_corr(),
        mission_id="mission-d1",
        organization_id="org-d",
        workspace_id="ws-d",
        allowed_tool_names=("fake.echo", "fake.sensitive_read"),
        budget=HarnessBudget(max_turns=8, max_events=100),
    )
    params.update(overrides)
    return ctrl.start_session(**params)


# ── Baseline / authority ────────────────────────────────────────────────────


def test_source_of_truth_matrix_complete():
    required = {
        "run_lifecycle",
        "harness_session_projection",
        "normalized_harness_events",
        "tool_intent",
        "execution_record",
        "approval_status",
        "audit_record",
        "certification_status",
    }
    assert required <= set(SOURCE_OF_TRUTH)
    assert SOURCE_OF_TRUTH["tool_intent"]["fm_i3"] == "nothing (no ToolIntent body stored)"
    assert "projection" in SOURCE_OF_TRUTH["run_lifecycle"]["fm_i3"]
    assert PRODUCTION_CERTIFIED is False


def test_schema_version_pinned():
    assert SCHEMA_VERSION == "1.0"


# ── Session + event durability ──────────────────────────────────────────────


def test_session_and_events_persisted_on_lifecycle(tmp_path):
    ctrl, fake, store = _ctrl(tmp_path)
    h = _start(ctrl, session_id="dur-1")
    rec = store.get_session("dur-1")
    assert rec is not None
    assert rec.run_id == "run-d1"
    assert rec.organization_id == "org-d"
    assert rec.verify_integrity()
    ctrl.submit_turn(h.session_id, input_text="hello", correlation_id=_corr())
    events = store.list_events("dur-1")
    assert len(events) >= 3
    assert all(e.verify_integrity() for e in events)
    # Monotonic sequence
    assert [e.sequence_number for e in events] == list(range(1, len(events) + 1))
    rec2 = store.get_session("dur-1")
    assert rec2.last_event_sequence == len(events)
    assert rec2.last_event_id == events[-1].event_id


def test_transactional_watermark_no_divergence(tmp_path):
    store = HarnessDurableStore(tmp_path / "w.db")
    s = DurableSessionRecord(
        session_id="s1",
        harness_id="fake",
        run_id="r1",
        mission_id="m1",
        organization_id="o",
        workspace_id="w",
        actor_id="a",
        projected_harness_state="READY",
        authoritative_run_state_snapshot="running",
    )
    store.create_session(s)
    # Force sequence gap → fail and no partial write
    bad = DurableEventRecord(
        event_id="e-gap",
        session_id="s1",
        sequence_number=5,
        event_type="WARNING",
        harness_id="fake",
        timestamp=time.time(),
        payload={"msg": "gap"},
    )
    with pytest.raises(HarnessError) as ei:
        store.append_event("s1", bad)
    assert ei.value.code == HarnessErrorCode.PROTOCOL_VIOLATION
    assert store.event_count("s1") == 0
    assert store.get_session("s1").last_event_sequence == 0


def test_no_duplicate_event_id_or_sequence(tmp_path):
    store = HarnessDurableStore(tmp_path / "dup.db")
    store.create_session(
        DurableSessionRecord(
            session_id="s1",
            harness_id="fake",
            run_id="r",
            mission_id="m",
            organization_id="o",
            workspace_id="w",
            actor_id="a",
            projected_harness_state="READY",
            authoritative_run_state_snapshot="running",
        )
    )
    e1 = DurableEventRecord(
        event_id="same",
        session_id="s1",
        sequence_number=1,
        event_type="SESSION_STARTED",
        harness_id="fake",
        timestamp=1.0,
        payload={},
    )
    store.append_event("s1", e1)
    e2 = DurableEventRecord(
        event_id="same",
        session_id="s1",
        sequence_number=2,
        event_type="SESSION_READY",
        harness_id="fake",
        timestamp=2.0,
        payload={},
    )
    with pytest.raises(Exception):
        store.append_event("s1", e2)


def test_banned_payload_keys_fail_closed(tmp_path):
    store = HarnessDurableStore(tmp_path / "ban.db")
    store.create_session(
        DurableSessionRecord(
            session_id="s1",
            harness_id="fake",
            run_id="r",
            mission_id="m",
            organization_id="o",
            workspace_id="w",
            actor_id="a",
            projected_harness_state="READY",
            authoritative_run_state_snapshot="running",
        )
    )
    e = DurableEventRecord(
        event_id="e1",
        session_id="s1",
        sequence_number=1,
        event_type="TEXT_DELTA",
        harness_id="fake",
        timestamp=1.0,
        payload={"chain_of_thought": "secret"},
    )
    with pytest.raises(HarnessError):
        store.append_event("s1", e)
    assert store.event_count("s1") == 0


def test_scope_mismatch_on_event_rejected(tmp_path):
    store = HarnessDurableStore(tmp_path / "scope.db")
    store.create_session(
        DurableSessionRecord(
            session_id="s1",
            harness_id="fake",
            run_id="r1",
            mission_id="m1",
            organization_id="org-a",
            workspace_id="ws-a",
            actor_id="a",
            projected_harness_state="READY",
            authoritative_run_state_snapshot="running",
        )
    )
    e = DurableEventRecord(
        event_id="e1",
        session_id="s1",
        sequence_number=1,
        event_type="WARNING",
        harness_id="fake",
        timestamp=1.0,
        payload={},
        organization_id="org-EVIL",
        workspace_id="ws-a",
        run_id="r1",
    )
    with pytest.raises(HarnessError) as ei:
        store.append_event("s1", e)
    assert ei.value.code == HarnessErrorCode.SCOPE_MISMATCH


# ── Restart recovery ────────────────────────────────────────────────────────


def test_restart_recovery_terminal_completed(tmp_path):
    ctrl, fake, store = _ctrl(tmp_path)
    h = _start(ctrl, session_id="rec-term")
    ctrl.submit_turn(h.session_id, input_text="done", correlation_id=_corr())
    ctrl.close_session(h.session_id)
    # New controller, same store (process restart simulation)
    ctrl2 = HarnessSessionController(
        FakeInMemoryHarness(),
        durable_store=store,
        use_real_gateway=True,
    )
    result = ctrl2.recover_session("rec-term")
    assert result.disposition is RecoveryDisposition.RECOVER_TERMINAL
    assert result.can_continue is False
    assert result.events_count >= 1


def test_restart_recovery_cancelled_no_resume(tmp_path):
    ctrl, _, store = _ctrl(tmp_path, FakeScenario.MULTI_TURN)
    h = _start(ctrl, session_id="rec-cancel")
    ctrl.submit_turn(h.session_id, input_text="a", correlation_id=_corr())
    ctrl.request_cancel(h.session_id, reason="stop")
    ctrl2 = HarnessSessionController(
        FakeInMemoryHarness(), durable_store=store, use_real_gateway=True
    )
    result = ctrl2.recover_session("rec-cancel")
    assert result.disposition is RecoveryDisposition.RECOVER_CANCELLED
    assert result.can_continue is False


def test_recovery_waiting_for_approval(tmp_path):
    ctrl, _, store = _ctrl(tmp_path, FakeScenario.APPROVAL_REQUIRED)
    h = _start(ctrl, session_id="rec-apr")
    ctrl.submit_turn(h.session_id, input_text="sens", correlation_id=_corr())
    rec = store.get_session("rec-apr")
    assert rec.pending_execution_id or rec.pending_approval_reference
    ctrl2 = HarnessSessionController(
        FakeInMemoryHarness(), durable_store=store, use_real_gateway=True
    )
    result = ctrl2.recover_session("rec-apr")
    assert result.disposition is RecoveryDisposition.RECOVER_WAITING_FOR_APPROVAL
    assert result.can_continue is False


def test_recovery_stale_quarantine(tmp_path):
    store = HarnessDurableStore(tmp_path / "stale.db", stale_after_sec=10.0)
    store.create_session(
        DurableSessionRecord(
            session_id="stale-1",
            harness_id="fake",
            run_id="r",
            mission_id="m",
            organization_id="o",
            workspace_id="w",
            actor_id="a",
            projected_harness_state="READY",
            authoritative_run_state_snapshot="running",
        )
    )
    store.append_event(
        "stale-1",
        DurableEventRecord(
            event_id="e1",
            session_id="stale-1",
            sequence_number=1,
            event_type="SESSION_READY",
            harness_id="fake",
            timestamp=time.time(),
            payload={},
        ),
        projected_harness_state="READY",
    )
    # Simulate wall-clock far beyond stale_after_sec without rewriting integrity.
    result = store.recover_session("stale-1", now=time.time() + 1000)
    assert result.disposition is RecoveryDisposition.QUARANTINE_STALE
    assert result.can_continue is False


def test_recovery_corrupt_integrity(tmp_path):
    store = HarnessDurableStore(tmp_path / "corr.db")
    store.create_session(
        DurableSessionRecord(
            session_id="c1",
            harness_id="fake",
            run_id="r",
            mission_id="m",
            organization_id="o",
            workspace_id="w",
            actor_id="a",
            projected_harness_state="READY",
            authoritative_run_state_snapshot="running",
        )
    )
    # Tamper DB integrity hash
    with sqlite3.connect(str(tmp_path / "corr.db")) as c:
        c.execute(
            "UPDATE harness_session SET integrity_hash=? WHERE session_id=?",
            ("deadbeef", "c1"),
        )
        c.commit()
    result = store.recover_session("c1")
    assert result.disposition is RecoveryDisposition.QUARANTINE_CORRUPT


def test_recovery_authority_conflict_missing_execution(tmp_path):
    store = HarnessDurableStore(tmp_path / "orph.db")
    store.create_session(
        DurableSessionRecord(
            session_id="o1",
            harness_id="fake",
            run_id="r",
            mission_id="m",
            organization_id="o",
            workspace_id="w",
            actor_id="a",
            projected_harness_state="WAITING_FOR_APPROVAL",
            authoritative_run_state_snapshot="awaiting_approval",
            pending_execution_id="exec-missing",
            pending_approval_reference="apr-1",
        )
    )
    result = store.recover_session("o1", execution_exists=False)
    assert result.disposition is RecoveryDisposition.QUARANTINE_AUTHORITY_CONFLICT


def test_rebind_rejects_quarantined(tmp_path):
    store = HarnessDurableStore(tmp_path / "q.db")
    store.create_session(
        DurableSessionRecord(
            session_id="q1",
            harness_id="fake",
            run_id="r",
            mission_id="m",
            organization_id="o",
            workspace_id="w",
            actor_id="a",
            projected_harness_state="READY",
            authoritative_run_state_snapshot="running",
        )
    )
    store.mark_quarantine("q1", "test")
    ctrl = HarnessSessionController(
        FakeInMemoryHarness(), durable_store=store, use_real_gateway=True
    )
    with pytest.raises(HarnessError) as ei:
        ctrl.rebind_recovered_session("q1")
    assert ei.value.code == HarnessErrorCode.QUARANTINED


# ── Inspection replay ───────────────────────────────────────────────────────


def test_inspection_replay_no_execution(tmp_path):
    ctrl, _, store = _ctrl(tmp_path)
    h = _start(ctrl, session_id="replay-1")
    ctrl.submit_turn(h.session_id, input_text="hi", correlation_id=_corr())
    timeline = ctrl.replay_session("replay-1")
    assert timeline["ok"] is True
    assert timeline["can_execute"] is False
    assert timeline["replay_kind"] == "inspection"
    assert timeline["event_count"] >= 1
    # Gateway not invoked by replay
    before = len(ctrl.gateway.submitted)
    ctrl.replay_session("replay-1")
    assert len(ctrl.gateway.submitted) == before


def test_replay_detects_watermark_mismatch(tmp_path):
    store = HarnessDurableStore(tmp_path / "wm.db")
    store.create_session(
        DurableSessionRecord(
            session_id="s1",
            harness_id="fake",
            run_id="r",
            mission_id="m",
            organization_id="o",
            workspace_id="w",
            actor_id="a",
            projected_harness_state="READY",
            authoritative_run_state_snapshot="running",
        )
    )
    store.append_event(
        "s1",
        DurableEventRecord(
            event_id="e1",
            session_id="s1",
            sequence_number=1,
            event_type="SESSION_READY",
            harness_id="fake",
            timestamp=1.0,
            payload={},
        ),
    )
    # Tamper watermark without matching events
    with sqlite3.connect(str(tmp_path / "wm.db")) as c:
        c.execute(
            "UPDATE harness_session SET last_event_sequence=9 WHERE session_id='s1'"
        )
        # Fix integrity will fail anyway
        c.commit()
    # Re-seal won't match — recovery/replay should fail integrity first
    timeline = store.replay_timeline("s1")
    assert timeline["ok"] is False


# ── Persistence failure fail-closed ─────────────────────────────────────────


def test_controller_fails_closed_without_silently_dropping_store(tmp_path):
    ctrl, _, store = _ctrl(tmp_path)
    h = _start(ctrl, session_id="fc-1")
    # Closing store path by using invalid append via direct store after close
    ctrl.close_session(h.session_id)
    rec = store.get_session("fc-1")
    assert rec.closed is True
    with pytest.raises(HarnessError):
        store.append_event(
            "fc-1",
            DurableEventRecord(
                event_id="late",
                session_id="fc-1",
                sequence_number=rec.last_event_sequence + 1,
                event_type="TEXT_DELTA",
                harness_id="fake",
                timestamp=time.time(),
                payload={"text": "late"},
            ),
        )


def test_require_durable_store_flag():
    with pytest.raises(HarnessError):
        HarnessSessionController(
            FakeInMemoryHarness(),
            require_durable_store=True,
            durable_store=None,
        )


# ── Resource snapshot / approval refs ───────────────────────────────────────


def test_resource_snapshot_survives_restart(tmp_path):
    ctrl, _, store = _ctrl(tmp_path, FakeScenario.MULTI_TURN)
    h = _start(ctrl, session_id="res-1")
    ctrl.submit_turn(h.session_id, input_text="t1", correlation_id=_corr())
    rec = store.get_session("res-1")
    assert rec.resource_usage_snapshot.get("turns", 0) >= 1
    # Restart
    ctrl2 = HarnessSessionController(
        FakeInMemoryHarness(), durable_store=store, use_real_gateway=True
    )
    rec2 = store.get_session("res-1")
    assert rec2.resource_usage_snapshot.get("turns") == rec.resource_usage_snapshot.get("turns")
    result = ctrl2.recover_session("res-1")
    assert result.session is not None


def test_approval_reference_persisted(tmp_path):
    ctrl, _, store = _ctrl(tmp_path, FakeScenario.APPROVAL_REQUIRED)
    h = _start(ctrl, session_id="apr-ref")
    ctrl.submit_turn(h.session_id, input_text="s", correlation_id=_corr())
    rec = store.get_session("apr-ref")
    assert rec.pending_approval_reference.startswith("apr-") or rec.pending_execution_id


# ── Retention purge ─────────────────────────────────────────────────────────


def test_purge_expired_respects_pending_and_quarantine(tmp_path):
    store = HarnessDurableStore(tmp_path / "purge.db")
    now = time.time()
    # Expired completed — purgable
    store.create_session(
        DurableSessionRecord(
            session_id="p1",
            harness_id="fake",
            run_id="r",
            mission_id="m",
            organization_id="o",
            workspace_id="w",
            actor_id="a",
            projected_harness_state="COMPLETED",
            authoritative_run_state_snapshot="completed",
            terminal_outcome=TerminalOutcome.COMPLETED.value,
            retention_class=RetentionClass.COMPLETED.value,
            expires_at=now - 10,
            closed=True,
        )
    )
    # Expired but pending approval — not purgable
    store.create_session(
        DurableSessionRecord(
            session_id="p2",
            harness_id="fake",
            run_id="r2",
            mission_id="m2",
            organization_id="o",
            workspace_id="w",
            actor_id="a",
            projected_harness_state="WAITING_FOR_APPROVAL",
            authoritative_run_state_snapshot="awaiting_approval",
            pending_approval_reference="apr-x",
            expires_at=now - 10,
        )
    )
    # Quarantined — hold
    store.create_session(
        DurableSessionRecord(
            session_id="p3",
            harness_id="fake",
            run_id="r3",
            mission_id="m3",
            organization_id="o",
            workspace_id="w",
            actor_id="a",
            projected_harness_state="FAILED",
            authoritative_run_state_snapshot="failed",
            quarantined=True,
            quarantine_reason="hold",
            retention_class=RetentionClass.QUARANTINED.value,
            expires_at=now - 10,
        )
    )
    purged = store.purge_expired(now=now)
    assert "p1" in purged
    assert "p2" not in purged
    assert "p3" not in purged


# ── Security ────────────────────────────────────────────────────────────────


def test_no_toolintent_or_credentials_in_store(tmp_path):
    ctrl, _, store = _ctrl(tmp_path, FakeScenario.TOOL_THEN_CONTINUE)
    h = _start(ctrl, session_id="sec-1")
    ctrl.submit_turn(h.session_id, input_text="tool", correlation_id=_corr())
    raw = (tmp_path / "harness.db").read_bytes()
    assert b"api_key" not in raw
    assert b"password" not in raw
    assert b"chain_of_thought" not in raw
    # ToolIntent bodies not stored as full JSON blobs with private keys
    assert b"OPENAI" not in raw


def test_agent_session_adapter_untouched():
    eng = Path(__file__).resolve().parents[1] / "saathi" / "engineering"
    for p in eng.rglob("*.py"):
        body = p.read_text(encoding="utf-8", errors="replace")
        assert "HarnessDurableStore" not in body
        assert "agent_runtime.harness" not in body


def test_unsupported_schema_fails_closed(tmp_path):
    store = HarnessDurableStore(tmp_path / "sch.db")
    with pytest.raises(HarnessError):
        store.create_session(
            DurableSessionRecord(
                session_id="bad",
                harness_id="fake",
                run_id="r",
                mission_id="m",
                organization_id="o",
                workspace_id="w",
                actor_id="a",
                projected_harness_state="READY",
                authoritative_run_state_snapshot="running",
                schema_version="99.0",
            )
        )
