"""AI Lab — Prompt Registry (versioning, evaluation, rollback, leaderboard)."""
from saathi.ai_lab import PromptRegistry


def _reg(tmp_path):
    return PromptRegistry(db_path=str(tmp_path / "lab.db"))


def test_register_versions_and_active(tmp_path):
    r = _reg(tmp_path)
    v1 = r.register("hcg.signal", "analyse {market}", purpose="swing", author="Claude Code")
    v2 = r.register("hcg.signal", "analyse {market} carefully", notes="tighter")
    assert v1 == 1 and v2 == 2
    assert r.active("hcg.signal").version == 2          # newest is active
    assert len(r.versions("hcg.signal")) == 2


def test_render_uses_active_version(tmp_path):
    r = _reg(tmp_path)
    r.register("greet", "Hello {name} v1")
    r.register("greet", "Hi {name} v2")
    assert r.render("greet", name="Ajay") == "Hi Ajay v2"


def test_render_missing_raises(tmp_path):
    r = _reg(tmp_path)
    try:
        r.render("nope")
        assert False, "should raise"
    except KeyError:
        pass


def test_eval_attaches_and_leaderboard_ranks(tmp_path):
    r = _reg(tmp_path)
    r.register("p", "a")           # v1
    r.register("p", "b")           # v2 (active)
    r.record_eval("p", 1, score=0.91, latency_ms=2400, cost=0.003, failures=12)
    r.record_eval("p", 2, score=0.74)
    lb = r.leaderboard("p")
    assert lb[0]["version"] == 1 and lb[0]["score"] == 0.91   # best first
    assert r.active("p").version == 2 and r.active("p").score == 0.74


def test_rollback_sets_active(tmp_path):
    r = _reg(tmp_path)
    r.register("p", "v1")
    r.register("p", "v2")
    assert r.active("p").version == 2
    assert r.rollback("p", 1) is True
    assert r.active("p").version == 1
    assert r.rollback("p", 99) is False                # unknown version


def test_catalog_summarizes(tmp_path):
    r = _reg(tmp_path)
    r.register("a", "x", project="mr-yeti"); r.register("a", "y", project="mr-yeti")
    r.register("b", "z", project="pielts")
    r.record_eval("a", 2, score=0.8)
    cat = {c["name"]: c for c in r.catalog()}
    assert cat["a"]["versions"] == 2 and cat["a"]["active_version"] == 2
    assert cat["a"]["active_score"] == 0.8 and cat["a"]["project"] == "mr-yeti"
    assert cat["b"]["versions"] == 1 and cat["b"]["active_score"] is None
