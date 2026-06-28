"""Episodic memory — SQLite-backed session log, one row per interaction."""
from __future__ import annotations
import asyncio
import json
import os
import sqlite3
from datetime import datetime, UTC
from typing import Any

_DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "baadar_episodic.db")


def _conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
    c = sqlite3.connect(_DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c


def _init_db(c: sqlite3.Connection) -> None:
    c.execute("""
        CREATE TABLE IF NOT EXISTS interactions (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT NOT NULL,
            skill      TEXT,
            input_text TEXT,
            response   TEXT,
            feedback   TEXT,
            band_est   REAL,
            metadata   TEXT,
            ts         TEXT NOT NULL
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_student ON interactions(student_id)")
    c.commit()


class EpisodicMemory:
    def __init__(self):
        self._c = _conn()
        _init_db(self._c)

    async def store(self, interaction: dict[str, Any]) -> None:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._store_sync, interaction)

    def _store_sync(self, interaction: dict[str, Any]) -> None:
        self._c.execute(
            "INSERT INTO interactions (student_id,skill,input_text,response,feedback,band_est,metadata,ts) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (
                interaction.get("student_id", ""),
                interaction.get("skill", ""),
                interaction.get("input_text", ""),
                interaction.get("response", ""),
                interaction.get("feedback", ""),
                interaction.get("band_est"),
                json.dumps(interaction.get("metadata", {})),
                datetime.now(UTC).isoformat(),
            ),
        )
        self._c.commit()

    async def get_history(self, student_id: str, limit: int = 50) -> list[dict]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._get_sync, student_id, limit)

    def _get_sync(self, student_id: str, limit: int) -> list[dict]:
        rows = self._c.execute(
            "SELECT * FROM interactions WHERE student_id=? ORDER BY ts DESC LIMIT ?",
            (student_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    async def get_weakness_summary(self, student_id: str) -> dict[str, int]:
        """Count interactions per skill to identify weak areas."""
        rows = self._c.execute(
            "SELECT skill, COUNT(*) as cnt FROM interactions WHERE student_id=? GROUP BY skill",
            (student_id,),
        ).fetchall()
        return {r["skill"]: r["cnt"] for r in rows}
