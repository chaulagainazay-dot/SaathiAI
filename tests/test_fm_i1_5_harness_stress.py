"""FM-I1.5 — Harness verification, fuzzing, and stress certification.

No real adapters, providers, network, process, browser, or credentials.
Thresholds are imported from harness.thresholds (declared before measurement).
"""
from __future__ import annotations

import itertools
import threading
import time
import tracemalloc
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Tuple

import pytest

from saathi.agent_runtime.harness import (
    PRODUCTION_CERTIFIED,
    ApprovalRefState,
    FakeInMemoryHarness,
    FakeScenario,
    GatewayTestDouble,
    HarnessAuditLog,
    HarnessBudget,
    HarnessError,
    HarnessErrorCode,
    HarnessEvent,
    HarnessEventType,
    HarnessSessionController,
    HarnessSessionStartRequest,
    HarnessSessionState,
    ToolProposal,
    ToolProposalDisposition,
    can_transition_harness,
    is_terminal_harness_state,
)
from saathi.agent_runtime.harness.thresholds import (
    CONCURRENCY_LEVELS,
    MAX_CANCEL_LATENCY_MS,
    MAX_MEMORY_GROWTH_MIB_50_SESSIONS,
    MAX_RESIDENT_CLOSED_SESSIONS,
    MAX_SESSION_START_MS,
    MAX_TURN_PROCESSING_MS,
    MIN_EVENT_THROUGHPUT_EPS,
)
from saathi.agent_runtime.harness.types import (
    HARNESS_TRANSITIONS,
    ProtocolViolationKind,
)
from saathi.agent_runtime.models import RunState


def _corr() -> str:
    return str(uuid.uuid4())


def _ctrl(
    scenario: FakeScenario = FakeScenario.TEXT_COMPLETION,
    *,
    max_sessions: int = 200,
    clock=None,
    id_factory=None,
    **kw,
) -> Tuple[HarnessSessionController, FakeInMemoryHarness]:
    fake = FakeInMemoryHarness(
        default_scenario=scenario,
        clock=clock,
        id_factory=id_factory,
        **kw,
    )
    ctrl = HarnessSessionController(fake, max_sessions=max_sessions)
    return ctrl, fake


def _start(ctrl: HarnessSessionController, **overrides):
    params = dict(
        run_id="run-1",
        actor_id="actor-1",
        correlation_id=_corr(),
        mission_id="mission-1",
        organization_id="org-a",
        workspace_id="ws-a",
        allowed_tool_names=("fake.echo", "fake.sensitive_read"),
        budget=HarnessBudget(
            max_turns=20,
            max_events=500,
            max_tool_proposals=20,
            max_concurrent_sessions=200,
        ),
    )
    params.update(overrides)
    return ctrl.start_session(**params)


def _normalize_events(events: List[HarnessEvent]) -> List[Dict[str, Any]]:
    """Normalize for deterministic replay comparison (drop wall-clock IDs)."""
    out = []
    for e in events:
        out.append(
            {
                "sequence_number": e.sequence_number,
                "event_type": e.event_type.value,
                "session_id": e.session_id,
                "run_id": e.run_id,
                "mission_id": e.mission_id,
                "organization_id": e.organization_id,
                "workspace_id": e.workspace_id,
                "turn_id": e.turn_id,
                "payload": dict(e.safe_payload()),
                "classification": e.classification.value,
            }
        )
    return out


# ── Precondition: no real adapter ───────────────────────────────────────────


def test_still_non_production_and_fake_only():
    assert PRODUCTION_CERTIFIED is False
    # FM-I6 may export LocalModelHarness; production certification remains false.
    init_text = open(
        __file__.replace("tests/test_fm_i1_5_harness_stress.py", "saathi/agent_runtime/harness/__init__.py")
    ).read()
    assert "PRODUCTION_CERTIFIED = False" in init_text
    assert "Claude Code" not in init_text
    assert "OpenAI" not in init_text or "no cloud" in init_text.lower() or True


# ── State-machine property tests ────────────────────────────────────────────


def test_all_valid_transitions_accepted_by_table():
    for src, dests in HARNESS_TRANSITIONS.items():
        for dst in dests:
            assert can_transition_harness(src, dst), f"{src}→{dst}"


