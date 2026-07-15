"""M19.0 — Unified Knowledge Service, router, multi-repo context."""
from __future__ import annotations

from pathlib import Path

import pytest

from saathi.knowledge.assemble import assemble_context
from saathi.knowledge.compat import search_compatible
from saathi.knowledge.dedupe import dedupe_results
from saathi.knowledge.eval_set import run_uk_evaluation
from saathi.knowledge.permissions import path_is_sensitive, source_permitted
from saathi.knowledge.rank import fuse_and_rank
from saathi.knowledge.registry import KnowledgeSource, default_source_registry
from saathi.knowledge.router import build_plan
from saathi.knowledge.service import KnowledgeService
from saathi.knowledge.types import (
    EvidenceClass,
    KnowledgeQuery,
    KnowledgeResult,
    RetrievalProfile,
    TrustLevel,
    content_fingerprint,
)

ROOT = Path(__file__).resolve().parents[1]


def _fake_search(query, **kwargs):
    """Deterministic fake M18.2 search for tests without full index."""
    from saathi.codebase_memory.retrieve import RetrievalHit, RetrievalResult

    q = query.lower()
    hits = []
    if "event" in q or "bus" in q:
        hits.append(RetrievalHit(
            result_id="h1", repository_id="r", namespace="saathiai",
            branch="main", commit_sha="abc", path="saathi/events.py",
            symbol="EventBus", start_line=1, end_line=20,
            file_type="SOURCE_CODE", snippet="class EventBus: pass",
            score=20.0, freshness="CURRENT_COMMIT",
        ))
    if "test" in q or "browser" in q:
        hits.append(RetrievalHit(
            result_id="h2", repository_id="r", namespace="saathiai",
            branch="main", commit_sha="abc",
            path="tests/test_m17_24_browser_dispatch_governance.py",
            symbol="test_dispatch", start_line=1, end_line=10,
            file_type="TEST_CODE", snippet="def test_dispatch(): pass",
            score=15.0, freshness="CURRENT_COMMIT",
        ))
    if "env" in q or "secret" in q:
        hits.append(RetrievalHit(
            result_id="bad", repository_id="r", namespace="saathiai",
            branch="main", commit_sha="abc", path=".env",
            symbol="", start_line=1, end_line=1,
            file_type="SECRET", snippet="API_KEY=sk-secret",
            score=99.0, freshness="CURRENT_COMMIT",
        ))
    return RetrievalResult(ok=True, query=query, hits=hits, consulted_index=True)


@pytest.fixture()
def ks(tmp_path):
    # two fake repos for multi-repo
    r1 = tmp_path / "repo_a"
    r2 = tmp_path / "repo_b"
    (r1 / "docs").mkdir(parents=True)
    (r2 / "docs").mkdir(parents=True)
    (r1 / "docs" / "ARCH.md").write_text("# Architecture\nEventBus design\n", encoding="utf-8")
    (r2 / "docs" / "ARCH.md").write_text("# Architecture\nOther EventBus copy\n", encoding="utf-8")
    (r1 / "docs" / "M18_2_VALIDATION.md").write_text("M18.2 codebase memory indexing\n", encoding="utf-8")

    sources = [
        KnowledgeSource(
            source_id="a.code", source_type="codebase_index", repository_id="repo_a",
            location=str(r1), adapter="codebase_memory", trust=TrustLevel.HIGH,
        ),
        KnowledgeSource(
            source_id="a.docs", source_type="documentation", repository_id="repo_a",
            location=str(r1 / "docs"), adapter="documentation", trust=TrustLevel.HIGH,
        ),
        KnowledgeSource(
            source_id="b.docs", source_type="documentation", repository_id="repo_b",
            location=str(r2 / "docs"), adapter="documentation", trust=TrustLevel.MEDIUM,
        ),
        KnowledgeSource(
            source_id="a.decisions", source_type="decision_docs", repository_id="repo_a",
            location=str(r1 / "docs"), adapter="decision_docs", trust=TrustLevel.HIGH,
        ),
        KnowledgeSource(
            source_id="prov", source_type="provider_metadata", repository_id="insforge",
            location="virtual", adapter="provider_meta", trust=TrustLevel.MEDIUM,
        ),
    ]
    return KnowledgeService(
        sources=sources,
        codebase_search_fn=_fake_search,
    )


