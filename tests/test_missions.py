"""Mission — the root object of SaathiOS: store, seed, overview aggregation."""
import tempfile, os
from saathi.missions.store import Mission, MissionStore, seed_missions, _SEED, TYPES
from saathi.missions.overview import overview


def _store():
    fd, p = tempfile.mkstemp(suffix=".db"); os.close(fd)
    return MissionStore(p)


def test_create_get_and_key_uniqueness():
    st = _store()
    m = Mission(key="acme", name="Grow Acme", type="client", department="travel")
    mid = st.create(m)
    assert st.get(mid)["name"] == "Grow Acme"
    assert st.get_by_key("acme")["type"] == "client"
    assert st.create_if_absent(Mission(key="acme", name="dup")) == mid   # no duplicate key


def test_seed_creates_five_businesses_idempotently():
    st = _store()
    assert seed_missions(st) == 5
    assert seed_missions(st) == 0                     # idempotent
    keys = {m["key"] for m in st.list()}
    assert {"mr_yeti", "pielts", "surmount_travels", "hcg_signal", "hcg_canteen"} == keys
    assert all(m.type in TYPES for m in _SEED)


def test_update_mission_fields():
    st = _store()
    mid = st.create(Mission(key="acme", name="Acme"))
    assert st.update(mid, {"status": "paused", "objectives": ["A", "B"]}) is True
    got = st.get(mid)
    assert got["status"] == "paused" and got["objectives"] == ["A", "B"]
    assert st.update("nope", {"status": "x"}) is False


def test_overview_aggregates_by_mission_namespace(monkeypatch):
    # a Mission's key == evidence project; overview should roll it up
    from saathi.evidence.store import EvidenceStore
    from saathi.evidence.schema import Evidence
    fd, ep = tempfile.mkstemp(suffix=".db"); os.close(fd)
    store = EvidenceStore(ep)
    store.record(Evidence(department="travel", project="surmount_travels", episode="L-1", confidence=0.8, cost=0.0))
    store.record(Evidence(department="travel", project="surmount_travels", episode="L-2", confidence=0.6, cost=0.0))
    import saathi.evidence.store as es
    monkeypatch.setattr(es, "_default", store)
    monkeypatch.setattr(es, "default_store", lambda: store)

    ov = overview({"key": "surmount_travels", "department": "travel", "name": "Grow Surmount Travels"})
    assert ov["kpis"]["evidence"] == 2
    assert ov["kpis"]["avg_confidence"] == 0.7
    assert len(ov["recent_evidence"]) == 2