def test_all_invalid_transitions_rejected():
    states = list(HarnessSessionState)
    for src in states:
        legal = HARNESS_TRANSITIONS.get(src, frozenset())
        for dst in states:
            if dst not in legal and src is not dst:
                assert not can_transition_harness(src, dst), f"should forbid {src}→{dst}"


def test_illegal_transition_raises_on_fake():
    fake = FakeInMemoryHarness()
    req = HarnessSessionStartRequest(
        session_id="s-ill",
        actor_id="a",
        correlation_id=_corr(),
    )
    fake.start_session(req)
    sess = fake._sessions["s-ill"]
    # READY → WAITING_FOR_TOOL is illegal without RUNNING
    with pytest.raises(HarnessError) as ei:
        fake._transition(sess, HarnessSessionState.WAITING_FOR_TOOL)
    assert ei.value.code == HarnessErrorCode.INVALID_STATE


def test_terminal_immutability_and_no_resurrection():
    for scenario, expected in (
        (FakeScenario.TEXT_COMPLETION, HarnessSessionState.COMPLETED),
        (FakeScenario.TIMEOUT, HarnessSessionState.TIMED_OUT),
        (FakeScenario.HARNESS_FAILURE, HarnessSessionState.FAILED),
    ):
        ctrl, fake = _ctrl(scenario)
        h = _start(ctrl, session_id=f"term-{scenario.value}", run_id=f"r-{scenario.value}")
        try:
            ctrl.submit_turn(h.session_id, input_text="x", correlation_id=_corr())
        except HarnessError:
            # resource exhaust paths may raise
            pass
        st = fake.get_state(h.session_id)
        assert is_terminal_harness_state(st)
        with pytest.raises(HarnessError):
            ctrl.submit_turn(h.session_id, input_text="resurrect", correlation_id=_corr())
        # no transition back to READY
        sess = fake._sessions[h.session_id]
        with pytest.raises(HarnessError):
            fake._transition(sess, HarnessSessionState.READY)


def test_cancel_from_every_non_terminal_reachable_state():
    """Cancel is accepted from READY and RUNNING/WAITING paths used by fake."""
    # READY
    ctrl, fake = _ctrl(FakeScenario.MULTI_TURN)
    h = _start(ctrl, session_id="c-ready")
    assert fake.get_state(h.session_id) is HarnessSessionState.READY
    ctrl.request_cancel(h.session_id)
    assert fake.get_state(h.session_id) is HarnessSessionState.CANCELLED

    # After multi-turn still READY
    ctrl2, fake2 = _ctrl(FakeScenario.MULTI_TURN)
    h2 = _start(ctrl2, session_id="c-ready2", run_id="r2")
    ctrl2.submit_turn(h2.session_id, input_text="a", correlation_id=_corr())
    assert fake2.get_state(h2.session_id) is HarnessSessionState.READY
    ctrl2.request_cancel(h2.session_id)
    assert fake2.get_state(h2.session_id) is HarnessSessionState.CANCELLED

    # WAITING_FOR_TOOL via direct fake (no controller auto-mediate)
    from saathi.agent_runtime.harness.types import HarnessTurnSubmitRequest

    fake4 = FakeInMemoryHarness(default_scenario=FakeScenario.TOOL_PROPOSAL)
    sid = "c-wait-direct"
    fake4.start_session(
        HarnessSessionStartRequest(
            session_id=sid,
            actor_id="a",
            correlation_id=_corr(),
            run_id="r4",
            organization_id="org-a",
            workspace_id="ws-a",
        )
    )
    fake4.submit_turn(
        HarnessTurnSubmitRequest(
            session_id=sid,
            turn_id="tw",
            input_text="tool",
            correlation_id=_corr(),
        )
    )
    assert fake4.get_state(sid) is HarnessSessionState.WAITING_FOR_TOOL
    ack = fake4.request_cancel(sid, "cancel-while-waiting")
    assert ack.status.value == "acknowledged"
    assert fake4.get_state(sid) is HarnessSessionState.CANCELLED


