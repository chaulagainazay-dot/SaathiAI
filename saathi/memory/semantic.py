"""Semantic memory — long-term pattern store.

Uses ChromaDB when available (Phase 6); falls back to a SQLite-backed
keyword store so the rest of the system works without it.
"""
from __future__ import annotations
import json
import os
import sqlite3
from typing import Any

_DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "baadar_semantic.db")


def _conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
    c = sqlite3.connect(_DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c


def _init_db(c: sqlite3.Connection) -> None:
    c.execute("""
        CREATE TABLE IF NOT EXISTS patterns (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT NOT NULL,
            skill      TEXT NOT NULL,
            error_type TEXT NOT NULL,
            count      INTEGER DEFAULT 1,
            examples   TEXT DEFAULT '[]'
        )
    """)
    c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_pattern ON patterns(student_id,skill,error_type)")
    c.commit()


class SemanticMemory:
    def __init__(self):
        self._c = _conn()
        _init_db(self._c)
        self._chroma = None
        self._try_init_chroma()

    def _try_init_chroma(self) -> None:
        try:
            import chromadb  # type: ignore
            self._chroma = chromadb.PersistentClient(
                path=os.path.join(os.path.dirname(_DB_PATH), "chroma")
            )
        except ImportError:
            pass  # Phase 6: install chromadb when ready

    async def update(self, student_id: str, interaction: dict[str, Any]) -> None:
        """Record error patterns from an interaction."""
        corrections = interaction.get("corrections", [])
        skill = interaction.get("skill", "general")
        for corr in corrections:
            error_type = corr.get("type", "unknown")
            example = corr.get("error", "")
            self._upsert_pattern(student_id, skill, error_type, example)

    def _upsert_pattern(self, student_id: str, skill: str, error_type: str, example: str) -> None:
        row = self._c.execute(
            "SELECT id, count, examples FROM patterns WHERE student_id=? AND skill=? AND error_type=?",
            (student_id, skill, error_type),
        ).fetchone()
        if row:
            examples = json.loads(row["examples"])
            if example and example not in examples:
                examples.append(example)
            self._c.execute(
                "UPDATE patterns SET count=count+1, examples=? WHERE id=?",
                (json.dumps(examples[-10:]), row["id"]),
            )
        else:
            self._c.execute(
                "INSERT INTO patterns (student_id,skill,error_type,count,examples) VALUES (?,?,?,1,?)",
                (student_id, skill, error_type, json.dumps([example] if example else [])),
            )
        self._c.commit()

    def get_top_weaknesses(self, student_id: str, n: int = 5) -> list[dict]:
        rows = self._c.execute(
            "SELECT skill, error_type, count FROM patterns WHERE student_id=? ORDER BY count DESC LIMIT ?",
            (student_id, n),
        ).fetchall()
        return [dict(r) for r in rows]
