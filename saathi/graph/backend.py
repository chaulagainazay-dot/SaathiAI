"""Graph backends — the swappable store behind the KnowledgeGraph (M2 Phase 4a).

AP-02 (Provider Independence): the platform talks to ``KnowledgeGraph``, never to
a backend directly. ``GraphBackend`` is the interface; ``SQLiteGraphBackend`` is
the Phase-1 implementation; a ``Neo4jGraphBackend`` is a drop-in later with zero
caller changes.

Nodes and edges are versioned and never deleted — evolution creates a new
version and a SUPERSEDES edge (Graph Evolution Engine).
"""
from __future__ import annotations

import json
import sqlite3
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from saathi.graph.types import NodeType, EdgeType


@dataclass
class GraphNode:
    node_id: int
    node_type: NodeType
    name: str
    properties: dict = field(default_factory=dict)
    confidence: float = 1.0
    version: int = 1
    superseded_by: int | None = None
    created_at: float = 0.0


@dataclass
class GraphEdge:
    edge_id: int
    from_id: int
    to_id: int
    relationship: EdgeType
    properties: dict = field(default_factory=dict)
    confidence: float = 1.0


class GraphBackend(ABC):
    """The interface every backend implements. Departments never see this —
    they use KnowledgeGraph, which uses a backend."""

    @abstractmethod
    def add_node(self, node_type: NodeType, name: str, properties: dict,
                 confidence: float, version: int) -> int: ...

    @abstractmethod
    def get_node(self, node_id: int) -> GraphNode | None: ...

    @abstractmethod
    def find_node(self, node_type: NodeType, name: str) -> GraphNode | None: ...

    @abstractmethod
    def set_superseded(self, old_id: int, new_id: int) -> None: ...

    @abstractmethod
    def nodes_of_type(self, node_type: NodeType) -> list[GraphNode]: ...

    @abstractmethod
    def add_edge(self, from_id: int, to_id: int, relationship: EdgeType,
                 properties: dict, confidence: float) -> int: ...

    @abstractmethod
    def edges_from(self, node_id: int, relationship: EdgeType | None) -> list[GraphEdge]: ...

    @abstractmethod
    def edges_to(self, node_id: int, relationship: EdgeType | None) -> list[GraphEdge]: ...

    @abstractmethod
    def counts(self) -> dict: ...


_SCHEMA = """
CREATE TABLE IF NOT EXISTS kg_nodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    node_type TEXT NOT NULL,
    name TEXT NOT NULL,
    properties TEXT DEFAULT '{}',
    confidence REAL DEFAULT 1.0,
    version INTEGER DEFAULT 1,
    superseded_by INTEGER,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_node_type ON kg_nodes(node_type);
CREATE INDEX IF NOT EXISTS idx_node_name ON kg_nodes(name);

CREATE TABLE IF NOT EXISTS kg_edges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_id INTEGER NOT NULL,
    to_id INTEGER NOT NULL,
    relationship TEXT NOT NULL,
    properties TEXT DEFAULT '{}',
    confidence REAL DEFAULT 1.0,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_edge_from ON kg_edges(from_id);
CREATE INDEX IF NOT EXISTS idx_edge_to ON kg_edges(to_id);
CREATE INDEX IF NOT EXISTS idx_edge_rel ON kg_edges(relationship);
"""


class SQLiteGraphBackend(GraphBackend):
    def __init__(self, db_path: "str | Path", now: Callable[[], float] = time.time):
        Path(str(db_path)).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(db_path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(_SCHEMA)
        self.db.commit()
        self._now = now

    def add_node(self, node_type, name, properties, confidence, version) -> int:
        cur = self.db.execute(
            "INSERT INTO kg_nodes (node_type, name, properties, confidence, version,"
            " created_at) VALUES (?,?,?,?,?,?)",
            (node_type.value, name, json.dumps(properties), confidence, version, self._now()))
        self.db.commit()
        return cur.lastrowid

    def get_node(self, node_id) -> GraphNode | None:
        r = self.db.execute("SELECT * FROM kg_nodes WHERE id=?", (node_id,)).fetchone()
        return self._node(r) if r else None

    def find_node(self, node_type, name) -> GraphNode | None:
        r = self.db.execute(
            "SELECT * FROM kg_nodes WHERE node_type=? AND name=? AND superseded_by IS NULL"
            " ORDER BY version DESC LIMIT 1", (node_type.value, name)).fetchone()
        return self._node(r) if r else None

    def set_superseded(self, old_id, new_id) -> None:
        self.db.execute("UPDATE kg_nodes SET superseded_by=? WHERE id=?", (new_id, old_id))
        self.db.commit()

    def nodes_of_type(self, node_type) -> list[GraphNode]:
        rows = self.db.execute("SELECT * FROM kg_nodes WHERE node_type=?",
                               (node_type.value,)).fetchall()
        return [self._node(r) for r in rows]

    def add_edge(self, from_id, to_id, relationship, properties, confidence) -> int:
        cur = self.db.execute(
            "INSERT INTO kg_edges (from_id, to_id, relationship, properties, confidence,"
            " created_at) VALUES (?,?,?,?,?,?)",
            (from_id, to_id, relationship.value, json.dumps(properties), confidence, self._now()))
        self.db.commit()
        return cur.lastrowid

    def edges_from(self, node_id, relationship) -> list[GraphEdge]:
        q = "SELECT * FROM kg_edges WHERE from_id=?"
        p = [node_id]
        if relationship is not None:
            q += " AND relationship=?"; p.append(relationship.value)
        return [self._edge(r) for r in self.db.execute(q, p).fetchall()]

    def edges_to(self, node_id, relationship) -> list[GraphEdge]:
        q = "SELECT * FROM kg_edges WHERE to_id=?"
        p = [node_id]
        if relationship is not None:
            q += " AND relationship=?"; p.append(relationship.value)
        return [self._edge(r) for r in self.db.execute(q, p).fetchall()]

    def counts(self) -> dict:
        n = self.db.execute("SELECT COUNT(*) c FROM kg_nodes").fetchone()["c"]
        e = self.db.execute("SELECT COUNT(*) c FROM kg_edges").fetchone()["c"]
        return {"nodes": n, "edges": e}

    @staticmethod
    def _node(r) -> GraphNode:
        return GraphNode(
            node_id=r["id"], node_type=NodeType(r["node_type"]), name=r["name"],
            properties=json.loads(r["properties"] or "{}"), confidence=r["confidence"],
            version=r["version"], superseded_by=r["superseded_by"], created_at=r["created_at"])

    @staticmethod
    def _edge(r) -> GraphEdge:
        return GraphEdge(
            edge_id=r["id"], from_id=r["from_id"], to_id=r["to_id"],
            relationship=EdgeType(r["relationship"]),
            properties=json.loads(r["properties"] or "{}"), confidence=r["confidence"])