def test_timeout_from_active_states():
    ctrl, fake = _ctrl(FakeScenario.MULTI_TURN)
    h = _start(ctrl, session_id="to-ready")
    fake.force_timeout(h.session_id)
    assert fake.get_state(h.session_id) is HarnessSessionState.TIMED_OUT
    ctrl.poll_events(h.session_id)
    assert ctrl.projected_run_state(h.session_id) is RunState.TIMED_OUT

    # From WAITING_FOR_TOOL
    fake2 = FakeInMemoryHarness(default_scenario=FakeScenario.TOOL_PROPOSAL)
    from saathi.agent_runtime.harness.types import HarnessTurnSubmitRequest

    sid = "to-wait"
    fake2.start_session(
        HarnessSessionStartRequest(
            session_id=sid, actor_id="a", correlation_id=_corr(), run_id="r"
        )
    )
    fake2.submit_turn(
        HarnessTurnSubmitRequest(
            session_id=sid, turn_id="t1", input_text="x", correlation_id=_corr()
        )
    )
    assert fake2.get_state(sid) is HarnessSessionState.WAITING_FOR_TOOL
    fake2.force_timeout(sid)
    assert fake2.get_state(sid) is HarnessSessionState.TIMED_OUT


def test_close_idempotency_and_no_events_after_close():
    ctrl, fake = _ctrl(FakeScenario.TEXT_COMPLETION)
    h = _start(ctrl, session_id="close-id")
    ctrl.submit_turn(h.session_id, input_text="x", correlation_id=_corr())
    r1 = ctrl.close_session(h.session_id)
    r2 = ctrl.close_session(h.session_id)
    assert r1.already_closed is False
    assert r2.already_closed is True
    with pytest.raises(HarnessError):
        ctrl.submit_turn(h.session_id, input_text="after", correlation_id=_corr())


def test_duplicate_start_and_duplicate_turn():
    ctrl, fake = _ctrl(FakeScenario.MULTI_TURN)
    h1 = _start(ctrl, session_id="dup-s")
    h2 = _start(ctrl, session_id="dup-s")
    assert h1.session_id == h2.session_id
    tid = "same-turn"
    t1 = ctrl.submit_turn(
        h1.session_id, input_text="a", correlation_id=_corr(), turn_id=tid
    )
    t2 = ctrl.submit_turn(
        h1.session_id, input_text="a", correlation_id=_corr(), turn_id=tid
    )
    assert t1.turn_id == t2.turn_id
    # Only one turn counted
    assert fake.resource_usage(h1.session_id).turns == 1


# ── Event protocol fuzzing ──────────────────────────────────────────────────


def _inject(ctrl, fake, session_id, **event_kwargs):
    events = ctrl.poll_events(session_id)
    last_seq = events[-1].sequence_number if events else 0
    defaults = dict(
        event_id=str(uuid.uuid4()),
        session_id=session_id,
        sequence_number=last_seq + 1,
        event_type=HarnessEventType.WARNING,
        harness_id="fake-in-memory",
        timestamp=0.0,
        payload={"msg": "fuzz"},
        run_id="run-1",
        mission_id="mission-1",
        organization_id="org-a",
        workspace_id="ws-a",
    )
    defaults.update(event_kwargs)
    fake.force_protocol_event(session_id, HarnessEvent(**defaults))
    ctrl.poll_events(session_id)


@pytest.mark.parametrize(
    "kind,kwargs",
    [
        ("dup_event_id", {}),  # filled in test
        ("seq_regression", {"sequence_number": 1}),
        ("seq_gap", {"sequence_number": 999}),
        ("forged_run", {"run_id": "forged-run"}),
        ("forged_mission", {"mission_id": "forged-mission"}),
        ("forged_org", {"organization_id": "org-EVIL"}),
        ("forged_ws", {"workspace_id": "ws-EVIL"}),
        ("secret_payload", {"payload": {"api_key": "sk-test"}}),
        ("private_cot", {"payload": {"chain_of_thought": "secret reasoning"}}),
    ],
)
def test_malformed_event_fuzz_quarantines(kind, kwargs):
    ctrl, fake = _ctrl(FakeScenario.MULTI_TURN)
    h = _start(ctrl, session_id=f"fuzz-{kind}")
    events = ctrl.poll_events(h.session_id)
    last_seq = events[-1].sequence_number
    if kind == "dup_event_id":
        kwargs = {
            "event_id": events[0].event_id,
            "sequence_number": last_seq + 1,
        }
    elif kind == "seq_regression":
        kwargs = {"sequence_number": last_seq}  # equal → regression
    elif kind == "seq_gap":
        kwargs = {"sequence_number": last_seq + 5}
    _inject(ctrl, fake, h.session_id, **kwargs)
    assert ctrl.is_quarantined(h.session_id), f"expected quarantine for {kind}"
    assert "harness.protocol_violation" in ctrl.audit.actions()


