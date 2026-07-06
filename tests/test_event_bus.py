"""Universal Event Bus — emit → persist → route to Evidence → notify subscribers."""
import tempfile, os
from saathi.events.bus import EventBus
from saathi.events.routes import department_for
from saathi.evidence.store import EvidenceStore


def _bus():
    fd, p = tempfile.mkstemp(suffix=".db"); os.close(fd)
    return EventBus(p)


def test_routing_table_maps_types_to_departments():
    assert department_for("essay.scored") == "pielts"
    assert department_for("trade.closed") == "hcg"
    assert department_for("meal.sold") == "cafeteria"
    assert department_for("episode.produced") == "ai_studio"
    assert department_for("booking.confirmed") == "travel"
    assert department_for("something.unknown") is None


def test_emit_persists_and_queries():
    b = _bus()
    r = b.emit("lesson.completed", "pielts", {"topic": "Present Perfect"}, subject="L-1")
    assert r["id"] and r["type"] == "lesson.completed"
    assert b.count() == 1
    evs = b.query(source="pielts")
    assert len(evs) == 1 and evs[0]["payload"]["topic"] == "Present Perfect"


def test_emit_routes_into_evidence(monkeypatch):
    fd, ep = tempfile.mkstemp(suffix=".db"); os.close(fd)
    store = EvidenceStore(ep)
    import saathi.evidence.store as es
    monkeypatch.setattr(es, "_default", store)
    monkeypatch.setattr(es, "default_store", lambda: store)
    b = _bus()
    res = b.emit("essay.scored", "pielts",
                 {"essay_id": "ES-1", "band": 5.5, "prompt_version": "v4"}, subject="ES-1")
    assert len(res["evidence_ids"]) == 1                 # routed via pielts adapter
    assert store.count(department="pielts") == 1
    row = store.query(department="pielts")[0]
    assert row["metrics"]["band"] == 5.5


def test_unmatched_event_still_persists_without_evidence():
    b = _bus()
    res = b.emit("website.visit", "website", {"path": "/pricing"})
    assert res["evidence_ids"] == []                     # no route yet
    assert b.count() == 1                                # signal not lost


def test_subscribe_fires_on_glob():
    b = _bus()
    seen = []
    b.subscribe("trade.*", lambda ev: seen.append(ev.type))
    b.emit("trade.closed", "hcg", {"result": "win"})
    b.emit("lesson.completed", "pielts", {})
    assert seen == ["trade.closed"]                      # only matching pattern fired


def test_stats_group_by_type_and_source():
    b = _bus()
    b.emit("meal.sold", "cafeteria", {})
    b.emit("meal.sold", "cafeteria", {})
    b.emit("trade.closed", "hcg", {})
    s = b.stats()
    assert s["by_type"]["meal.sold"] == 2 and s["by_source"]["hcg"] == 1 and s["total"] == 3
