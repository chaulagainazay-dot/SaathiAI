"""Knowledge Library — source catalog + honest importer."""
import tempfile, os
from saathi.knowledge_library.store import LibraryStore
from saathi.knowledge_library.importer import (_parse_repo_url, _tags, _directors_for,
                                               _summary, seed_defaults)


def _s():
    fd, p = tempfile.mkstemp(suffix=".db"); os.close(fd)
    return LibraryStore(p)


def test_add_dedupes_by_url_and_searches():
    s = _s()
    s.add(title="AI Agents Guide", url="https://x/a", category="AI Engineering",
          tags=["langgraph", "evaluation"], related_directors=["research"],
          key_lessons=["Evaluation-first"], summary="production agents")
    s.add(title="AI Agents Guide v2", url="https://x/a", category="AI Engineering")  # same url → update
    assert len(s.list()) == 1
    hits = s.search("evaluation")
    assert hits and hits[0]["tags"]


def test_search_by_director_and_tag_and_category():
    s = _s()
    s.add(title="A", url="u1", category="AI Engineering", tags=["memory"], related_directors=["learning"])
    s.add(title="B", url="u2", category="Trading", tags=["risk"], related_directors=["signal_engine"])
    assert len(s.search(director="learning")) == 1
    assert len(s.search(tag="risk")) == 1
    assert len(s.search(category="Trading")) == 1
    assert s.categories()["AI Engineering"] == 1


def test_parse_repo_url_variants():
    assert _parse_repo_url("https://github.com/Nicolepcx/ai-agents-the-definitive-guide.git") == \
        ("Nicolepcx", "ai-agents-the-definitive-guide")
    assert _parse_repo_url("https://github.com/o/r") == ("o", "r")
    assert _parse_repo_url("https://gitlab.com/o/r") is None


def test_tag_and_director_inference_is_from_content():
    tags = _tags("This repo covers LangGraph, evaluation, memory and safety for multi-agent systems.")
    assert "langgraph" in tags and "evaluation" in tags and "memory" in tags
    dirs = _directors_for(tags)
    assert "research" in dirs or "learning" in dirs   # inferred, not invented


def test_summary_skips_badges_and_headings():
    md = "# Title\n\n[![badge](x)](y)\n\nThis is the real description of the project.\n"
    assert _summary(md).startswith("This is the real description")


def test_seed_defaults_adds_the_book_repo():
    s = _s()
    assert seed_defaults(s) == 1
    assert seed_defaults(s) == 0                       # idempotent
    src = s.find(url="https://github.com/Nicolepcx/ai-agents-the-definitive-guide")
    assert src and "research" in src["related_directors"]
    assert any("Evaluation" in l for l in src["key_lessons"])