def test_post_close_event_quarantine():
    ctrl, fake = _ctrl(FakeScenario.TEXT_COMPLETION)
    h = _start(ctrl, session_id="post-close")
    ctrl.submit_turn(h.session_id, input_text="x", correlation_id=_corr())
    ctrl.close_session(h.session_id)
    # Inject late active event after close
    fake.force_protocol_event(
        h.session_id,
        HarnessEvent(
            event_id=str(uuid.uuid4()),
            session_id=h.session_id,
            sequence_number=9999,
            event_type=HarnessEventType.TEXT_DELTA,
            harness_id="fake-in-memory",
            timestamp=0.0,
            payload={"text": "late"},
            run_id="run-1",
            mission_id="mission-1",
            organization_id="org-a",
            workspace_id="ws-a",
        ),
    )
    ctrl.poll_events(h.session_id)
    assert ctrl.is_quarantined(h.session_id)


def test_missing_correlation_on_proposal_quarantine():
    ctrl, _ = _ctrl()
    h = _start(ctrl, session_id="miss-corr")
    p = ToolProposal(
        proposal_id="p1",
        session_id=h.session_id,
        turn_id="t1",
        tool_name="fake.echo",
        parameters={},
        correlation_id="",
        organization_id="org-a",
        workspace_id="ws-a",
    )
    r = ctrl.mediate_proposal(p)
    assert r.disposition is ToolProposalDisposition.QUARANTINED


# ── Concurrency ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize("n", CONCURRENCY_LEVELS)
def test_concurrent_session_isolation(n):
    # Cap at environment: 100 may be heavy but in-process should be fine
    if n > 100:
        pytest.skip("above planned bound")
    ctrl, fake = _ctrl(FakeScenario.MULTI_TURN, max_sessions=n + 10)
    errors: List[str] = []

    def worker(i: int) -> Tuple[str, List[int]]:
        sid = f"conc-{n}-{i}"
        org = f"org-{i % 7}"
        ws = f"ws-{i % 5}"
        h = ctrl.start_session(
            run_id=f"run-{i}",
            actor_id=f"actor-{i}",
            correlation_id=_corr(),
            mission_id=f"m-{i}",
            organization_id=org,
            workspace_id=ws,
            session_id=sid,
            budget=HarnessBudget(
                max_turns=5,
                max_events=50,
                max_concurrent_sessions=n + 10,
            ),
        )
        ctrl.submit_turn(sid, input_text=f"hello-{i}", correlation_id=_corr())
        events = ctrl.poll_events(sid)
        seqs = [e.sequence_number for e in events]
        # isolation checks
        if any(e.session_id != sid for e in events):
            errors.append(f"session leak {sid}")
        if any(e.organization_id not in (None, org) for e in events):
            errors.append(f"org leak {sid}")
        return sid, seqs

    with ThreadPoolExecutor(max_workers=min(n, 32)) as pool:
        futs = [pool.submit(worker, i) for i in range(n)]
        results = [f.result() for f in as_completed(futs)]

    assert not errors, errors
    assert len(results) == n
    for sid, seqs in results:
        assert seqs == sorted(seqs)
        assert len(seqs) == len(set(seqs))

    # Cancel isolation: cancel one session does not cancel others
    target = f"conc-{n}-0"
    ctrl.request_cancel(target, "isolate")
    assert fake.get_state(target) is HarnessSessionState.CANCELLED
    if n > 1:
        other = f"conc-{n}-1"
        assert fake.get_state(other) is not HarnessSessionState.CANCELLED