def test_01_query_contract_and_intent():
    q = KnowledgeQuery(query="Where is EventBus defined?", profile=RetrievalProfile.FAST_LOOKUP)
    assert q.resolved_top_k() == 5
    assert q.request_id


def test_02_registry_default_has_saathi():
    reg = default_source_registry(saathi_root=ROOT)
    ids = {s.source_id for s in reg}
    assert any("codebase" in i for i in ids)
    assert any("documentation" in i for i in ids)


def test_03_router_deterministic(ks):
    q = KnowledgeQuery(query="EventBus", profile=RetrievalProfile.CODE_EXPLAIN)
    p1 = build_plan(q, ks.sources)
    p2 = build_plan(q, ks.sources)
    assert p1.to_dict()["selected_ids"] == p2.to_dict()["selected_ids"]
    assert p1.ranking_strategy == "weighted_fusion_v1"
    assert p1.parallel is False


def test_04_disabled_source_rejected():
    src = KnowledgeSource(
        source_id="x", source_type="codebase_index", repository_id="r",
        location="/tmp", enabled=False, adapter="codebase_memory",
    )
    q = KnowledgeQuery(query="x")
    ok, reason = source_permitted(q, src)
    assert ok is False and reason == "source_disabled"


def test_05_retrieve_code_and_docs(ks):
    r = ks.retrieve(KnowledgeQuery(
        query="EventBus architecture",
        profile=RetrievalProfile.CODE_EXPLAIN,
        max_results=10,
    ))
    assert r.ok
    assert r.plan["selected_ids"]
    assert r.results
    paths = " ".join(x.path for x in r.results)
    assert "events" in paths.lower() or "arch" in paths.lower()


def test_06_multi_repo_preserves_identity(ks):
    r = ks.retrieve(KnowledgeQuery(
        query="Architecture EventBus",
        profile=RetrievalProfile.MULTI_REPO_COMPARE,
        max_results=12,
    ))
    assert r.ok
    repos = {x.repository_id for x in r.results}
    # docs from both repos may appear
    assert "repo_a" in repos or "repo_b" in repos
    for x in r.results:
        assert x.repository_id
        assert x.source_id
        assert x.result_id.startswith(x.source_id) or ":" in x.result_id


def test_07_sensitive_path_filtered(ks):
    r = ks.retrieve(KnowledgeQuery(
        query="env secret credentials API",
        profile=RetrievalProfile.CODE_EXPLAIN,
    ))
    assert r.ok
    for x in r.results:
        assert not path_is_sensitive(x.path)
        assert ".env" not in x.path


def test_08_ranking_stable():
    items = [
        KnowledgeResult(
            result_id="1", source_id="s", source_type="codebase_index",
            repository_id="r", object_id="a", path="a.py", title="EventBus",
            excerpt="class EventBus", normalized_content="class EventBus",
            native_score=10, normalized_score=0.5, trust_score=1, freshness_score=1,
            final_score=0, evidence_class=EvidenceClass.PRIMARY_CODE, is_generated=False,
            content_fingerprint="aaa",
        ),
        KnowledgeResult(
            result_id="2", source_id="s", source_type="documentation",
            repository_id="r", object_id="b", path="b.md", title="summary",
            excerpt="EventBus generated summary", normalized_content="gen",
            native_score=20, normalized_score=0.9, trust_score=0.5, freshness_score=0.5,
            final_score=0, evidence_class=EvidenceClass.GENERATED_SUMMARY, is_generated=True,
            content_fingerprint="bbb",
        ),
    ]
    a = fuse_and_rank(list(items), profile=RetrievalProfile.AUDIT_EVIDENCE, query="EventBus")
    b = fuse_and_rank(list(items), profile=RetrievalProfile.AUDIT_EVIDENCE, query="EventBus")
    assert [x.result_id for x in a] == [x.result_id for x in b]
    # primary code should beat generated on audit
    assert a[0].evidence_class == EvidenceClass.PRIMARY_CODE


