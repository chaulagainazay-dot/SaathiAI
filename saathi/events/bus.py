"""The Saathi Event Bus — the single spine every product writes to.

Products (AI Studio, PIELTS, HCG, Cafeteria, Travel CRM, Telegram, POS, future
apps) emit ONE thing: an Event. They know nothing about Evidence, Learning, or
Registries. The bus persists the event and routes it — through Event Adapters —
into the Evidence Store, exactly like the Model Router decouples departments from
providers. Add a business = emit its events + register one adapter; the pipeline
downstream (Evidence → Learning → Recommendation → CEO → Prompt Registry) never
changes.

    emit(type, source, payload) → persist → route to evidence → notify subscribers

Event types are dotted verbs: lesson.completed, essay.scored, trade.closed,
meal.sold, video.published, booking.confirmed, invoice.paid, telegram.message.
"""
from __future__ import annotations

import fnmatch
import json
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

_COLUMNS = ["id", "timestamp", "type", "source", "project", "subject", "payload", "evidence_ids"]


@dataclass
class Event:
    type: str                          # dotted verb, e.g. "essay.scored"
    source: str                        # emitting product/app, e.g. "pielts"
    payload: dict = field(default_factory=dict)
    project: str = ""
    subject: str = ""                  # entity id (essay id, trade id, episode…)
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    timestamp: float = field(default_factory=time.time)

    def to_row(self, evidence_ids: list) -> tuple:
        return (self.id, self.timestamp, self.type, self.source, self.project,
                self.subject, json.dumps(self.payload), json.dumps(evidence_ids))


def _row_to_dict(row) -> dict:
    d = dict(zip(_COLUMNS, row))
    for c in ("payload", "evidence_ids"):
        try:
            d[c] = json.loads(d[c]) if d[c] else ({} if c == "payload" else [])
        except Exception:
            d[c] = {} if c == "payload" else []
    return d


class EventBus:
    def __init__(self, db_path: str | None = None):
        self.db_path = Path(db_path) if db_path else (Path.home() / ".saathi" / "events.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._subscribers: list[tuple[str, callable]] = []
        self._init()

    def _conn(self):
        return sqlite3.connect(str(self.db_path))

    def _init(self):
        cols = ", ".join(f"{c} {'REAL' if c == 'timestamp' else 'TEXT'}" for c in _COLUMNS)
        with self._conn() as c:
            c.execute(f"CREATE TABLE IF NOT EXISTS event({cols}, PRIMARY KEY(id))")
            c.execute("CREATE INDEX IF NOT EXISTS idx_evt ON event(type, timestamp)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_evt_src ON event(source, timestamp)")

    # ── the one method every product calls ────────────────────────────────────
    def emit(self, type: str, source: str, payload: dict | None = None, *,
             project: str = "", subject: str = "") -> dict:
        ev = Event(type=type, source=source, payload=payload or {}, project=project, subject=subject)
        evidence_ids = self._route_to_evidence(ev)
        with self._conn() as c:
            c.execute(f"INSERT OR REPLACE INTO event({','.join(_COLUMNS)}) VALUES({','.join('?'*len(_COLUMNS))})",
                      ev.to_row(evidence_ids))
        for pattern, handler in self._subscribers:
            if fnmatch.fnmatch(ev.type, pattern):
                try:
                    handler(ev)
                except Exception:
                    pass
        return {"id": ev.id, "type": ev.type, "evidence_ids": evidence_ids}

    def _route_to_evidence(self, ev: Event) -> list:
        try:
            from saathi.events.routes import to_evidence
            return to_evidence(ev)
        except Exception:
            return []

    # ── in-process subscriptions (glob pattern on type) ───────────────────────
    def subscribe(self, pattern: str, handler) -> None:
        self._subscribers.append((pattern, handler))

    # ── reads ─────────────────────────────────────────────────────────────────
    def query(self, *, type: str | None = None, source: str | None = None,
              since: float | None = None, limit: int = 50) -> list[dict]:
        where, args = [], []
        if type:
            where.append("type LIKE ?"); args.append(type.replace("*", "%"))
        if source:
            where.append("source=?"); args.append(source)
        if since:
            where.append("timestamp>=?"); args.append(since)
        sql = "SELECT " + ",".join(_COLUMNS) + " FROM event"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY timestamp DESC LIMIT ?"; args.append(limit)
        with self._conn() as c:
            return [_row_to_dict(r) for r in c.execute(sql, args).fetchall()]

    def count(self) -> int:
        with self._conn() as c:
            return c.execute("SELECT COUNT(*) FROM event").fetchone()[0]

    def stats(self, *, since: float | None = None) -> dict:
        since = since if since is not None else 0
        with self._conn() as c:
            by_type = c.execute("SELECT type, COUNT(*) FROM event WHERE timestamp>=? GROUP BY type "
                                "ORDER BY 2 DESC", (since,)).fetchall()
            by_src = c.execute("SELECT source, COUNT(*) FROM event WHERE timestamp>=? GROUP BY source",
                               (since,)).fetchall()
        return {"by_type": {t: n for t, n in by_type}, "by_source": {s: n for s, n in by_src},
                "total": sum(n for _, n in by_type)}


_default = None
def default_bus() -> EventBus:
    global _default
    if _default is None:
        _default = EventBus()
    return _default
