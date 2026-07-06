"""PIELTS business event source → Evidence, end-to-end through the bus."""
import tempfile, os
from saathi.businesses import pielts, HANDLERS
from saathi.events.bus import EventBus
from saathi.evidence.store import EvidenceStore


def test_essay_scored_becomes_band_evidence():
    evs = pielts.handle("essay.scored", {"essay_id": "ES-1", "band": 5.5, "topic": "Present Perfect",
                                         "prompt_version": "v4", "confidence": 0.8, "user_id": "u9"})
    assert len(evs) == 1
    e = evs[0]
    assert e.department == "pielts" and e.metrics["band"] == 5.5 and e.metrics["topic"] == "Present Perfect"
    assert e.prompt_version == "v4" and e.metrics["user"] == "u9"


def test_quiz_completed_computes_accuracy():
    evs = pielts.handle("quiz.completed", {"correct": 7, "total": 10, "topic": "Articles"})
    assert evs[0].metrics["accuracy"] == 0.7 and evs[0].confidence == 0.7


def test_mistake_and_lesson_and_feedback_covered():
    assert pielts.handle("mistake.detected", {"mistake": "wrong tense", "topic": "Past"})[0].status == "mistake"
    assert pielts.handle("lesson.completed", {"topic": "Nouns", "seconds": 120})[0].director == "curriculum"
    assert pielts.handle("user.feedback", {"rating": 5})[0].feedback["rating"] == 5
    assert pielts.handle("subscription.started", {"plan": "premium", "amount": 500})[0].status == "subscribed"


def test_raw_signals_produce_no_evidence():
    assert pielts.handle("word.learned", {"word": "ubiquitous"}) == []
    assert pielts.handle("streak.updated", {"days": 7}) == []


def test_registry_has_all_five_businesses():
    assert set(HANDLERS) == {"pielts", "hcg", "cafeteria", "travel", "ai_studio"}


def test_bus_routes_pielts_events_to_evidence(monkeypatch):
    fd, ep = tempfile.mkstemp(suffix=".db"); os.close(fd)
    store = EvidenceStore(ep)
    import saathi.evidence.store as es
    monkeypatch.setattr(es, "_default", store)
    monkeypatch.setattr(es, "default_store", lambda: store)
    fd2, bp = tempfile.mkstemp(suffix=".db"); os.close(fd2)
    bus = EventBus(bp)
    r1 = bus.emit("essay.scored", "pielts", {"essay_id": "ES-2", "band": 6.0, "topic": "Writing Task 2"}, subject="ES-2")
    r2 = bus.emit("mistake.detected", "pielts", {"mistake": "subject-verb", "topic": "Grammar"})
    r3 = bus.emit("word.learned", "pielts", {"word": "x"})            # raw → no evidence
    assert len(r1["evidence_ids"]) == 1 and len(r2["evidence_ids"]) == 1 and r3["evidence_ids"] == []
    assert store.count(department="pielts") == 2
