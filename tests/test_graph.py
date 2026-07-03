"""Knowledge Graph tests (M2 Phase 4a) — backend-agnostic API, AP-12 + AP-19.

Covers: node/edge upsert (idempotent), the rich ontology, versioned evolution
(supersede, never delete — "why Renderer Y now?"), query engine (what_supports,
depends_on, dependents, governing decisions, goal contributors, path), and
backend independence. In-memory SQLite; no Neo4j, no network.
"""
import pytest

from saathi.graph import KnowledgeGraph, NodeType, EdgeType, SQLiteGraphBackend


@pytest.fixture
def kg():
    return KnowledgeGraph(backend=SQLiteGraphBackend(":memory:"))


# ── registry: idempotent upsert ───────────────────────────────────────────
def test_upsert_node_is_idempotent(kg):
    a = kg.upsert_node(NodeType.CAPABILITY, "AI Studio")
    b = kg.upsert_node(NodeType.CAPABILITY, "AI Studio")
    assert a.node_id == b.node_id                 # same node, not a duplicate
    assert kg.counts()["nodes"] == 1


def test_relate_creates_edge(kg):
    cap = kg.upsert_node(NodeType.CAPABILITY, "Storage Intelligence")
    prod = kg.upsert_node(NodeType.PRODUCT, "AI Studio")
    kg.relate(cap, EdgeType.USED_BY, prod)
    assert kg.counts()["edges"] == 1
    assert [n.name for n in kg.neighbors(cap, EdgeType.USED_BY)] == ["AI Studio"]


# ── evolution: version, never overwrite ───────────────────────────────────
def test_supersede_versions_and_stays_answerable(kg):
    old = kg.upsert_node(NodeType.TOOL, "Renderer X", {"role": "educational videos"})
    new = kg.supersede(old, "Renderer Y", {"reason": "consistently outperforms X"})
    assert new.version == 2
    # old is superseded but NOT deleted — history preserved
    old_refetched = kg.backend.get_node(old.node_id)
    assert old_refetched.superseded_by == new.node_id
    # "why are we using Renderer Y?" → SUPERSEDES edge back to X + its reason
    superseded = kg.neighbors(new, EdgeType.SUPERSEDES, "out")
    assert superseded[0].name == "Renderer X"
    assert new.properties["reason"] == "consistently outperforms X"
    # current_version follows the chain to the head
    assert kg.current_version(old).node_id == new.node_id


# ── query engine (no Cypher) ──────────────────────────────────────────────
def test_what_supports_traces_evidence(kg):
    knowledge = kg.upsert_node(NodeType.KNOWLEDGE, "Hooks under 3s retain more")
    ep1 = kg.upsert_node(NodeType.EPISODE, "episode-231")
    ep2 = kg.upsert_node(NodeType.EPISODE, "episode-455")
    kg.relate(knowledge, EdgeType.DERIVED_FROM, ep1)
    kg.relate(knowledge, EdgeType.DERIVED_FROM, ep2)
    supports = kg.what_supports(knowledge)
    assert {n.name for n in supports} == {"episode-231", "episode-455"}


def test_depends_on_and_dependents(kg):
    studio = kg.upsert_node(NodeType.CAPABILITY, "AI Studio")
    storage = kg.upsert_node(NodeType.CAPABILITY, "Storage Intelligence")
    kg.relate(studio, EdgeType.DEPENDS_ON, storage)
    assert [n.name for n in kg.depends_on(studio)] == ["Storage Intelligence"]
    # "what depends on Storage Intelligence?"
    assert [n.name for n in kg.dependents_of(storage)] == ["AI Studio"]


def test_governing_decision(kg):
    adr = kg.upsert_node(NodeType.DECISION, "ADR: AI Director above Storyboard")
    cap = kg.upsert_node(NodeType.CAPABILITY, "AI Studio")
    kg.relate(adr, EdgeType.GOVERNS, cap)
    assert [n.name for n in kg.governing_decisions(cap)] == ["ADR: AI Director above Storyboard"]


def test_goal_contribution_question(kg):
    """Which capabilities contribute toward the financial goal? Almost no AI
    system can answer this — the graph can."""
    goal = kg.upsert_node(NodeType.GOAL, "Revenue $7,938,838.98",
                          {"target": 7938838.98})
    studio = kg.upsert_node(NodeType.CAPABILITY, "AI Studio")
    pielts = kg.upsert_node(NodeType.CAPABILITY, "pielts")
    kg.relate(studio, EdgeType.CONTRIBUTES_TO, goal)
    kg.relate(pielts, EdgeType.CONTRIBUTES_TO, goal)
    contributors = kg.contributors_to_goal(goal)
    assert {n.name for n in contributors} == {"AI Studio", "pielts"}


def test_path_explains_goal_to_evidence(kg):
    goal = kg.upsert_node(NodeType.GOAL, "Revenue Goal")
    strat = kg.upsert_node(NodeType.STRATEGY, "Content Growth")
    cap = kg.upsert_node(NodeType.CAPABILITY, "AI Studio")
    ep = kg.upsert_node(NodeType.EPISODE, "video-published")
    kg.relate(goal, EdgeType.ACHIEVED_BY, strat)
    kg.relate(strat, EdgeType.IMPLEMENTED_BY, cap)
    kg.relate(cap, EdgeType.DERIVED_FROM, ep)
    trail = kg.path(goal, ep)
    assert trail is not None
    assert [n.name for n in trail] == ["Revenue Goal", "Content Growth", "AI Studio", "video-published"]


def test_no_path_returns_none(kg):
    a = kg.upsert_node(NodeType.GOAL, "G")
    b = kg.upsert_node(NodeType.EPISODE, "E")
    assert kg.path(a, b) is None


# ── backend independence (AP-02) ──────────────────────────────────────────
def test_service_only_touches_backend_interface():
    """A fake backend proves the service never reaches for SQLite/Neo4j directly."""
    calls = []

    class RecordingBackend(SQLiteGraphBackend):
        def add_node(self, *a, **k):
            calls.append("add_node")
            return super().add_node(*a, **k)

    kg = KnowledgeGraph(backend=RecordingBackend(":memory:"))
    kg.upsert_node(NodeType.GOAL, "X")
    assert "add_node" in calls          # went through the backend interface


def test_events_published():
    events = []
    kg = KnowledgeGraph(backend=SQLiteGraphBackend(":memory:"),
                        publish=lambda n, p: events.append(n))
    a = kg.upsert_node(NodeType.CAPABILITY, "A")
    b = kg.upsert_node(NodeType.PRODUCT, "B")
    kg.relate(a, EdgeType.USED_BY, b)
    kg.supersede(a, "A2")
    assert "kg.node_created" in events
    assert "kg.edge_created" in events
    assert "kg.node_superseded" in events
