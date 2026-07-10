"""M9 Memory Engine — canonical normalized schema + durable store.

Fourteen tables in data/memory.db. Nothing is destroyed on delete: a tombstone
row is written and the embedding removed so vector search cannot return it,
while the source record is retained for provenance. Embeddings are stored as
raw float32 bytes with an embedding_version so re-embedding is controlled and
incompatible dimensions never mix.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parent.parent.parent.parent
DB_PATH = ROOT / "data" / "memory.db"

MEMORY_TYPES = {
    "working", "conversation", "episodic", "semantic", "procedural",
    "user", "business", "project", "agent", "document",
}
PRIVACY_LEVELS = {"public", "internal", "private", "sensitive"}
STATUSES = {"active", "reinforced", "stale", "archived", "expired",
            "superseded", "deleted"}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS memory_item(
  id TEXT PRIMARY KEY,
  namespace TEXT NOT NULL,            -- scope firewall key, e.g. user:ajay / project:pielts
  memory_type TEXT NOT NULL,
  content TEXT NOT NULL,
  normalized TEXT NOT NULL,           -- lowercased/tokenizable form for keyword match
  project_id TEXT DEFAULT '',
  user_scope TEXT DEFAULT '',
  agent_scope TEXT DEFAULT '',
  confidence REAL DEFAULT 0.5,
  importance REAL DEFAULT 0.5,
  freshness REAL DEFAULT 1.0,
  created_at REAL, updated_at REAL, last_accessed REAL DEFAULT 0,
  access_count INTEGER DEFAULT 0,
  expiry REAL,                        -- null = never
  privacy TEXT DEFAULT 'internal',
  retention TEXT DEFAULT 'standard',
  embedding_version TEXT DEFAULT '',
  checksum TEXT DEFAULT '',
  status TEXT DEFAULT 'active',
  provenance TEXT DEFAULT '{}',
  pinned INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS memory_version(
  id TEXT PRIMARY KEY, memory_id TEXT, content TEXT, confidence REAL,
  reason TEXT DEFAULT '', created_at REAL);
CREATE TABLE IF NOT EXISTS memory_source(
  id TEXT PRIMARY KEY, memory_id TEXT, source_type TEXT, source_id TEXT,
  citation TEXT DEFAULT '', created_at REAL);
CREATE TABLE IF NOT EXISTS memory_embedding(
  memory_id TEXT PRIMARY KEY, dim INTEGER, version TEXT,
  vector BLOB, norm REAL, created_at REAL);
CREATE TABLE IF NOT EXISTS memory_relation(
  id TEXT PRIMARY KEY, src_id TEXT, dst_id TEXT, relation TEXT,
  weight REAL DEFAULT 1.0, created_at REAL);
CREATE TABLE IF NOT EXISTS memory_access(
  id TEXT PRIMARY KEY, memory_id TEXT, actor TEXT, decision TEXT,
  reason TEXT DEFAULT '', created_at REAL);
CREATE TABLE IF NOT EXISTS memory_feedback(
  id TEXT PRIMARY KEY, memory_id TEXT, useful INTEGER, note TEXT DEFAULT '',
  created_at REAL);
CREATE TABLE IF NOT EXISTS memory_policy(
  id TEXT PRIMARY KEY, namespace TEXT, key TEXT, value TEXT, created_at REAL);
CREATE TABLE IF NOT EXISTS memory_namespace(
  namespace TEXT PRIMARY KEY, owner TEXT, kind TEXT, created_at REAL);
CREATE TABLE IF NOT EXISTS memory_summary(
  id TEXT PRIMARY KEY, namespace TEXT, content TEXT, created_at REAL);
CREATE TABLE IF NOT EXISTS memory_conflict(
  id TEXT PRIMARY KEY, memory_id TEXT, conflicts_with TEXT, kind TEXT,
  status TEXT DEFAULT 'open', created_at REAL);
CREATE TABLE IF NOT EXISTS memory_tombstone(
  id TEXT PRIMARY KEY, memory_id TEXT, namespace TEXT, reason TEXT,
  restorable INTEGER DEFAULT 1, created_at REAL);
CREATE TABLE IF NOT EXISTS retrieval_run(
  id TEXT PRIMARY KEY, query TEXT, namespaces TEXT, mode TEXT,
  result_count INTEGER, latency_ms REAL, avg_score REAL, created_at REAL);
CREATE TABLE IF NOT EXISTS retrieval_result(
  id TEXT PRIMARY KEY, run_id TEXT, memory_id TEXT, final_score REAL,
  semantic_score REAL, keyword_score REAL, reason TEXT DEFAULT '');
CREATE INDEX IF NOT EXISTS idx_mem_ns ON memory_item(namespace, status);
CREATE INDEX IF NOT EXISTS idx_mem_type ON memory_item(memory_type, status);
CREATE INDEX IF NOT EXISTS idx_mem_project ON memory_item(project_id);
CREATE INDEX IF NOT EXISTS idx_rel_src ON memory_relation(src_id);
CREATE INDEX IF NOT EXISTS idx_src_mem ON memory_source(memory_id);
"""


