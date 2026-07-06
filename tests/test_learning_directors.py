"""Learning layer — 3 recommend-only Directors + Recommendation schema/store."""
import tempfile, os
from saathi.learning.recommendation import Recommendation, RecommendationStore
from saathi.learning.directors import technical, educational, business


def _store():
    fd, path = tempfile.mkstemp(suffix=".db"); os.close(fd)
    return RecommendationStore(path)


def _studio_rows(conf):
    return [{"id": f"r{i}", "director": "render", "confidence": conf, "cost": 0.0,
             "provider": "ffmpeg", "metrics": {}} for i in range(4)]


def test_technical_flags_low_confidence_director():
    recs = technical(_studio_rows(0.6))          # 60% < 85% bar
    assert len(recs) == 1
    r = recs[0]
    assert r.category == "technical" and r.affected_director == "render"
    assert r.requires_approval is True and r.status == "pending"
    assert r.priority in ("high", "medium", "low") and len(r.evidence) == 4


def test_technical_stays_silent_when_quality_is_high():
    assert technical(_studio_rows(0.95)) == []   # nothing to fix → no noise


def test_technical_needs_minimum_sample():
    assert technical(_studio_rows(0.5)[:2]) == []  # < 3 runs → no recommendation


def test_educational_from_low_bands():
    pielts = [{"id": f"e{i}", "metrics": {"band": 5.0, "topic": "Present Perfect"}} for i in range(4)]
    recs = educational(studio_rows=[], pielts_rows=pielts)
    assert any(r.category == "educational" and "Present Perfect" in r.problem for r in recs)
    assert all(r.requires_approval for r in recs)


def test_business_hcg_win_rate():
    hcg = [{"id": f"t{i}", "status": "loss", "metrics": {}} for i in range(4)]
    recs = business({"hcg": hcg})
    assert any(r.department == "hcg" and "win rate" in r.problem.lower() for r in recs)


def test_store_records_lists_and_decides():
    st = _store()
    rec = Recommendation(category="technical", problem="p", recommendation="do x",
                         affected_director="render", priority="high", confidence=0.9)
    st.record(rec)
    pend = st.list(status="pending")
    assert len(pend) == 1 and pend[0]["affected_director"] == "render"
    assert st.decide(rec.id, True, implemented_in="script-director@v18") is True
    assert st.decide(rec.id, True) is False       # already decided, not pending
    assert st.list(status="accepted")[0]["implemented_in"] == "script-director@v18"


def test_upsert_unique_avoids_duplicate_pending():
    st = _store()
    a = Recommendation(category="technical", problem="same", recommendation="x", affected_director="render")
    b = Recommendation(category="technical", problem="same", recommendation="x2", affected_director="render")
    st.upsert_unique(a); st.upsert_unique(b)
    assert len(st.list(status="pending")) == 1     # collapsed to one
