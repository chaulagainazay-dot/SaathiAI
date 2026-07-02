from __future__ import annotations
"""SQLite memory: conversation history + long-term facts with keyword recall."""
import re
import sqlite3
import time
from pathlib import Path


class Memory:
    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(db_path, check_same_thread=False)
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS turns(
                id INTEGER PRIMARY KEY, session_id TEXT, role TEXT,
                content TEXT, ts REAL);
            CREATE TABLE IF NOT EXISTS facts(
                id INTEGER PRIMARY KEY, fact TEXT UNIQUE, category TEXT,
                ts REAL);
            CREATE TABLE IF NOT EXISTS english_mistakes(
                id INTEGER PRIMARY KEY, mistake TEXT, correction TEXT,
                count INTEGER DEFAULT 1, ts REAL);
            CREATE TABLE IF NOT EXISTS tasks(
                id INTEGER PRIMARY KEY, title TEXT, status TEXT DEFAULT 'open',
                due TEXT, created_ts REAL, done_ts REAL);
        """)

    # --- conversation ---
    def save_turn(self, session_id: str, role: str, content: str):
        self.db.execute("INSERT INTO turns(session_id, role, content, ts) VALUES(?,?,?,?)",
                        (session_id, role, content, time.time()))
        self.db.commit()

    def recent_turns(self, session_id: str, limit: int = 20) -> list[dict]:
        rows = self.db.execute(
            "SELECT role, content FROM turns WHERE session_id=? ORDER BY id DESC LIMIT ?",
            (session_id, limit)).fetchall()
        return [{"role": r, "content": c} for r, c in reversed(rows)]

    # --- long-term facts ---
    def save_fact(self, fact: str, category: str = "general"):
        self.db.execute("INSERT OR IGNORE INTO facts(fact, category, ts) VALUES(?,?,?)",
                        (fact, category, time.time()))
        self.db.commit()

    def relevant_facts(self, query: str, limit: int = 8) -> list[str]:
        words = {w for w in re.findall(r"\w+", query.lower()) if len(w) > 3}
        rows = self.db.execute("SELECT fact FROM facts ORDER BY ts DESC LIMIT 200").fetchall()
        scored = []
        for (fact,) in rows:
            score = sum(1 for w in words if w in fact.lower())
            scored.append((score, fact))
        scored.sort(key=lambda x: -x[0])
        # always include a few recent facts even with zero keyword overlap
        return [f for _, f in scored[:limit]]

    # --- english coaching ---
    def log_mistake(self, mistake: str, correction: str):
        row = self.db.execute("SELECT id, count FROM english_mistakes WHERE mistake=?",
                              (mistake,)).fetchone()
        if row:
            self.db.execute("UPDATE english_mistakes SET count=count+1, ts=? WHERE id=?",
                            (time.time(), row[0]))
        else:
            self.db.execute(
                "INSERT INTO english_mistakes(mistake, correction, ts) VALUES(?,?,?)",
                (mistake, correction, time.time()))
        self.db.commit()

    def top_mistakes(self, limit: int = 10) -> list[dict]:
        rows = self.db.execute(
            "SELECT mistake, correction, count FROM english_mistakes "
            "ORDER BY count DESC LIMIT ?", (limit,)).fetchall()
        return [{"mistake": m, "correction": c, "count": n} for m, c, n in rows]

    # --- tasks ---
    def add_task(self, title: str, due: str | None = None) -> int:
        cur = self.db.execute("INSERT INTO tasks(title, due, created_ts) VALUES(?,?,?)",
                              (title, due, time.time()))
        self.db.commit()
        return cur.lastrowid

    def complete_task(self, task_id: int):
        self.db.execute("UPDATE tasks SET status='done', done_ts=? WHERE id=?",
                        (time.time(), task_id))
        self.db.commit()

    def open_tasks(self) -> list[dict]:
        rows = self.db.execute(
            "SELECT id, title, due FROM tasks WHERE status='open' ORDER BY id").fetchall()
        return [{"id": i, "title": t, "due": d} for i, t, d in rows]
