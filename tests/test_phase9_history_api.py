"""Phase 9 — historical truth contract.

History must answer "what actually happened", independently of which run is open
now and of how many certification runs were created recently.
"""
import pytest

from saathi.agent_runtime.api import (
    TEST_STRATEGIES, VERIFICATION_FAILED, VERIFICATION_PASSED,
    VERIFICATION_UNAVAILABLE, _verification_state)
from saathi.agent_runtime.models import _TERMINAL, IllegalTransition, RunState
from saathi.agent_runtime.store import RunStore


@pytest.fixture()
def store(tmp_path):
    return RunStore(db_path=tmp_path / "hist.db")


def _run(store, *, objective="obj", strategy="build", state=RunState.COMPLETED,
         conversation_id="", updated_at=None):
    """Create a run and drive it to a terminal state through the real store."""
    rid = store.create_run(objective=objective, strategy=strategy, actor="user:test",
                           conversation_id=conversation_id)
    store.transition(rid, RunState.PLANNING)
    store.transition(rid, RunState.QUEUED)
    store.transition(rid, RunState.RUNNING)
    try:
        store.transition(rid, state)
    except IllegalTransition:
        # Some terminal states have no inbound edge in the state machine (see
        # test_rolled_back_has_no_inbound_transition). The history query still
        # has to return them if a row ever holds one, so the row is written
        # directly -- this asserts nothing about reachability.
        with store._conn() as c:
            c.execute("UPDATE orchestration_run SET state=?, updated_at=? WHERE id=?",
                      (state.value, 1.0, rid))
    if updated_at is not None:
        with store._conn() as c:
            c.execute("UPDATE orchestration_run SET updated_at=? WHERE id=?", (updated_at, rid))
    return rid


# ── terminal filtering ─────────────────────────────────────────────────────

def test_only_terminal_runs_are_history(store):
    done = _run(store, objective="done")
    active = store.create_run(objective="still going", strategy="build", actor="u")
    store.transition(active, RunState.PLANNING)

    rows, _ = store.terminal_history(limit=50)
    ids = [r["id"] for r in rows]
    assert done in ids
    assert active not in ids, "an active run is not history"


def test_paused_runs_are_not_history(store):
    rid = store.create_run(objective="paused", strategy="build", actor="u")
    store.transition(rid, RunState.PLANNING)
    store.transition(rid, RunState.QUEUED)
    store.transition(rid, RunState.RUNNING)
    store.transition(rid, RunState.PAUSED)

    rows, _ = store.terminal_history(limit=50)
    assert rid not in [r["id"] for r in rows], "paused is not terminal"


@pytest.mark.parametrize("state", sorted(s.value for s in _TERMINAL))
def test_every_terminal_state_is_returned(store, state):
    rid = _run(store, state=RunState(state))
    rows, _ = store.terminal_history(limit=50)
    assert rid in [r["id"] for r in rows], f"{state} must appear in history"
    assert next(r for r in rows if r["id"] == rid)["state"] == state


def test_terminal_filter_uses_the_canonical_set(store):
    # Six states, straight from the backend's own definition.
    assert {s.value for s in _TERMINAL} == {
        "completed", "cancelled", "failed", "timed_out",
        "rolled_back", "partially_completed"}


# ── ordering ───────────────────────────────────────────────────────────────

def test_history_orders_by_when_runs_ended(store):
    # Created first but ended last -- history must follow the ending.
    a = _run(store, objective="ended last", updated_at=9000)
    b = _run(store, objective="ended first", updated_at=100)
    rows, _ = store.terminal_history(limit=50)
    assert [r["id"] for r in rows][:2] == [a, b]


def test_equal_timestamps_order_deterministically(store):
    ids = [_run(store, objective=f"o{i}", updated_at=500) for i in range(4)]
    first = [r["id"] for r in store.terminal_history(limit=50)[0]]
    second = [r["id"] for r in store.terminal_history(limit=50)[0]]
    assert first == second, "same-instant records must not shuffle between reads"
    assert set(first) == set(ids)


# ── fixture policy: the crowding fix ───────────────────────────────────────

def test_certification_strategies_are_excluded_by_default(store):
    real = _run(store, objective="real work", strategy="build", updated_at=10)
    hold = _run(store, objective="fixture", strategy="test_hold", updated_at=20)
    fail = _run(store, objective="fixture", strategy="test_fail",
                state=RunState.FAILED, updated_at=30)

    rows, _ = store.terminal_history(limit=50, exclude_strategies=TEST_STRATEGIES)
    ids = [r["id"] for r in rows]
    assert ids == [real]
    assert hold not in ids and fail not in ids


def test_fixtures_can_be_included_explicitly(store):
    real = _run(store, strategy="build", updated_at=10)
    hold = _run(store, strategy="test_hold", updated_at=20)
    rows, _ = store.terminal_history(limit=50)          # no exclusion
    assert {real, hold} <= {r["id"] for r in rows}


def test_newer_fixtures_cannot_crowd_out_real_history(store):
    """The defect this endpoint exists to fix.

    A generic newest-N window filtered afterwards would return only fixtures.
    Filtering terminal + fixtures inside the query keeps real history reachable.
    """
    real = [_run(store, objective=f"real {i}", strategy="build", updated_at=i)
            for i in range(3)]
    for i in range(40):                                  # 40 newer fixture runs
        _run(store, objective="fixture", strategy="test_hold", updated_at=1000 + i)

    rows, _ = store.terminal_history(limit=10, exclude_strategies=TEST_STRATEGIES)
    ids = [r["id"] for r in rows]
    assert set(real) <= set(ids), "real history must survive a burst of fixtures"
    assert len(ids) == 3