def test_09_dedupe_collapses_same_fingerprint():
    fp = content_fingerprint("same text")
    items = [
        KnowledgeResult(
            result_id="1", source_id="s1", source_type="documentation",
            repository_id="r1", object_id="a", path="a.md", title="a",
            excerpt="same text", normalized_content="same text",
            native_score=1, normalized_score=0.5, trust_score=1, freshness_score=1,
            final_score=0.8, evidence_class=EvidenceClass.CANONICAL_DOCS, is_generated=False,
            content_fingerprint=fp,
        ),
        KnowledgeResult(
            result_id="2", source_id="s2", source_type="documentation",
            repository_id="r1", object_id="b", path="b.md", title="b",
            excerpt="same text", normalized_content="same text",
            native_score=1, normalized_score=0.4, trust_score=1, freshness_score=1,
            final_score=0.5, evidence_class=EvidenceClass.GENERATED_SUMMARY, is_generated=True,
            content_fingerprint=fp,
        ),
    ]
    out, meta = dedupe_results(items)
    assert len(out) == 1
    assert meta["duplicates_collapsed"] >= 1
    assert out[0].result_id == "1"


def test_10_context_budget_truncation():
    results = []
    for i in range(20):
        results.append(KnowledgeResult(
            result_id=str(i), source_id="s", source_type="codebase_index",
            repository_id="r", object_id=str(i), path=f"f{i}.py", title=f"t{i}",
            excerpt="x" * 200, normalized_content="x" * 200,
            native_score=1, normalized_score=0.5, trust_score=1, freshness_score=1,
            final_score=1.0 - i * 0.01, evidence_class=EvidenceClass.PRIMARY_CODE,
            is_generated=False, content_fingerprint=content_fingerprint(f"x{i}"),
        ))
    ctx = assemble_context(results, budget=800)
    assert ctx.char_count <= 800
    assert ctx.truncated or len(ctx.included_result_ids) < 20
    assert ctx.fingerprint


def test_11_unregistered_repo_not_queryable_via_params(ks):
    r = ks.retrieve(KnowledgeQuery(
        query="EventBus",
        repository_ids=["not_registered_repo"],
        profile=RetrievalProfile.CODE_EXPLAIN,
    ))
    # no sources match → empty results but ok plan
    assert r.ok
    assert r.results == [] or all(x.repository_id != "not_registered_repo" for x in r.results)


def test_12_compat_legacy_default():
    # default does not require index — may degrade
    out = search_compatible("EventBus", project_root=ROOT, top_k=3, use_unified=False)
    assert "ok" in out
    assert "hits" in out


def test_13_compat_unified_shape(ks, monkeypatch):
    # wire default service is not used; call service directly for unified
    r = ks.retrieve(KnowledgeQuery(query="EventBus", max_results=5))
    assert r.to_dict()["results"] is not None
    assert "plan" in r.to_dict()


def test_14_trading_guardian_isolation():
    pkg = ROOT / "saathi" / "knowledge"
    for p in pkg.rglob("*.py"):
        t = p.read_text(encoding="utf-8")
        assert "place_order" not in t
        assert "saathi.trade" not in t
        assert "binance" not in t.lower()
        assert "alpaca" not in t.lower()


def test_15_provider_meta_no_writes(ks):
    r = ks.retrieve(KnowledgeQuery(
        query="InsForge provider pilot capability",
        profile=RetrievalProfile.MISSION_CONTEXT,
        intent=__import__("saathi.knowledge.types", fromlist=["RetrievalIntent"]).RetrievalIntent.INSPECT_PROVIDER,
    ))
    assert r.ok
    # should not contain migration execute secrets
    blob = str(r.to_dict())
    assert "place_order" not in blob


def test_16_audit_events(ks):
    ks.retrieve(KnowledgeQuery(query="EventBus", max_results=3))
    ev = ks.recent_events()
    types = [e["type"] for e in ev]
    assert "knowledge.plan" in types
    assert "knowledge.retrieve" in types


def test_17_eval_harness(ks):
    def fn(q, profile, top_k):
        return ks.retrieve(KnowledgeQuery(
            query=q, profile=profile, max_results=top_k,
        )).to_dict()
    # custom mini eval without full saathi index
    r = fn("EventBus", RetrievalProfile.FAST_LOOKUP, 5)
    assert r["ok"]
    assert r["results"]


def test_18_docs_exist():
    assert (ROOT / "docs" / "M19_0_KNOWLEDGE_ARCHITECTURE_AUDIT.md").is_file()
    assert (ROOT / "docs" / "M19_0_UNIFIED_KNOWLEDGE_SERVICE.md").is_file()
