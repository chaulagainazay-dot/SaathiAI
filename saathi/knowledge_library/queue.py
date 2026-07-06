"""Reading Queue — the knowledge backlog / AI-engineering curriculum.

A prioritised list of sources to import. Curating replaces coding: fill this,
then import top-down. Marked 'imported' once it lands in the Library.
"""
from __future__ import annotations

import sqlite3
import time
import uuid
from pathlib import Path

STATUSES = ("pending", "importing", "imported", "skipped")


class QueueStore:
    def __init__(self, db_path: str | None = None):
        self.db_path = Path(db_path) if db_path else (Path.home() / ".saathi" / "reading_queue.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.execute("CREATE TABLE IF NOT EXISTS queue(id TEXT PRIMARY KEY, title TEXT, url TEXT, "
                      "category TEXT, priority INTEGER, status TEXT, added REAL)")

    def _conn(self):
        return sqlite3.connect(str(self.db_path))

    def add(self, title: str, *, url: str = "", category: str = "", priority: int = 3,
            status: str = "pending") -> dict:
        with self._conn() as c:
            row = c.execute("SELECT id FROM queue WHERE title=?", (title,)).fetchone()
            qid = row[0] if row else uuid.uuid4().hex[:12]
            c.execute("INSERT OR REPLACE INTO queue VALUES(?,?,?,?,?,?,?)",
                      (qid, title, url, category, max(1, min(5, int(priority))),
                       status if status in STATUSES else "pending", time.time()))
        return {"id": qid, "title": title, "priority": priority, "status": status, "category": category}

    def list(self, *, status: str = "") -> list[dict]:
        sql = "SELECT id,title,url,category,priority,status FROM queue"
        args = []
        if status:
            sql += " WHERE status=?"; args.append(status)
        sql += " ORDER BY priority DESC, added"
        with self._conn() as c:
            return [dict(zip(["id", "title", "url", "category", "priority", "status"], r))
                    for r in c.execute(sql, args).fetchall()]

    def set_status(self, qid: str, status: str) -> bool:
        if status not in STATUSES:
            return False
        with self._conn() as c:
            return c.execute("UPDATE queue SET status=? WHERE id=?", (status, qid)).rowcount > 0


_SEED = [
    ("AI Agents: The Definitive Guide", "https://github.com/Nicolepcx/ai-agents-the-definitive-guide", "AI Engineering", 5, "imported"),
    ("OpenHands", "https://github.com/All-Hands-AI/OpenHands", "AI Engineering", 5, "pending"),
    ("Dify", "https://github.com/langgenius/dify", "AI Engineering", 5, "pending"),
    ("LibreChat", "https://github.com/danny-avila/LibreChat", "AI Engineering", 4, "pending"),
    ("Google ADK", "https://github.com/google/adk-python", "AI Engineering", 5, "pending"),
    ("OpenAI Agents SDK", "https://github.com/openai/openai-agents-python", "AI Engineering", 4, "pending"),
    ("LangGraph", "https://github.com/langchain-ai/langgraph", "AI Engineering", 4, "pending"),
    ("MCP Specification", "https://github.com/modelcontextprotocol/modelcontextprotocol", "AI Engineering", 4, "pending"),
    ("A2A Protocol", "https://github.com/google-a2a/A2A", "AI Engineering", 4, "pending"),
    ("Cambridge IELTS books", "", "IELTS", 5, "pending"),
    ("IELTS Official Band Descriptors", "", "IELTS", 5, "pending"),
    ("IELTS Examiner Reports", "", "IELTS", 4, "pending"),
    ("ICT / Smart Money Concepts", "", "Trading", 4, "pending"),
    ("Risk Management (Trading)", "", "Trading", 4, "pending"),
    ("HACCP Food Safety", "", "Cafeteria", 5, "pending"),
    ("Kitchen Operations & Inventory", "", "Cafeteria", 4, "pending"),
]


def seed_queue(store: "QueueStore | None" = None) -> int:
    store = store or default_store()
    existing = {q["title"] for q in store.list()}
    n = 0
    for title, url, cat, pri, st in _SEED:
        if title not in existing:
            store.add(title, url=url, category=cat, priority=pri, status=st); n += 1
    return n


_default = None
def default_store() -> QueueStore:
    global _default
    if _default is None:
        _default = QueueStore()
    return _default
