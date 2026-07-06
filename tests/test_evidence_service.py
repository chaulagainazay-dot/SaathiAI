"""Evidence Service (SaathiOS shared memory) — universal schema, store, adapters."""
import tempfile, os
from saathi.evidence.schema import Evidence, row_to_dict, COLUMNS
from saathi.evidence.store import EvidenceStore
from saathi.evidence.adapters import from_studio_production, from_pielts_essay, ADAPTERS, ingest


def _store():
    fd, path = tempfile.mkstemp(suffix=".db"); os.close(fd)
    return EvidenceStore(path)


def _prod():
    return {"episode": "EP-021", "status": "ready", "est_seconds": 60,
            "plan": {"brand": "mr_yeti", "topic": "Present Perfect"},
            "research": {"summary": "s", "key_facts": [1], "common_mistakes": [1], "examples": [1]},
            "creative": {"story_arc": "a", "hook_style": "q", "cta": "c", "visual_direction": "v"},
            "script": {"hook": "h", "scenes": [1, 2, 3], "cta": "c", "seo": {"title": "t"}},
            "scene_package": {"scenes": [1, 2, 3]},
            "render_plan": {"scenes": [1], "adapter": "ffmpeg", "engines": {"image": "flux", "voice": "kokoro"}},
            "publish_plan": {"platforms": [{"platform": "youtube"}, {"platform": "tiktok"}], "master": {"title": "t"}}}


def test_schema_roundtrip():
    ev = Evidence(department="ai_studio", episode="EP-1", confidence=0.9, metrics={"ctr": 6.4})
    row = ev.to_row()
    assert len(row) == len(COLUMNS)
    d = row_to_dict(row)
    assert d["department"] == "ai_studio" and d["metrics"]["ctr"] == 6.4


def test_store_record_and_query():
    st = _store()
    st.record(Evidence(department="ai_studio", episode="EP-1", cost=0.03, confidence=0.94))
    st.record(Evidence(department="pielts", episode="ES-9", confidence=0.8))
    assert st.count() == 2
    assert st.count(department="ai_studio") == 1
    q = st.query(department="ai_studio")
    assert len(q) == 1 and q[0]["episode"] == "EP-1"


def test_studio_adapter_makes_episode_plus_stage_rows():
    evs = from_studio_production(_prod())
    assert len(evs) == 7                                     # 1 episode + 6 stage rows
    ep = evs[0]
    assert ep.department == "ai_studio" and ep.episode == "EP-021" and ep.project == "mr_yeti"
    assert ep.confidence == 1.0 and ep.cost == 0.03          # all artifacts complete
    assert ep.metrics["publish_targets"] == ["youtube", "tiktok"]
    render = next(e for e in evs if e.director == "render")
    assert "ffmpeg" in render.provider and "flux" in render.provider


def test_ingest_persists_via_registry():
    st = _store()
    ids = ingest("ai_studio", _prod(), store=st)
    assert len(ids) == 7
    assert len(st.episodes("ai_studio")) == 1               # grouped by episode
    assert st.stats()["departments"]["ai_studio"]["count"] == 7


def test_pielts_adapter_and_registry_coverage():
    evs = from_pielts_essay({"essay_id": "ES-3", "band": 6.5, "prompt_version": "v4", "confidence": 0.88})
    assert evs[0].department == "pielts" and evs[0].metrics["band"] == 6.5
    assert {"ai_studio", "pielts", "hcg", "cafeteria"} <= set(ADAPTERS)


def test_attach_recommendation():
    st = _store()
    ev = Evidence(department="ai_studio", episode="EP-2")
    st.record(ev)
    assert st.attach_recommendation(ev.id, "Try Hook v12") is True
    assert st.query(episode="EP-2")[0]["recommendation"] == "Try Hook v12"