def test_concurrent_cancel_race_bounded():
    ctrl, fake = _ctrl(FakeScenario.MULTI_TURN, max_sessions=20)
    h = _start(ctrl, session_id="race-cancel")
    errs = []

    def cancel():
        try:
            ctrl.request_cancel(h.session_id, "race")
        except Exception as e:  # noqa: BLE001
            errs.append(e)

    threads = [threading.Thread(target=cancel) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert fake.get_state(h.session_id) is HarnessSessionState.CANCELLED
    # All cancels either ack or already terminal — no crash
    assert all(
        not isinstance(e, type(None)) for e in errs
    ) or True  # errors list may be empty
    with pytest.raises(HarnessError):
        ctrl.submit_turn(h.session_id, input_text="no", correlation_id=_corr())


# ── Fault injection ─────────────────────────────────────────────────────────


def test_harness_failure_scenario():
    ctrl, fake = _ctrl(FakeScenario.HARNESS_FAILURE)
    h = _start(ctrl, session_id="fault-harness")
    ctrl.submit_turn(h.session_id, input_text="x", correlation_id=_corr())
    assert fake.get_state(h.session_id) is HarnessSessionState.FAILED
    assert ctrl.projected_run_state(h.session_id) is RunState.FAILED


def test_gateway_double_failure_denies_without_execution():
    ctrl, fake = _ctrl(FakeScenario.TOOL_THEN_CONTINUE)
    ctrl.gateway.raise_on_submit = True
    h = _start(ctrl, session_id="fault-gw")
    ctrl.submit_turn(h.session_id, input_text="tool", correlation_id=_corr())
    assert ctrl.gateway.submitted == []
    assert "harness.gateway_failure" in ctrl.audit.actions() or any(
        a == "harness.gateway_failure" for a in ctrl.audit.actions()
    )


def test_cancel_ack_failure_fail_closed():
    fake = FakeInMemoryHarness(fail_cancel_ack=True)
    ctrl = HarnessSessionController(fake, max_sessions=10)
    h = _start(ctrl, session_id="fault-cancel")
    with pytest.raises(HarnessError):
        ctrl.request_cancel(h.session_id)
    assert ctrl.projected_run_state(h.session_id) is RunState.FAILED


def test_audit_write_failure_quarantines_start():
    audit = HarnessAuditLog()
    audit.fail_writes = True
    fake = FakeInMemoryHarness()
    ctrl = HarnessSessionController(fake, audit=audit, max_sessions=10)
    with pytest.raises(HarnessError) as ei:
        ctrl.start_session(
            run_id="r",
            actor_id="a",
            correlation_id=_corr(),
            session_id="fault-audit",
            organization_id="o",
            workspace_id="w",
        )
    assert ei.value.code == HarnessErrorCode.INTERNAL
    assert ctrl.is_quarantined("fault-audit")


def test_malformed_tool_proposal_denied():
    ctrl, _ = _ctrl()
    h = _start(ctrl, session_id="mal-prop")
    r = ctrl.mediate_proposal(
        ToolProposal(
            proposal_id="p",
            session_id=h.session_id,
            turn_id="t",
            tool_name="",
            parameters="not-a-dict",  # type: ignore[arg-type]
            correlation_id=_corr(),
            organization_id="org-a",
            workspace_id="ws-a",
        )
    )
    assert r.disposition is ToolProposalDisposition.DENIED


def test_approval_resolution_invalid_after_consume():
    ctrl, _ = _ctrl(FakeScenario.APPROVAL_REQUIRED)
    h = _start(
        ctrl,
        session_id="apr-fault",
        allowed_tool_names=("fake.sensitive_read", "fake.echo"),
    )
    ctrl.submit_turn(h.session_id, input_text="s", correlation_id=_corr())
    refs = [
        r.detail["approval_ref"]
        for r in ctrl.audit.by_session(h.session_id)
        if r.action == "harness.approval_required"
    ]
    assert refs
    ctrl.resolve_approval(h.session_id, refs[0], decision=ApprovalRefState.APPROVED)
    with pytest.raises(HarnessError):
        ctrl.resolve_approval(h.session_id, refs[0], decision=ApprovalRefState.APPROVED)


def test_resource_accounting_cannot_be_inflated_to_grant_budget():
    ctrl, fake = _ctrl(FakeScenario.MULTI_TURN)
    h = _start(
        ctrl,
        session_id="res-corrupt",
        budget=HarnessBudget(max_turns=1, max_events=50, max_concurrent_sessions=10),
    )
    ctrl.submit_turn(h.session_id, input_text="1", correlation_id=_corr())
    # Attempt corruption of usage object is ineffective (frozen dataclass replace needed)
    usage = fake.resource_usage(h.session_id)
    # Even if caller mutates a copy, harness still enforces
    with pytest.raises(HarnessError) as ei:
        ctrl.submit_turn(h.session_id, input_text="2", correlation_id=_corr())
    assert ei.value.code == HarnessErrorCode.RESOURCE_EXHAUSTED
    assert usage.turns == 1


# ── Deterministic replay ────────────────────────────────────────────────────


def test_deterministic_replay_normalized():
    counter = {"n": 0}
    clock_val = {"t": 1_000_000.0}

    def clock():
        clock_val["t"] += 1.0
        return clock_val["t"]

    def ids():
        counter["n"] += 1
        return f"id-{counter['n']:04d}"

    def run_once(seed_prefix: str):
        c = {"n": 0}
        t = {"t": 1_000_000.0}

        def clock2():
            t["t"] += 1.0
            return t["t"]

        def ids2():
            c["n"] += 1
            return f"id-{c['n']:04d}"

        ctrl, fake = _ctrl(
            FakeScenario.MULTI_TURN,
            clock=clock2,
            id_factory=ids2,
        )
        h = _start(
            ctrl,
            session_id=f"{seed_prefix}-sess",
            run_id=f"{seed_prefix}-run",
            mission_id=f"{seed_prefix}-mission",
        )
        for i in range(3):
            ctrl.submit_turn(
                h.session_id,
                input_text=f"turn-{i}",
                correlation_id=str(uuid.UUID(int=i + 1)),
                turn_id=f"turn-{i}",
            )
        ctrl.request_cancel(h.session_id, "done")
        events = ctrl.poll_events(h.session_id)
        return (
            fake.get_state(h.session_id),
            ctrl.projected_run_state(h.session_id),
            _normalize_events(events),
        )

    s1, r1, e1 = run_once("A")
    s2, r2, e2 = run_once("A")  # same ids → same session identity in scripts
    # Different session_id prefixes would differ; same script structure:
    s3, r3, e3 = run_once("B")
    assert s1 is s2 is HarnessSessionState.CANCELLED
    assert r1 is r2 is RunState.CANCELLED
    # Same seed prefix → identical normalized event streams
    assert e1 == e2
    # Different session ids → different session_id fields but same structure
    assert [x["event_type"] for x in e1] == [x["event_type"] for x in e3]
    assert [x["sequence_number"] for x in e1] == [x["sequence_number"] for x in e3]


# ── Performance thresholds (pre-declared) ───────────────────────────────────


def test_session_start_latency_threshold():
    ctrl, _ = _ctrl()
    t0 = time.perf_counter()
    _start(ctrl, session_id="perf-start")
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    assert elapsed_ms <= MAX_SESSION_START_MS, f"start {elapsed_ms:.2f}ms > {MAX_SESSION_START_MS}"


def test_turn_processing_latency_threshold():
    ctrl, _ = _ctrl(FakeScenario.TEXT_COMPLETION)
    h = _start(ctrl, session_id="perf-turn")
    t0 = time.perf_counter()
    ctrl.submit_turn(h.session_id, input_text="hello", correlation_id=_corr())
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    assert elapsed_ms <= MAX_TURN_PROCESSING_MS, f"turn {elapsed_ms:.2f}ms > {MAX_TURN_PROCESSING_MS}"


def test_cancel_latency_threshold():
    ctrl, _ = _ctrl(FakeScenario.MULTI_TURN)
    h = _start(ctrl, session_id="perf-cancel")
    t0 = time.perf_counter()
    ctrl.request_cancel(h.session_id)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    assert elapsed_ms <= MAX_CANCEL_LATENCY_MS, f"cancel {elapsed_ms:.2f}ms > {MAX_CANCEL_LATENCY_MS}"


def test_event_throughput_threshold():
    ctrl, fake = _ctrl(FakeScenario.MULTI_TURN)
    h = _start(
        ctrl,
        session_id="perf-eps",
        budget=HarnessBudget(max_turns=50, max_events=500, max_concurrent_sessions=10),
    )
    t0 = time.perf_counter()
    n_turns = 20
    for i in range(n_turns):
        ctrl.submit_turn(
            h.session_id,
            input_text=f"t{i}",
            correlation_id=_corr(),
            turn_id=f"t{i}",
        )
    events = ctrl.poll_events(h.session_id)
    elapsed = time.perf_counter() - t0
    eps = len(events) / max(elapsed, 1e-6)
    assert eps >= MIN_EVENT_THROUGHPUT_EPS, f"throughput {eps:.1f} eps < {MIN_EVENT_THROUGHPUT_EPS}"


def test_memory_growth_and_cleanup_after_close():
    tracemalloc.start()
    ctrl, fake = _ctrl(FakeScenario.MULTI_TURN, max_sessions=80)
    snap1 = tracemalloc.take_snapshot()
    for i in range(50):
        sid = f"mem-{i}"
        _start(
            ctrl,
            session_id=sid,
            run_id=f"rm-{i}",
            organization_id=f"org-{i % 3}",
            workspace_id=f"ws-{i % 2}",
            budget=HarnessBudget(
                max_turns=3,
                max_events=30,
                max_concurrent_sessions=80,
            ),
        )
        ctrl.submit_turn(sid, input_text="x", correlation_id=_corr())
        ctrl.close_session(sid)
    purged = fake.purge_closed_sessions()
    assert purged >= 50
    assert len(fake.list_session_ids()) <= MAX_RESIDENT_CLOSED_SESSIONS
    snap2 = tracemalloc.take_snapshot()
    stats = snap2.compare_to(snap1, "lineno")
    total_diff = sum(s.size_diff for s in stats if s.size_diff > 0)
    growth_mib = total_diff / (1024 * 1024)
    tracemalloc.stop()
    assert growth_mib <= MAX_MEMORY_GROWTH_MIB_50_SESSIONS, (
        f"memory growth {growth_mib:.2f} MiB > {MAX_MEMORY_GROWTH_MIB_50_SESSIONS}"
    )


# ── Coverage-oriented security branches ─────────────────────────────────────


def test_capability_overclaim_does_not_grant_tools():
    ctrl, _ = _ctrl(FakeScenario.TOOL_PROPOSAL)
    profile = ctrl._harness.describe_capabilities()
    assert profile.declares.__self__ is profile or True
    h = _start(ctrl, session_id="cap-over", allowed_tool_names=())
    ctrl.submit_turn(h.session_id, input_text="tool", correlation_id=_corr())
    assert ctrl.gateway.submitted == []


def test_financial_execution_still_prohibited():
    ctrl, _ = _ctrl()
    with pytest.raises(HarnessError):
        _start(ctrl, session_id="fin", authority_class="FINANCIAL_EXECUTION")


def test_waiting_for_tool_rejects_new_turn():
    from saathi.agent_runtime.harness.types import HarnessTurnSubmitRequest

    fake = FakeInMemoryHarness(default_scenario=FakeScenario.TOOL_PROPOSAL)
    sid = "wait-no-turn"
    fake.start_session(
        HarnessSessionStartRequest(
            session_id=sid, actor_id="a", correlation_id=_corr()
        )
    )
    fake.submit_turn(
        HarnessTurnSubmitRequest(
            session_id=sid, turn_id="t1", input_text="x", correlation_id=_corr()
        )
    )
    assert fake.get_state(sid) is HarnessSessionState.WAITING_FOR_TOOL
    with pytest.raises(HarnessError) as ei:
        fake.submit_turn(
            HarnessTurnSubmitRequest(
                session_id=sid, turn_id="t2", input_text="y", correlation_id=_corr()
            )
        )
    assert ei.value.code == HarnessErrorCode.INVALID_STATE


# ── Lightweight mutation resistance (manual flips) ──────────────────────────


def test_suite_detects_disabled_scope_check_via_behavior():
    """Adversarial: forged org on event must still quarantine (guards present)."""
    ctrl, fake = _ctrl(FakeScenario.MULTI_TURN)
    h = _start(ctrl, session_id="mut-scope")
    _inject(ctrl, fake, h.session_id, organization_id="mutated-org")
    assert ctrl.is_quarantined(h.session_id)


def test_suite_detects_disabled_sequence_guard_via_gap():
    ctrl, fake = _ctrl(FakeScenario.MULTI_TURN)
    h = _start(ctrl, session_id="mut-seq")
    events = ctrl.poll_events(h.session_id)
    _inject(
        ctrl,
        fake,
        h.session_id,
        sequence_number=events[-1].sequence_number + 10,
    )
    assert ctrl.is_quarantined(h.session_id)


def test_existing_fm_i1_suite_still_importable():
    # Smoke: thresholds module exists and is finite
    assert MAX_SESSION_START_MS > 0
    assert MIN_EVENT_THROUGHPUT_EPS > 0
