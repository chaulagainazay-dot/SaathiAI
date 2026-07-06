"""The universal Recommendation schema + store — the output of every Learning
Director. One shape, searchable, evidence-linked, decision-tracked.

The law: Learning Directors RECOMMEND, they never edit. A recommendation is a
proposal with evidence attached. The CEO accepts or rejects; only on acceptance
does anything flow to the Prompt Registry. Nothing changes automatically. This
mirrors a software release: evidence → recommendation → decision → registry →
production → evidence.
"""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

CATEGORIES = ("technical", "educational", "business")
PRIORITIES = ("high", "medium", "low")
STATUSES = ("pending", "accepted", "rejected", "implemented")

_COLUMNS = ["id", "timestamp", "category", "priority", "confidence", "department",
            "affected_director", "problem", "recommendation", "expected_improvement",
            "estimated_cost", "risk", "requires_approval", "status", "implemented_in",
            "result", "evidence"]
_JSON = {"evidence"}


@dataclass
class Recommendation:
    category: str                        # technical | educational | business
    problem: str
    recommendation: str
    department: str = ""
    affected_director: str = ""
    priority: str = "medium"
    confidence: float = 0.0
    expected_improvement: str = ""
    estimated_cost: str = "low"
    risk: str = "low"
    requires_approval: bool = True
    status: str = "pending"
    implemented_in: str = ""             # prompt version / run once accepted+deployed
    result: str = ""
    evidence: list = field(default_factory=list)   # evidence ids / episode ids backing it
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    timestamp: float = field(default_factory=time.time)

    def to_row(self) -> tuple:
        return (self.id, self.timestamp, self.category, self.priority, float(self.confidence),
                self.department, self.affected_director, self.problem, self.recommendation,
                self.expected_improvement, self.estimated_cost, self.risk,
                1 if self.requires_approval else 0, self.status, self.implemented_in,
                self.result, json.dumps(self.evidence))

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def _row_to_dict(row) -> dict:
    d = dict(zip(_COLUMNS, row))
    d["requires_approval"] = bool(d["requires_approval"])
    for c in _JSON:
        try:
            d[c] = json.loads(d[c]) if d[c] else []
        except Exception:
            d[c] = []
    return d


class RecommendationStore:
    def __init__(self, db_path: str | None = None):
        self.db_path = Path(db_path) if db_path else (Path.home() / ".saathi" / "recommendations.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _conn(self):
        return sqlite3.connect(str(self.db_path))

    def _init(self):
        cols = ", ".join(f"{c} {'REAL' if c in ('timestamp','confidence') else 'INTEGER' if c=='requires_approval' else 'TEXT'}"
                         for c in _COLUMNS)
        with self._conn() as c:
            c.execute(f"CREATE TABLE IF NOT EXISTS recommendation({cols}, PRIMARY KEY(id))")
            c.execute("CREATE INDEX IF NOT EXISTS idx_rec ON recommendation(category, status)")

    def record(self, rec: Recommendation) -> str:
        ph = ",".join("?" * len(_COLUMNS))
        with self._conn() as c:
            c.execute(f"INSERT OR REPLACE INTO recommendation({','.join(_COLUMNS)}) VALUES({ph})", rec.to_row())
        return rec.id

    def upsert_unique(self, rec: Recommendation) -> str:
        """Avoid duplicate pending recs for the same (director, problem) — refresh instead."""
        with self._conn() as c:
            row = c.execute(
                "SELECT id FROM recommendation WHERE affected_director=? AND problem=? AND status='pending'",
                (rec.affected_director, rec.problem)).fetchone()
        if row:
            rec.id = row[0]
        return self.record(rec)

    def list(self, *, category: str | None = None, status: str | None = None, limit: int = 50) -> list[dict]:
        where, args = [], []
        if category:
            where.append("category=?"); args.append(category)
        if status:
            where.append("status=?"); args.append(status)
        sql = "SELECT " + ",".join(_COLUMNS) + " FROM recommendation"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY (priority='high') DESC, confidence DESC, timestamp DESC LIMIT ?"
        args.append(limit)
        with self._conn() as c:
            return [_row_to_dict(r) for r in c.execute(sql, args).fetchall()]

    def decide(self, rec_id: str, accept: bool, *, implemented_in: str = "") -> bool:
        status = "accepted" if accept else "rejected"
        with self._conn() as c:
            cur = c.execute("UPDATE recommendation SET status=?, implemented_in=? WHERE id=? AND status='pending'",
                            (status, implemented_in, rec_id))
            return cur.rowcount > 0

    def counts(self) -> dict:
        with self._conn() as c:
            rows = c.execute("SELECT status, COUNT(*) FROM recommendation GROUP BY status").fetchall()
        return {r[0]: r[1] for r in rows}


_default = None
def default_store() -> RecommendationStore:
    global _default
    if _default is None:
        _default = RecommendationStore()
    return _default
