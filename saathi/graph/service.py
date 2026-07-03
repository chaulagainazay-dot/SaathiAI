"""KnowledgeGraph — the service every department talks to (M2 Phase 4a).

Departments say ``KnowledgeGraph``, never ``Neo4j`` / ``SQLite`` (AP-02) and never
write Cypher. The service wraps a pluggable backend and provides:

  * upsert nodes/edges (Graph Registry — the only writer of graph structure)
  * evolution (supersede: new version + SUPERSEDES edge, never delete)
  * query methods (what_supports / depends_on / contributors_to_goal / path / why)

Relationships are first-class (AP-19): the interesting questions are about edges.
"""
from __future__ import annotations

from collections import deque
from typing import Callable

from saathi.graph.backend import GraphBackend, SQLiteGraphBackend, GraphNode, GraphEdge
from saathi.graph.types import NodeType, EdgeType


class KnowledgeGraph:
    def __init__(self, backend: GraphBackend | None = None, db_path: str | None = None,
                 publish: "Callable[[str, dict], None] | None" = None):
        if backend is None:
            backend = SQLiteGraphBackend(db_path or ":memory:")
        self.backend = backend
        self._publish_fn = publish

    def _publish(self, name: str, payload: dict) -> None:
        if self._publish_fn is not None:
            self._publish_fn(name, payload)

    # ── Graph Registry (the only structure writer) ────────────────────────
    def upsert_node(self, node_type: NodeType, name: str, properties: dict | None = None,
                    confidence: float = 1.0) -> GraphNode:
        existing = self.backend.find_node(node_type, name)
        if existing is not None:
            return existing
        nid = self.backend.add_node(node_type, name, properties or {}, confidence, version=1)
        self._publish("kg.node_created", {"node_id": nid, "type": node_type.value, "name": name})
        return self.backend.get_node(nid)

    def relate(self, from_node: GraphNode, relationship: EdgeType, to_node: GraphNode,
               properties: dict | None = None, confidence: float = 1.0) -> GraphEdge:
        eid = self.backend.add_edge(from_node.node_id, to_node.node_id, relationship,
                                    properties or {}, confidence)
        self._publish("kg.edge_created",
                      {"from": from_node.name, "rel": relationship.value, "to": to_node.name})
        return GraphEdge(eid, from_node.node_id, to_node.node_id, relationship,
                         properties or {}, confidence)

    # ── Graph Evolution Engine ────────────────────────────────────────────
    def supersede(self, old: GraphNode, new_name: str, properties: dict | None = None,
                  confidence: float = 1.0) -> GraphNode:
        """Knowledge changes — version, don't overwrite. Creates a new node,
        marks the old superseded, and links new -SUPERSEDES-> old so "why do we
        use X now?" stays answerable."""
        new_id = self.backend.add_node(old.node_type, new_name, properties or {},
                                       confidence, version=old.version + 1)
        self.backend.set_superseded(old.node_id, new_id)
        self.backend.add_edge(new_id, old.node_id, EdgeType.SUPERSEDES, {}, confidence)
        new_node = self.backend.get_node(new_id)
        self._publish("kg.node_superseded",
                      {"old": old.name, "new": new_name, "node_id": new_id})
        return new_node

    def current_version(self, node: GraphNode) -> GraphNode:
        """Follow the superseded_by chain to the live head. Re-fetches fresh
        state so a stale snapshot (captured before a supersede) still resolves."""
        cur = self.backend.get_node(node.node_id) or node
        seen = set()
        while cur.superseded_by is not None and cur.node_id not in seen:
            seen.add(cur.node_id)
            nxt = self.backend.get_node(cur.superseded_by)
            if nxt is None:
                break
            cur = nxt
        return cur

    # ── Graph Query Engine (no department writes Cypher) ──────────────────
    def neighbors(self, node: GraphNode, relationship: EdgeType | None = None,
                  direction: str = "out") -> list[GraphNode]:
        edges: list[GraphEdge] = []
        if direction in ("out", "both"):
            edges += self.backend.edges_from(node.node_id, relationship)
        if direction in ("in", "both"):
            edges += self.backend.edges_to(node.node_id, relationship)
        out = []
        for e in edges:
            other = e.to_id if e.from_id == node.node_id else e.from_id
            n = self.backend.get_node(other)
            if n is not None:
                out.append(n)
        return out

    def what_supports(self, node: GraphNode) -> list[GraphNode]:
        """Evidence behind a piece of knowledge (SUPPORTS / DERIVED_FROM)."""
        return (self.neighbors(node, EdgeType.SUPPORTS, "in")
                + self.neighbors(node, EdgeType.DERIVED_FROM, "out"))

    def depends_on(self, node: GraphNode) -> list[GraphNode]:
        return self.neighbors(node, EdgeType.DEPENDS_ON, "out")

    def dependents_of(self, node: GraphNode) -> list[GraphNode]:
        """Which capabilities depend on this one (e.g. 'what uses AI Studio?')."""
        return self.neighbors(node, EdgeType.DEPENDS_ON, "in")

    def improvements_for(self, capability: GraphNode) -> list[GraphNode]:
        return self.neighbors(capability, EdgeType.IMPROVED_BY, "out")

    def governing_decisions(self, capability: GraphNode) -> list[GraphNode]:
        """Which ADR introduced/governs this capability."""
        return self.neighbors(capability, EdgeType.GOVERNS, "in")

    def contributors_to_goal(self, goal: GraphNode) -> list[GraphNode]:
        """Which capabilities contribute toward a goal — the question almost no
        AI system can answer. Capability -CONTRIBUTES_TO-> Goal."""
        return self.neighbors(goal, EdgeType.CONTRIBUTES_TO, "in")

    def path(self, src: GraphNode, dst: GraphNode, max_depth: int = 6) -> list[GraphNode] | None:
        """BFS over the graph (both directions) — explainability without Cypher."""
        if src.node_id == dst.node_id:
            return [src]
        visited = {src.node_id}
        queue: deque[tuple[GraphNode, list[GraphNode]]] = deque([(src, [src])])
        while queue:
            node, trail = queue.popleft()
            if len(trail) > max_depth:
                continue
            for nb in self.neighbors(node, direction="both"):
                if nb.node_id == dst.node_id:
                    return trail + [nb]
                if nb.node_id not in visited:
                    visited.add(nb.node_id)
                    queue.append((nb, trail + [nb]))
        return None

    def counts(self) -> dict:
        return self.backend.counts()
