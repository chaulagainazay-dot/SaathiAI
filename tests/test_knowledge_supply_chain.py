"""Knowledge Supply Chain — trust, lifecycle, director ratings, consult, reading queue."""
import tempfile, os
from saathi.knowledge_library.store import LibraryStore, default_trust, STATUSES
from saathi.knowledge_library.queue import QueueStore, seed_queue


def _s():
    fd, p = tempfile.mkstemp(suffix=".db"); os.close(fd)
    return LibraryStore(p)


def test_default_trust_by_source_type():
    assert default_trust("book") == 5 and default_trust("gov") == 5
    assert default_trust("github") == 4 and default_trust("youtube") == 3
    assert default_trust("reddit") == 2 and default_trust("ai_notes") == 1


def test_add_assigns_trust_and_lifecycle():
    s = _s()
    a = s.add(title="Docs", url="u1", source_type="doc")
    b = s.add(title="Blog", url="u2", source_type="blog")
    assert a["trust"] == 5 and b["trust"] == 3
    assert a["status"] == "summarized" and a["director_ratings"] == {}


def test_status_and_trust_and_rating_updates():
    s = _s()
    x = s.add(title="A", url="u", source_type="github")
    assert s.set_status(x["id"], "director_ready") is True
    assert s.set_status(x["id"], "bogus") is False
    assert s.set_trust(x["id"], 2) is True
    assert s.rate_director(x["id"], "research", 5) is True
    g = s.get(x["id"])
    assert g["status"] == "director_ready" and g["trust"] == 2
    assert g["director_ratings"]["research"] == 5


def test_search_ranks_higher_trust_first():
    s = _s()
    s.add(title="low", url="l", source_type="reddit", summary="agent evaluation", tags=["evaluation"])
    s.add(title="high", url="h", source_type="book", summary="agent evaluation", tags=["evaluation"])
    hits = s.search("evaluation")
    assert hits[0]["title"] == "high"                    # same relevance → higher trust wins


def test_consult_records_influence():
    s = _s()
    x = s.add(title="A", url="u", source_type="book", summary="planning multi-agent", tags=["planning"])
    assert s.get(x["id"])["influence"] == 0
    hits = s.consult("planning", limit=3)
    assert hits and s.get(x["id"])["influence"] == 1     # consulting bumps the counter


def test_reading_queue_seed_and_status():
    fd, p = tempfile.mkstemp(suffix=".db"); os.close(fd)
    q = QueueStore(p)
    assert seed_queue(q) >= 10
    assert seed_queue(q) == 0                             # idempotent
    pend = q.list(status="pending")
    assert any("OpenHands" in i["title"] for i in pend)
    top = q.list()[0]
    assert top["priority"] == 5                           # sorted priority desc
    assert q.set_status(top["id"], "imported") is True