def _now() -> float:
    return time.time()


def _id() -> str:
    return uuid.uuid4().hex


def checksum(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def normalize(text: str) -> str:
    return " ".join(text.lower().split())


class MemoryStore:
    """All durable persistence for the M9 Memory Engine."""

    def __init__(self, db_path: str | Path | None = None):
        self.db_path = Path(db_path) if db_path else DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.executescript(_SCHEMA)

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(str(self.db_path))
        c.row_factory = sqlite3.Row
        return c

    # ── items ─────────────────────────────────────────────────────────────
    def add_item(self, *, namespace: str, memory_type: str, content: str,
                 project_id: str = "", user_scope: str = "", agent_scope: str = "",
                 confidence: float = 0.5, importance: float = 0.5,
                 privacy: str = "internal", retention: str = "standard",
                 expiry: Optional[float] = None, provenance: dict | None = None,
                 pinned: bool = False) -> str:
        if memory_type not in MEMORY_TYPES:
            raise ValueError(f"invalid memory_type: {memory_type}")
        if privacy not in PRIVACY_LEVELS:
            raise ValueError(f"invalid privacy: {privacy}")
        mid = _id()
        now = _now()
        with self._conn() as c:
            c.execute(
                "INSERT INTO memory_item(id,namespace,memory_type,content,normalized,"
                "project_id,user_scope,agent_scope,confidence,importance,freshness,"
                "created_at,updated_at,expiry,privacy,retention,checksum,status,"
                "provenance,pinned) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (mid, namespace, memory_type, content, normalize(content),
                 project_id, user_scope, agent_scope, confidence, importance, 1.0,
                 now, now, expiry, privacy, retention, checksum(content),
                 "active", json.dumps(provenance or {}), 1 if pinned else 0))
            c.execute("INSERT INTO memory_version VALUES(?,?,?,?,?,?)",
                      (_id(), mid, content, confidence, "created", now))
        return mid

    def get_item(self, mid: str) -> Optional[dict]:
        with self._conn() as c:
            row = c.execute("SELECT * FROM memory_item WHERE id=?", (mid,)).fetchone()
        return self._row(row) if row else None

    def _row(self, row) -> dict:
        d = dict(row)
        d["provenance"] = json.loads(d.get("provenance") or "{}")
        d["pinned"] = bool(d["pinned"])
        return d

    def update_item(self, mid: str, **fields) -> None:
        cols = {"confidence", "importance", "freshness", "status", "privacy",
                "retention", "expiry", "embedding_version", "content",
                "normalized", "pinned", "last_accessed", "access_count"}
        sets, args = ["updated_at=?"], [_now()]
        for k, v in fields.items():
            if k in cols:
                sets.append(f"{k}=?"); args.append(int(v) if k == "pinned" else v)
        args.append(mid)
        with self._conn() as c:
            c.execute(f"UPDATE memory_item SET {','.join(sets)} WHERE id=?", args)

    def touch(self, mid: str) -> None:
        with self._conn() as c:
            c.execute("UPDATE memory_item SET last_accessed=?, access_count=access_count+1 "
                      "WHERE id=?", (_now(), mid))

    def add_version(self, mid: str, content: str, confidence: float, reason: str):
        with self._conn() as c:
            c.execute("INSERT INTO memory_version VALUES(?,?,?,?,?,?)",
                      (_id(), mid, content, confidence, reason, _now()))

    def versions(self, mid: str) -> list[dict]:
        with self._conn() as c:
            return [dict(r) for r in c.execute(
                "SELECT * FROM memory_version WHERE memory_id=? ORDER BY created_at",
                (mid,)).fetchall()]

    def list_items(self, *, namespaces: list[str] | None = None,
                   memory_type: str | None = None, project_id: str | None = None,
                   status: str = "active", limit: int = 100,
                   include_deleted: bool = False) -> list[dict]:
        where, args = [], []
        if not include_deleted:
            where.append("status != 'deleted'")
        if status and status != "any":
            where.append("status=?"); args.append(status)
        if namespaces:
            where.append("namespace IN (%s)" % ",".join("?" * len(namespaces)))
            args += namespaces
        if memory_type:
            where.append("memory_type=?"); args.append(memory_type)
        if project_id is not None:
            where.append("project_id=?"); args.append(project_id)
        sql = "SELECT * FROM memory_item"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY updated_at DESC LIMIT ?"
        args.append(limit)
        with self._conn() as c:
            return [self._row(r) for r in c.execute(sql, args).fetchall()]

    def candidates(self, namespaces: list[str]) -> list[dict]:
        """Active, non-expired, retrievable items in the given namespaces."""
        if not namespaces:
            return []
        now = _now()
        q = ("SELECT * FROM memory_item WHERE status IN "
             "('active','reinforced','stale') AND (expiry IS NULL OR expiry > ?) "
             "AND namespace IN (%s)" % ",".join("?" * len(namespaces)))
        with self._conn() as c:
            return [self._row(r) for r in c.execute(q, [now, *namespaces]).fetchall()]

    # ── embeddings ────────────────────────────────────────────────────────
    def set_embedding(self, mid: str, vector: bytes, dim: int, version: str,
                      norm: float) -> None:
        with self._conn() as c:
            c.execute("INSERT OR REPLACE INTO memory_embedding VALUES(?,?,?,?,?,?)",
                      (mid, dim, version, vector, norm, _now()))
            c.execute("UPDATE memory_item SET embedding_version=? WHERE id=?",
                      (version, mid))

    def get_embedding(self, mid: str) -> Optional[dict]:
        with self._conn() as c:
            row = c.execute("SELECT * FROM memory_embedding WHERE memory_id=?",
                            (mid,)).fetchone()
        return dict(row) if row else None

    def embeddings_for(self, ids: list[str]) -> dict[str, dict]:
        """Bulk-load embeddings for many items in one query (retrieval hot path)."""
        if not ids:
            return {}
        out: dict[str, dict] = {}
        with self._conn() as c:
            # chunk to stay under SQLite's variable limit
            for i in range(0, len(ids), 900):
                batch = ids[i:i + 900]
                q = ("SELECT * FROM memory_embedding WHERE memory_id IN (%s)"
                     % ",".join("?" * len(batch)))
                for r in c.execute(q, batch).fetchall():
                    out[r["memory_id"]] = dict(r)
        return out

    def feedback_ids(self) -> dict[str, float]:
        """Map of memory_id → usefulness ratio, one query (retrieval hot path)."""
        with self._conn() as c:
            rows = c.execute("SELECT memory_id, AVG(useful) u FROM memory_feedback "
                             "GROUP BY memory_id").fetchall()
        return {r["memory_id"]: float(r["u"]) for r in rows}

    def drop_embedding(self, mid: str) -> None:
        with self._conn() as c:
            c.execute("DELETE FROM memory_embedding WHERE memory_id=?", (mid,))
            c.execute("UPDATE memory_item SET embedding_version='' WHERE id=?", (mid,))

    def items_missing_embedding(self, version: str, limit: int = 500) -> list[dict]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT mi.* FROM memory_item mi LEFT JOIN memory_embedding me "
                "ON me.memory_id=mi.id WHERE mi.status != 'deleted' AND "
                "(me.memory_id IS NULL OR me.version != ?) LIMIT ?",
                (version, limit)).fetchall()
        return [self._row(r) for r in rows]

    # ── sources / provenance ──────────────────────────────────────────────
    def add_source(self, mid: str, *, source_type: str, source_id: str,
                   citation: str = "") -> None:
        with self._conn() as c:
            c.execute("INSERT INTO memory_source VALUES(?,?,?,?,?,?)",
                      (_id(), mid, source_type, source_id, citation, _now()))

    def sources(self, mid: str) -> list[dict]:
        with self._conn() as c:
            return [dict(r) for r in c.execute(
                "SELECT * FROM memory_source WHERE memory_id=?", (mid,)).fetchall()]

    # ── relations (graph) ─────────────────────────────────────────────────
    def add_relation(self, src: str, dst: str, relation: str, weight: float = 1.0):
        with self._conn() as c:
            c.execute("INSERT INTO memory_relation VALUES(?,?,?,?,?,?)",
                      (_id(), src, dst, relation, weight, _now()))

    def relations(self, mid: str) -> list[dict]:
        with self._conn() as c:
            return [dict(r) for r in c.execute(
                "SELECT * FROM memory_relation WHERE src_id=? OR dst_id=?",
                (mid, mid)).fetchall()]

    def neighbors(self, mid: str, relation: str | None = None) -> list[str]:
        out = []
        for r in self.relations(mid):
            if relation and r["relation"] != relation:
                continue
            out.append(r["dst_id"] if r["src_id"] == mid else r["src_id"])
        return out

    # ── feedback / access log ─────────────────────────────────────────────
    def add_feedback(self, mid: str, useful: bool, note: str = "") -> None:
        with self._conn() as c:
            c.execute("INSERT INTO memory_feedback VALUES(?,?,?,?,?)",
                      (_id(), mid, 1 if useful else 0, note, _now()))

    def usefulness(self, mid: str) -> float:
        with self._conn() as c:
            rows = c.execute("SELECT useful FROM memory_feedback WHERE memory_id=?",
                             (mid,)).fetchall()
        if not rows:
            return 0.5
        return sum(r["useful"] for r in rows) / len(rows)

    def log_access(self, mid: str, actor: str, decision: str, reason: str = ""):
        with self._conn() as c:
            c.execute("INSERT INTO memory_access VALUES(?,?,?,?,?,?)",
                      (_id(), mid, actor, decision, reason, _now()))

    # ── conflicts ─────────────────────────────────────────────────────────
    def add_conflict(self, mid: str, conflicts_with: str, kind: str) -> str:
        cid = _id()
        with self._conn() as c:
            c.execute("INSERT INTO memory_conflict VALUES(?,?,?,?,?,?)",
                      (cid, mid, conflicts_with, kind, "open", _now()))
        return cid

    def conflicts(self, status: str = "open") -> list[dict]:
        with self._conn() as c:
            return [dict(r) for r in c.execute(
                "SELECT * FROM memory_conflict WHERE status=?", (status,)).fetchall()]

    def resolve_conflict(self, cid: str, status: str = "resolved") -> None:
        with self._conn() as c:
            c.execute("UPDATE memory_conflict SET status=? WHERE id=?", (status, cid))

    # ── tombstones (forgetting) ───────────────────────────────────────────
    def tombstone(self, mid: str, reason: str, restorable: bool = True) -> None:
        item = self.get_item(mid)
        if not item:
            return
        with self._conn() as c:
            c.execute("INSERT INTO memory_tombstone VALUES(?,?,?,?,?,?)",
                      (_id(), mid, item["namespace"], reason,
                       1 if restorable else 0, _now()))
            c.execute("UPDATE memory_item SET status='deleted' WHERE id=?", (mid,))
        self.drop_embedding(mid)   # cannot appear in vector search anymore

    def restore(self, mid: str) -> bool:
        with self._conn() as c:
            tomb = c.execute("SELECT * FROM memory_tombstone WHERE memory_id=? "
                             "ORDER BY created_at DESC LIMIT 1", (mid,)).fetchone()
            if not tomb or not tomb["restorable"]:
                return False
            c.execute("UPDATE memory_item SET status='active' WHERE id=?", (mid,))
        return True

    # ── summaries ─────────────────────────────────────────────────────────
    def add_summary(self, namespace: str, content: str) -> None:
        with self._conn() as c:
            c.execute("INSERT INTO memory_summary VALUES(?,?,?,?)",
                      (_id(), namespace, content, _now()))

    # ── retrieval runs (observability) ────────────────────────────────────
    def record_run(self, *, query: str, namespaces: list[str], mode: str,
                   results: list[dict], latency_ms: float) -> str:
        rid = _id()
        avg = (sum(r["final_score"] for r in results) / len(results)) if results else 0.0
        with self._conn() as c:
            c.execute("INSERT INTO retrieval_run VALUES(?,?,?,?,?,?,?,?)",
                      (rid, query[:200], json.dumps(namespaces), mode,
                       len(results), latency_ms, avg, _now()))
            for r in results:
                c.execute("INSERT INTO retrieval_result VALUES(?,?,?,?,?,?,?)",
                          (_id(), rid, r["memory_id"], r["final_score"],
                           r.get("semantic_score", 0), r.get("keyword_score", 0),
                           r.get("reason", "")))
        return rid

    def recent_runs(self, limit: int = 20) -> list[dict]:
        with self._conn() as c:
            return [dict(r) for r in c.execute(
                "SELECT * FROM retrieval_run ORDER BY created_at DESC LIMIT ?",
                (limit,)).fetchall()]

    # ── stats / health ────────────────────────────────────────────────────
    def stats(self) -> dict:
        with self._conn() as c:
            total = c.execute("SELECT COUNT(*) n FROM memory_item WHERE status!='deleted'").fetchone()["n"]
            by_type = {r["memory_type"]: r["n"] for r in c.execute(
                "SELECT memory_type, COUNT(*) n FROM memory_item WHERE status!='deleted' "
                "GROUP BY memory_type").fetchall()}
            embeds = c.execute("SELECT COUNT(*) n FROM memory_embedding").fetchone()["n"]
            stale = c.execute("SELECT COUNT(*) n FROM memory_item WHERE status='stale'").fetchone()["n"]
            deleted = c.execute("SELECT COUNT(*) n FROM memory_item WHERE status='deleted'").fetchone()["n"]
            conflicts = c.execute("SELECT COUNT(*) n FROM memory_conflict WHERE status='open'").fetchone()["n"]
        return {"total": total, "by_type": by_type, "embeddings": embeds,
                "stale": stale, "deleted": deleted, "open_conflicts": conflicts}