def test_only_the_two_known_fixtures_are_excluded(store):
    assert set(TEST_STRATEGIES) == {"test_hold", "test_fail"}
    for legit in ("build", "document", "business", "broad_research", "architect_build", "single"):
        rid = _run(store, strategy=legit)
        rows, _ = store.terminal_history(limit=50, exclude_strategies=TEST_STRATEGIES)
        assert rid in [r["id"] for r in rows], f"{legit} is production work"


# ── bounded read / pagination ──────────────────────────────────────────────

def test_reads_are_bounded_and_report_more(store):
    for i in range(12):
        _run(store, objective=f"o{i}", updated_at=i)
    rows, has_more = store.terminal_history(limit=5)
    assert len(rows) == 5 and has_more is True

    rows, has_more = store.terminal_history(limit=50)
    assert len(rows) == 12 and has_more is False


def test_cursor_walks_older_history_without_repeating(store):
    for i in range(9):
        _run(store, objective=f"o{i}", updated_at=100 + i)

    seen, before = [], None
    for _ in range(5):
        rows, has_more = store.terminal_history(limit=4, before=before)
        seen.extend(r["id"] for r in rows)
        if not has_more:
            break
        before = rows[-1]["updated_at"]
    assert len(seen) == len(set(seen)), "a cursor page must not repeat rows"
    assert len(seen) == 9


def test_conversation_filter_is_optional_and_exact(store):
    mine = _run(store, conversation_id="cmd-a")
    theirs = _run(store, conversation_id="cmd-b")
    rows, _ = store.terminal_history(limit=50, conversation_id="cmd-a")
    assert [r["id"] for r in rows] == [mine] and theirs not in [r["id"] for r in rows]


# ── verification aggregation ───────────────────────────────────────────────

def test_verification_summary_is_one_batched_read(store):
    a = _run(store)
    b = _run(store)
    store.add_verification(a, "t1", "output_schema", True)
    store.add_verification(b, "t1", "output_schema", False)

    summary = store.verification_summary([a, b])
    assert summary[a] == {"passed": 1, "failed": 0}
    assert summary[b] == {"passed": 0, "failed": 1}


def test_verification_is_never_inferred_from_terminal_state(store):
    rid = _run(store, state=RunState.COMPLETED)
    assert store.verification_summary([rid]) == {}, "no records means no verification"
    assert _verification_state(None) == VERIFICATION_UNAVAILABLE


def test_a_failure_dominates_any_number_of_passes():
    assert _verification_state({"passed": 5, "failed": 1}) == VERIFICATION_FAILED
    assert _verification_state({"passed": 0, "failed": 1}) == VERIFICATION_FAILED
    assert _verification_state({"passed": 3, "failed": 0}) == VERIFICATION_PASSED
    assert _verification_state({"passed": 0, "failed": 0}) == VERIFICATION_UNAVAILABLE


def test_duplicate_verification_records_stay_deterministic(store):
    rid = _run(store)
    for _ in range(3):
        store.add_verification(rid, "t1", "output_schema", True)
    assert _verification_state(store.verification_summary([rid])[rid]) == VERIFICATION_PASSED

    store.add_verification(rid, "t2", "citations", False)
    store.add_verification(rid, "t2", "citations", False)
    assert _verification_state(store.verification_summary([rid])[rid]) == VERIFICATION_FAILED


def test_failure_dominates_regardless_of_event_order(store):
    late_fail = _run(store)
    store.add_verification(late_fail, "t1", "s", True)
    store.add_verification(late_fail, "t2", "s", False)

    early_fail = _run(store)
    store.add_verification(early_fail, "t1", "s", False)
    store.add_verification(early_fail, "t2", "s", True)

    summaries = store.verification_summary([late_fail, early_fail])
    for rid in (late_fail, early_fail):
        assert _verification_state(summaries[rid]) == VERIFICATION_FAILED


def test_verification_summary_of_nothing_is_empty(store):
    assert store.verification_summary([]) == {}
    assert store.verification_summary(["missing-run"]) == {}


# ── read-only ──────────────────────────────────────────────────────────────

def test_history_reads_mutate_nothing(store):
    rid = _run(store, objective="unchanged")
    store.add_verification(rid, "t1", "s", True)
    before = store.get_run(rid)

    store.terminal_history(limit=50)
    store.verification_summary([rid])

    after = store.get_run(rid)
    assert after["state"] == before["state"]
    assert after["updated_at"] == before["updated_at"]
    assert len(store.verifications(rid)) == 1


def test_rolled_back_has_no_inbound_transition():
    """Documented, not fixed.

    `rolled_back` is in the canonical terminal set but no transition leads to
    it, so the runtime cannot currently produce one. History still handles the
    state, because the terminal set is the contract; making it reachable is a
    state-machine decision, not a history one.
    """
    from saathi.agent_runtime.models import _TRANSITIONS
    inbound = [src.value for src, dsts in _TRANSITIONS.items()
               if RunState.ROLLED_BACK in dsts]
    assert inbound == [], "if this starts failing, rolled_back became reachable"
    assert RunState.ROLLED_BACK in _TERMINAL
