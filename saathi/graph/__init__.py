"""Knowledge Graph — shared semantic structure for all of SaathiAI (M2 Phase 4).

Backend-agnostic (AP-02): departments use ``KnowledgeGraph``, never Neo4j/SQLite.
Relationships are first-class knowledge (AP-19). Evolution versions, never
overwrites — "why do we use Renderer Y now?" stays answerable.
"""
from saathi.graph.types import NodeType, EdgeType
from saathi.graph.backend import (
    GraphBackend, SQLiteGraphBackend, GraphNode, GraphEdge,
)
from saathi.graph.service import KnowledgeGraph

__all__ = [
    "NodeType", "EdgeType", "GraphBackend", "SQLiteGraphBackend",
    "GraphNode", "GraphEdge", "KnowledgeGraph",
]
