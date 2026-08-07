"""SQLite-backed incremental knowledge index (restart-safe, lexical)."""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Iterable

from .models import (
    INDEX_VERSION,
    MAX_TOTAL_CHUNKS,
    KnowledgeChunk,
    KnowledgeDocument,
)


class KnowledgeIndex:
    """Local lexical index. Semantic embeddings are intentionally not stored."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            cur = self._conn.cursor()
            cur.executescript(
                """
                CREATE TABLE IF NOT EXISTS meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS documents (
                    document_id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    authority TEXT NOT NULL,
                    relative_path TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    created_at REAL,
                    modified_at REAL,
                    indexed_at REAL,
                    milestone TEXT,
                    commit_sha TEXT,
                    tenant_id TEXT,
                    workspace_scope TEXT,
                    sensitivity TEXT,
                    chunk_count INTEGER,
                    byte_size INTEGER,
                    tombstoned INTEGER DEFAULT 0,
                    freshness TEXT,
                    metadata_json TEXT
                );
                CREATE TABLE IF NOT EXISTS chunks (
                    chunk_id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    ordinal INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    authority TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    relative_path TEXT NOT NULL,
                    title TEXT NOT NULL,
                    start_char INTEGER,
                    end_char INTEGER,
                    tenant_id TEXT,
                    workspace_scope TEXT,
                    sensitivity TEXT,
                    milestone TEXT,
                    commit_sha TEXT,
                    indexed_at REAL,
                    freshness TEXT,
                    tombstoned INTEGER DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(document_id);
                CREATE INDEX IF NOT EXISTS idx_chunks_source ON chunks(source_id);
                CREATE INDEX IF NOT EXISTS idx_chunks_tenant ON chunks(tenant_id);
                CREATE INDEX IF NOT EXISTS idx_docs_source ON documents(source_id);
                """
            )
            cur.execute(
                "INSERT OR IGNORE INTO meta(key, value) VALUES(?, ?)",
                ("index_version", INDEX_VERSION),
            )
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def set_meta(self, key: str, value: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO meta(key, value) VALUES(?, ?)",
                (key, str(value)),
            )
            self._conn.commit()

    def get_meta(self, key: str, default: str = "") -> str:
        with self._lock:
            row = self._conn.execute(
                "SELECT value FROM meta WHERE key = ?", (key,)
            ).fetchone()
            return row["value"] if row else default

    def get_document(self, document_id: str) -> KnowledgeDocument | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM documents WHERE document_id = ?", (document_id,)
            ).fetchone()
            return self._row_to_doc(row) if row else None

    def get_document_by_source(self, source_id: str) -> KnowledgeDocument | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM documents WHERE source_id = ? AND tombstoned = 0 "
                "ORDER BY indexed_at DESC LIMIT 1",
                (source_id,),
            ).fetchone()
            return self._row_to_doc(row) if row else None

    def upsert_document(self, doc: KnowledgeDocument, chunks: list[KnowledgeChunk]) -> None:
        with self._lock:
            # Replace chunks for document
            self._conn.execute("DELETE FROM chunks WHERE document_id = ?", (doc.document_id,))
            self._conn.execute(
                """
                INSERT OR REPLACE INTO documents(
                    document_id, source_id, title, source_type, authority,
                    relative_path, content_hash, created_at, modified_at, indexed_at,
                    milestone, commit_sha, tenant_id, workspace_scope, sensitivity,
                    chunk_count, byte_size, tombstoned, freshness, metadata_json
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    doc.document_id,
                    doc.source_id,
                    doc.title,
                    doc.source_type,
                    doc.authority,
                    doc.relative_path,
                    doc.content_hash,
                    doc.created_at,
                    doc.modified_at,
                    doc.indexed_at,
                    doc.milestone,
                    doc.commit_sha,
                    doc.tenant_id,
                    doc.workspace_scope,
                    doc.sensitivity,
                    doc.chunk_count,
                    doc.byte_size,
                    1 if doc.tombstoned else 0,
                    doc.freshness,
                    json.dumps(doc.metadata or {}),
                ),
            )
            for ch in chunks:
                self._conn.execute(
                    """
                    INSERT INTO chunks(
                        chunk_id, document_id, source_id, ordinal, text, content_hash,
                        authority, source_type, relative_path, title, start_char, end_char,
                        tenant_id, workspace_scope, sensitivity, milestone, commit_sha,
                        indexed_at, freshness, tombstoned
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        ch.chunk_id,
                        ch.document_id,
                        ch.source_id,
                        ch.ordinal,
                        ch.text,
                        ch.content_hash,
                        ch.authority,
                        ch.source_type,
                        ch.relative_path,
                        ch.title,
                        ch.start_char,
                        ch.end_char,
                        ch.tenant_id,
                        ch.workspace_scope,
                        ch.sensitivity,
                        ch.milestone,
                        ch.commit_sha,
                        ch.indexed_at,
                        ch.freshness,
                        1 if ch.tombstoned else 0,
                    ),
                )
            self._conn.commit()

    def tombstone_source(self, source_id: str) -> int:
        with self._lock:
            cur = self._conn.execute(
                "UPDATE documents SET tombstoned = 1 WHERE source_id = ?",
                (source_id,),
            )
            self._conn.execute(
                "UPDATE chunks SET tombstoned = 1 WHERE source_id = ?",
                (source_id,),
            )
            self._conn.commit()
            return cur.rowcount

    def count_chunks(self, *, include_tombstoned: bool = False) -> int:
        with self._lock:
            if include_tombstoned:
                row = self._conn.execute("SELECT COUNT(*) AS c FROM chunks").fetchone()
            else:
                row = self._conn.execute(
                    "SELECT COUNT(*) AS c FROM chunks WHERE tombstoned = 0"
                ).fetchone()
            return int(row["c"])

    def count_documents(self, *, include_tombstoned: bool = False) -> int:
        with self._lock:
            if include_tombstoned:
                row = self._conn.execute("SELECT COUNT(*) AS c FROM documents").fetchone()
            else:
                row = self._conn.execute(
                    "SELECT COUNT(*) AS c FROM documents WHERE tombstoned = 0"
                ).fetchone()
            return int(row["c"])

    def list_documents(self) -> list[KnowledgeDocument]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM documents WHERE tombstoned = 0 ORDER BY authority DESC, title"
            ).fetchall()
            return [self._row_to_doc(r) for r in rows]

    def all_live_chunks(self) -> list[KnowledgeChunk]:
        """Return live chunks for lexical scoring (bounded by MAX_TOTAL_CHUNKS)."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM chunks WHERE tombstoned = 0 "
                "ORDER BY authority DESC, document_id, ordinal "
                f"LIMIT {MAX_TOTAL_CHUNKS}"
            ).fetchall()
            return [self._row_to_chunk(r) for r in rows]

    def get_chunks_for_document(self, document_id: str) -> list[KnowledgeChunk]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM chunks WHERE document_id = ? AND tombstoned = 0 "
                "ORDER BY ordinal",
                (document_id,),
            ).fetchall()
            return [self._row_to_chunk(r) for r in rows]

    def get_chunk(self, chunk_id: str) -> KnowledgeChunk | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM chunks WHERE chunk_id = ?", (chunk_id,)
            ).fetchone()
            return self._row_to_chunk(row) if row else None

    def get_adjacent(self, chunk: KnowledgeChunk, radius: int = 1) -> list[KnowledgeChunk]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM chunks WHERE document_id = ? AND tombstoned = 0 "
                "AND ordinal BETWEEN ? AND ? ORDER BY ordinal",
                (
                    chunk.document_id,
                    max(0, chunk.ordinal - radius),
                    chunk.ordinal + radius,
                ),
            ).fetchall()
            return [self._row_to_chunk(r) for r in rows]

    def storage_bytes(self) -> int:
        try:
            return int(self.db_path.stat().st_size)
        except OSError:
            return 0

    def _row_to_doc(self, row: sqlite3.Row) -> KnowledgeDocument:
        meta = {}
        try:
            meta = json.loads(row["metadata_json"] or "{}")
        except json.JSONDecodeError:
            meta = {}
        return KnowledgeDocument(
            document_id=row["document_id"],
            source_id=row["source_id"],
            title=row["title"],
            source_type=row["source_type"],
            authority=row["authority"],
            relative_path=row["relative_path"],
            content_hash=row["content_hash"],
            created_at=row["created_at"] or 0.0,
            modified_at=row["modified_at"] or 0.0,
            indexed_at=row["indexed_at"] or 0.0,
            milestone=row["milestone"] or "",
            commit_sha=row["commit_sha"] or "",
            tenant_id=row["tenant_id"] or "platform",
            workspace_scope=row["workspace_scope"] or "*",
            sensitivity=row["sensitivity"] or "public_internal",
            chunk_count=row["chunk_count"] or 0,
            byte_size=row["byte_size"] or 0,
            tombstoned=bool(row["tombstoned"]),
            freshness=row["freshness"] or "unknown",
            metadata=meta,
        )

    def _row_to_chunk(self, row: sqlite3.Row) -> KnowledgeChunk:
        return KnowledgeChunk(
            chunk_id=row["chunk_id"],
            document_id=row["document_id"],
            source_id=row["source_id"],
            ordinal=row["ordinal"] or 0,
            text=row["text"] or "",
            content_hash=row["content_hash"] or "",
            authority=row["authority"] or "",
            source_type=row["source_type"] or "",
            relative_path=row["relative_path"] or "",
            title=row["title"] or "",
            start_char=row["start_char"] or 0,
            end_char=row["end_char"] or 0,
            tenant_id=row["tenant_id"] or "platform",
            workspace_scope=row["workspace_scope"] or "*",
            sensitivity=row["sensitivity"] or "public_internal",
            milestone=row["milestone"] or "",
            commit_sha=row["commit_sha"] or "",
            indexed_at=row["indexed_at"] or 0.0,
            freshness=row["freshness"] or "unknown",
            tombstoned=bool(row["tombstoned"]),
        )
