"""Live Teach Loop — suggester + session state machine + learn → registry/event."""
import pytest

from saathi.infrastructure.human_browser import (
    SelectorRegistry, TeachMode, TeachState, TeachCapture, suggest_selectors,
)


class Bus:
    def __init__(self): self.events = []
    def publish_sync(self, n, p): self.events.append((n, p))


def _cap(**kw):
    base = dict(key="youtube/publish", selector="#done-button", aria="Publish",
                text="PUBLISH", tag="button")
    base.update(kw)
    return TeachCapture(**base)


# ── AI suggester ─────────────────────────────────────────────────────────────
def test_suggester_ranks_id_and_aria_high():
    sug = suggest_selectors(_cap())
    strategies = [s["strategy"] for s in sug]
    assert strategies[0] == "id" and "aria" in strategies
    assert sug[0]["confidence"] >= sug[-1]["confidence"]      # ranked best-first


def test_suggester_dedupes():
    sug = suggest_selectors(_cap(selector="#x", aria="", text=""))
    assert len(sug) == 1 and sug[0]["strategy"] == "id"


def test_suggester_optional_ai_rerank():
    sug = suggest_selectors(_cap(), ask=lambda cap, ranked: {"confidence": 0.99})
    assert sug[0]["confidence"] == 0.99


# ── full loop ────────────────────────────────────────────────────────────────
def _teacher(tmp_path):
    reg = SelectorRegistry(db_path=str(tmp_path / "s.db"))
    bus = Bus()
    return TeachMode(registry=reg, bus=bus), reg, bus


def test_full_loop_learns_after_test_passes(tmp_path):
    t, reg, bus = _teacher(tmp_path)
    s = t.open("youtube/publish", workflow="youtube_upload", reason="Publish button not found")
    assert s.state is TeachState.PENDING
    assert ("teach.requested", s.__dict__ and bus.events[0][1]) == ("teach.requested", bus.events[0][1])

    t.take_control(s.id);            assert t.store.get(s.id).state is TeachState.CAPTURING
    t.submit_capture(s.id, _cap());  s = t.store.get(s.id)
    assert s.state is TeachState.SUGGESTED and s.suggestions and s.chosen == "#done-button"

    # TEST FIRST passes → learns
    s = t.verify_and_learn(s.id, verify_fn=lambda sel: True)
    assert s.state is TeachState.LEARNED
    # registry now knows the taught selector at high confidence
    assert reg.known("youtube/publish")[0].selector == "#done-button"
    # a selector.learned event fired (→ Episode)
    learned = [e for e in bus.events if e[0] == "selector.learned"]
    assert learned and learned[0][1]["element"] == "youtube/publish" and learned[0][1]["ok"] is True


def test_test_first_failure_does_not_learn(tmp_path):
    t, reg, bus = _teacher(tmp_path)
    s = t.open("youtube/publish")
    t.take_control(s.id); t.submit_capture(s.id, _cap())
    s = t.verify_and_learn(s.id, verify_fn=lambda sel: False)   # vision says wrong
    assert s.state is TeachState.SUGGESTED                       # back to choose, not learned
    assert reg.known("youtube/publish") == [] or all(k.source != "taught" for k in reg.known("youtube/publish"))
    assert not any(e[0] == "selector.learned" for e in bus.events)


def test_operator_can_choose_a_different_suggestion(tmp_path):
    t, reg, _ = _teacher(tmp_path)
    s = t.open("k")
    t.take_control(s.id); t.submit_capture(s.id, _cap())
    t.confirm(s.id, selector="button[aria-label='Publish']")     # pick the aria fallback
    s = t.verify_and_learn(s.id)                                  # no verify_fn → learn directly
    assert s.state is TeachState.LEARNED
    assert reg.known("k")[0].selector == "button[aria-label='Publish']"


def test_abort_and_pending_list(tmp_path):
    t, _, _ = _teacher(tmp_path)
    a = t.open("k1"); b = t.open("k2")
    assert {s.id for s in t.store.pending()} == {a.id, b.id}
    t.abort(a.id)
    assert {s.id for s in t.store.pending()} == {b.id}


def test_selector_learned_becomes_episode(tmp_path):
    from saathi.events import EventBus
    from saathi import episode_bridge
    bus = EventBus(); rec = []
    episode_bridge.install(bus, record_episode=lambda **kw: rec.append(kw) or 1)
    bus.publish_sync("selector.learned", {"element": "youtube/publish", "ok": True})
    assert rec and rec[0]["intent"] == "teach" and rec[0]["outcome"] == "success"
