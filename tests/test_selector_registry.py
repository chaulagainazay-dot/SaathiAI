"""Selector Registry + Teach Mode — the automation knowledge backbone."""
from saathi.infrastructure.human_browser import (
    SelectorRegistry, TeachCapture, learn_from_capture,
)
from saathi.infrastructure.human_browser.pages import youtube as YT


def test_seed_known_and_best(tmp_path):
    r = SelectorRegistry(db_path=str(tmp_path / "s.db"))
    r.seed("youtube/publish", ["#done-button", "[aria-label='Publish']", "ytcp-button#done"])
    known = r.known("youtube/publish")
    assert len(known) == 3
    best = r.best("youtube/publish", top=2)
    assert best.count(",") == 1                    # top-2 as comma-CSS "match any"


def test_success_raises_confidence_failure_lowers(tmp_path):
    r = SelectorRegistry(db_path=str(tmp_path / "s.db"))
    r.seed("k", ["#a", "#b"])
    for _ in range(4):
        r.record_success("k", "#a")
    r.record_failure("k", "#b")
    known = {k.selector: k for k in r.known("k")}
    assert known["#a"].confidence > known["#b"].confidence
    assert r.known("k")[0].selector == "#a"        # winner sorts first


def test_taught_selector_outranks_seeded(tmp_path):
    r = SelectorRegistry(db_path=str(tmp_path / "s.db"))
    r.seed("youtube/publish", ["#old-selector"])   # confidence 0.6
    r.learn("youtube/publish", "#new-taught-button")  # confidence 0.9
    assert r.known("youtube/publish")[0].selector == "#new-taught-button"
    assert r.stats("youtube/publish")["confidence"] >= 0.9


def test_learn_from_capture_writes_knowledge(tmp_path):
    r = SelectorRegistry(db_path=str(tmp_path / "s.db"))
    cap = TeachCapture(key="youtube/publish", selector="#done-button",
                       aria="Publish", text="PUBLISH", tag="button")
    ks = learn_from_capture(r, cap, confirmed=True)
    assert ks.selector == "#done-button" and ks.source == "taught"
    assert "youtube/publish" in r.keys()


def test_unconfirmed_capture_is_not_learned(tmp_path):
    r = SelectorRegistry(db_path=str(tmp_path / "s.db"))
    assert learn_from_capture(r, TeachCapture(key="k", selector="#x"), confirmed=False) is None
    assert r.keys() == []


def test_overview_and_stats(tmp_path):
    r = SelectorRegistry(db_path=str(tmp_path / "s.db"))
    YT.seed(r)
    ov = {e["key"]: e for e in r.overview()}
    assert "youtube/publish" in ov and "youtube/title" in ov
    assert ov["youtube/title"]["known"] >= 3       # multiple strategies seeded
    assert ov["youtube/publish"]["confidence"] > 0
