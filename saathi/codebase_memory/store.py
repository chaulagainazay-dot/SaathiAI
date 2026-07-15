"""SQLite persistence for governed codebase memory index."""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Optional

from saathi.codebase_memory.identity import INDEX_SCHEMA_VERSION, RepoIdentity

DEFAULT_INDEX_DIR = Path.home() / ".saathi" / "codebase_memory"


_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS files (
  path TEXT PRIMARY KEY,
  file_hash TEXT NOT NULL,
  classification TEXT NOT NULL,
  language TEXT DEFAULT '',
  size_bytes INTEGER DEFAULT 0,
  deleted INTEGER DEFAULT 0,
  generated INTEGER DEFAULT 0,
  vendored INTEGER DEFAULT 0,
  sensitivity TEXT DEFAULT 'internal',
  branch TEXT DEFAULT '',
  commit_sha TEXT DEFAULT '',
  dirty INTEGER DEFAULT 0,
  indexed_at REAL DEFAULT 0,
  last_verified_at REAL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS chunks (
  chunk_id TEXT PRIMARY KEY,
  path TEXT NOT NULL,
  start_line INTEGER,
  end_line INTEGER,
  symbol TEXT DEFAULT '',
  symbol_type TEXT DEFAULT '',
  section TEXT DEFAULT '',
  text TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  classification TEXT DEFAULT '',
  language TEXT DEFAULT '',
  file_hash TEXT DEFAULT '',
  branch TEXT DEFAULT '',
  commit_sha TEXT DEFAULT '',
  dirty INTEGER DEFAULT 0,
  deleted INTEGER DEFAULT 0,
  chunk_version TEXT DEFAULT 'c1',
  parser_version TEXT DEFAULT '',
  schema_version TEXT DEFAULT '',
  indexed_at REAL DEFAULT 0,
  last_verified_at REAL DEFAULT 0,
  sensitivity TEXT DEFAULT 'internal',
  embedding BLOB,
  embedding_version TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_chunks_path ON chunks(path);
CREATE INDEX IF NOT EXISTS idx_chunks_symbol ON chunks(symbol);
CREATE INDEX IF NOT EXISTS idx_chunks_deleted ON chunks(deleted);
CREATE TABLE IF NOT EXISTS symbols (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  qualified_name TEXT DEFAULT '',
  symbol_type TEXT DEFAULT '',
  path TEXT NOT NULL,
  start_line INTEGER,
  end_line INTEGER,
  parent TEXT DEFAULT '',
  imports TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_sym_name ON symbols(name);
CREATE TABLE IF NOT EXISTS exclusions (
  path TEXT PRIMARY KEY,
  reason TEXT NOT NULL,
  at REAL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS fts_chunks (
  chunk_id TEXT PRIMARY KEY,
  path TEXT,
  symbol TEXT,
  body TEXT
);
"""


class IndexStore:
    def __init__(self, db_path: Path | str):
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def set_meta(self, key: str, value: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO meta(key,value) VALUES(?,?)", (key, value),
            )
            self._conn.commit()

    def get_meta(self, key: str, default: str = "") -> str:
        with self._lock:
            row = self._conn.execute(
                "SELECT value FROM meta WHERE key=?", (key,),
            ).fetchone()
            return row["value"] if row else default

    def meta_dict(self) -> dict[str, str]:
        with self._lock:
            rows = self._conn.execute("SELECT key, value FROM meta").fetchall()
            return {r["key"]: r["value"] for r in rows}

    def save_identity(self, ident: RepoIdentity) -> None:
        for k, v in ident.to_dict().items():
            self.set_meta(f"id.{k}", str(v))
        self.set_meta("index_schema_version", INDEX_SCHEMA_VERSION)
        self.set_meta("updated_at", str(time.time()))

    def load_identity_meta(self) -> dict[str, str]:
        m = self.meta_dict()
        return {k[3:]: v for k, v in m.items() if k.startswith("id.")}

    def upsert_file(self, row: dict) -> None:
        with self._lock:
            self._conn.execute(
                """INSERT OR REPLACE INTO files(
                    path,file_hash,classification,language,size_bytes,deleted,
                    generated,vendored,sensitivity,branch,commit_sha,dirty,
                    indexed_at,last_verified_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    row["path"], row["file_hash"], row["classification"],
                    row.get("language", ""), row.get("size_bytes", 0),
                    int(row.get("deleted", 0)), int(row.get("generated", 0)),
                    int(row.get("vendored", 0)), row.get("sensitivity", "internal"),
                    row.get("branch", ""), row.get("commit_sha", ""),
                    int(row.get("dirty", 0)), row.get("indexed_at", time.time()),
                    row.get("last_verified_at", time.time()),
                ),
            )
            self._conn.commit()

    def get_file(self, path: str) -> dict | None:
        with self._lock:
            r = self._conn.execute("SELECT * FROM files WHERE path=?", (path,)).fetchone()
            return dict(r) if r else None

    def list_file_paths(self, *, include_deleted: bool = False) -> list[str]:
        with self._lock:
            if include_deleted:
                rows = self._conn.execute("SELECT path FROM files").fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT path FROM files WHERE deleted=0"
                ).fetchall()
            return [r["path"] for r in rows]

    def mark_deleted(self, path: str) -> None:
        with self._lock:
            self._conn.execute("UPDATE files SET deleted=1 WHERE path=?", (path,))
            self._conn.execute("UPDATE chunks SET deleted=1 WHERE path=?", (path,))
            self._conn.execute("DELETE FROM symbols WHERE path=?", (path,))
            self._conn.execute("DELETE FROM fts_chunks WHERE path=?", (path,))
            self._conn.commit()

    def delete_chunks_for_path(self, path: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM chunks WHERE path=?", (path,))
            self._conn.execute("DELETE FROM fts_chunks WHERE path=?", (path,))
            self._conn.execute("DELETE FROM symbols WHERE path=?", (path,))
            self._conn.commit()

    def upsert_chunk(self, row: dict) -> None:
        with self._lock:
            self._conn.execute(
                """INSERT OR REPLACE INTO chunks(
                    chunk_id,path,start_line,end_line,symbol,symbol_type,section,
                    text,content_hash,classification,language,file_hash,branch,
                    commit_sha,dirty,deleted,chunk_version,parser_version,
                    schema_version,indexed_at,last_verified_at,sensitivity,
                    embedding,embedding_version
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    row["chunk_id"], row["path"], row.get("start_line"), row.get("end_line"),
                    row.get("symbol", ""), row.get("symbol_type", ""), row.get("section", ""),
                    row["text"], row["content_hash"], row.get("classification", ""),
                    row.get("language", ""), row.get("file_hash", ""),
                    row.get("branch", ""), row.get("commit_sha", ""),
                    int(row.get("dirty", 0)), int(row.get("deleted", 0)),
                    row.get("chunk_version", "c1"), row.get("parser_version", ""),
                    row.get("schema_version", INDEX_SCHEMA_VERSION),
                    row.get("indexed_at", time.time()),
                    row.get("last_verified_at", time.time()),
                    row.get("sensitivity", "internal"),
                    row.get("embedding"), row.get("embedding_version", ""),
                ),
            )
            self._conn.execute(
                "INSERT OR REPLACE INTO fts_chunks(chunk_id,path,symbol,body) VALUES(?,?,?,?)",
                (
                    row["chunk_id"], row["path"], row.get("symbol", ""),
                    f"{row.get('symbol','')} {row.get('path','')} {row['text'][:2000]}",
                ),
            )
            self._conn.commit()

    def upsert_symbol(self, row: dict) -> None:
        sid = row.get("id") or f"{row['path']}:{row['name']}:{row.get('start_line',0)}"
        with self._lock:
            self._conn.execute(
                """INSERT OR REPLACE INTO symbols(
                    id,name,qualified_name,symbol_type,path,start_line,end_line,parent,imports
                ) VALUES(?,?,?,?,?,?,?,?,?)""",
                (
                    sid, row["name"], row.get("qualified_name", row["name"]),
                    row.get("symbol_type", ""), row["path"],
                    row.get("start_line"), row.get("end_line"),
                    row.get("parent", ""), row.get("imports", ""),
                ),
            )
            self._conn.commit()

    def record_exclusion(self, path: str, reason: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO exclusions(path,reason,at) VALUES(?,?,?)",
                (path, reason[:200], time.time()),
            )
            self._conn.commit()

    def exclusion_count(self) -> int:
        with self._lock:
            return int(self._conn.execute("SELECT COUNT(*) n FROM exclusions").fetchone()["n"])

    def counts(self) -> dict[str, int]:
        with self._lock:
            files = self._conn.execute(
                "SELECT COUNT(*) n FROM files WHERE deleted=0"
            ).fetchone()["n"]
            chunks = self._conn.execute(
                "SELECT COUNT(*) n FROM chunks WHERE deleted=0"
            ).fetchone()["n"]
            syms = self._conn.execute("SELECT COUNT(*) n FROM symbols").fetchone()["n"]
            excl = self._conn.execute("SELECT COUNT(*) n FROM exclusions").fetchone()["n"]
            return {
                "files": int(files), "chunks": int(chunks),
                "symbols": int(syms), "exclusions": int(excl),
            }

    def all_chunks(self, *, limit: int = 50000) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM chunks WHERE deleted=0 LIMIT ?", (limit,),
            ).fetchall()
            return [dict(r) for r in rows]

    def search_fts(self, query: str, *, limit: int = 50) -> list[dict]:
        """Simple LIKE-based lexical search (portable, no FTS5 dependency issues)."""
        tokens = [t for t in re_tokenize(query) if len(t) > 1][:12]
        if not tokens:
            return []
        with self._lock:
            clauses = []
            args: list[Any] = []
            for t in tokens:
                clauses.append("(body LIKE ? OR symbol LIKE ? OR path LIKE ?)")
                pat = f"%{t}%"
                args.extend([pat, pat, pat])
            sql = (
                "SELECT c.* FROM chunks c JOIN fts_chunks f ON c.chunk_id=f.chunk_id "
                f"WHERE c.deleted=0 AND ({' AND '.join(clauses)}) LIMIT ?"
            )
            args.append(limit)
            try:
                rows = self._conn.execute(sql, args).fetchall()
            except sqlite3.Error:
                return []
            return [dict(r) for r in rows]

    def find_symbol(self, name: str, *, limit: int = 40) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM symbols WHERE name LIKE ? OR qualified_name LIKE ? LIMIT ?",
                (f"%{name}%", f"%{name}%", limit),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_chunk(self, chunk_id: str) -> dict | None:
        with self._lock:
            r = self._conn.execute(
                "SELECT * FROM chunks WHERE chunk_id=?", (chunk_id,),
            ).fetchone()
            return dict(r) if r else None

    def integrity_ok(self) -> bool:
        with self._lock:
            try:
                r = self._conn.execute("PRAGMA integrity_check").fetchone()
                return r and r[0] == "ok"
            except sqlite3.Error:
                return False

    def clear_all(self) -> None:
        with self._lock:
            for t in ("chunks", "files", "symbols", "exclusions", "fts_chunks", "meta"):
                self._conn.execute(f"DELETE FROM {t}")
            self._conn.commit()


_STOP = frozenset({
    "where", "what", "which", "when", "who", "how", "the", "a", "an", "is", "are",
    "was", "were", "be", "been", "for", "of", "in", "on", "to", "and", "or",
    "this", "that", "with", "from", "by", "as", "it", "its", "into", "about",
    "does", "do", "did", "can", "could", "should", "would", "file", "files",
    "document", "documents", "code", "please", "tell", "me",
})


def re_tokenize(q: str) -> list[str]:
    import re
    toks = re.findall(r"[A-Za-z0-9_./-]{2,}", q.lower())
    return [t for t in toks if t not in _STOP][:16]


def index_db_path(ident: RepoIdentity, *, base: Path | None = None) -> Path:
    base = base or Path(
        __import__("os").environ.get(
            "SAATHI_CBM_INDEX_DIR", str(DEFAULT_INDEX_DIR),
        )
    )
    return base / f"{ident.index_key}.sqlite"
