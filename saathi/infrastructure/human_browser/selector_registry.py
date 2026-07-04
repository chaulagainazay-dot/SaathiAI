"""Selector Registry — how SaathiAI remembers the structure of websites over time.

Not just selectors: *selector knowledge*. Per element key (e.g. "youtube/publish")
it stores every known selector with a confidence that rises on success, falls on
failure, and starts high when a human teaches it. Workflows resolve keys through
here (self-healing: best-known first), and Teach Mode writes new selectors here
without a code change. This is the data behind the Automation Knowledge Graph —
"Publish button: known since 2026, changed 3×, confidence 98%, 4 alternatives."

SQLite-backed; path injectable for tests.
"""
from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class KnownSelector:
    key: str
    selector: str
    strategy: str          # id | aria | css | xpath | text | taught | vision
    confidence: float      # 0..1
    source: str            # page_object | taught | vision
    successes: int
    failures: int
    last_verified: float
    created: float


class SelectorRegistry:
    def __init__(self, db_path: str | None = None):
        self.db_path = Path(db_path) if db_path else (Path.home() / ".saathi" / "selectors.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _conn(self):
        c = sqlite3.connect(str(self.db_path)); c.row_factory = sqlite3.Row
        return c

    def _init(self):
        with self._conn() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS selectors(
                key TEXT, selector TEXT, strategy TEXT, confidence REAL, source TEXT,
                successes INTEGER DEFAULT 0, failures INTEGER DEFAULT 0,
                last_verified REAL, created REAL, PRIMARY KEY(key, selector))""")

    # ── writes ──────────────────────────────────────────────────────────
    def seed(self, key: str, selectors: list[str], *, strategy: str = "css",
             source: str = "page_object", confidence: float = 0.6) -> None:
        """Register a workflow's default selectors (idempotent, won't lower an
        existing learned confidence)."""
        now = time.time()
        with self._conn() as c:
            for sel in selectors:
                c.execute("""INSERT OR IGNORE INTO selectors
                    (key,selector,strategy,confidence,source,last_verified,created)
                    VALUES(?,?,?,?,?,?,?)""",
                    (key, sel, strategy, confidence, source, now, now))

    def learn(self, key: str, selector: str, *, strategy: str = "taught",
              source: str = "taught", confidence: float = 0.9) -> KnownSelector:
        """Teach Mode: a human confirmed this selector. High initial confidence."""
        now = time.time()
        with self._conn() as c:
            c.execute("""INSERT INTO selectors
                (key,selector,strategy,confidence,source,successes,last_verified,created)
                VALUES(?,?,?,?,?,1,?,?)
                ON CONFLICT(key,selector) DO UPDATE SET
                  confidence=MAX(confidence, excluded.confidence),
                  strategy=excluded.strategy, source=excluded.source,
                  successes=successes+1, last_verified=excluded.last_verified""",
                (key, selector, strategy, confidence, source, now, now))
        return self.known(key)[0]

    def record_success(self, key: str, selector: str) -> None:
        with self._conn() as c:
            c.execute("""UPDATE selectors SET
                confidence=MIN(1.0, confidence+0.05), successes=successes+1, last_verified=?
                WHERE key=? AND selector=?""", (time.time(), key, selector))

    def record_failure(self, key: str, selector: str) -> None:
        with self._conn() as c:
            c.execute("""UPDATE selectors SET
                confidence=MAX(0.0, confidence-0.15), failures=failures+1
                WHERE key=? AND selector=?""", (key, selector))

    def reward(self, key: str) -> None:
        """A keyed step succeeded — repeated use is stronger evidence than one
        capture, so raise the leading selector's confidence toward 1.0."""
        top = self.known(key)
        if top:
            self.record_success(key, top[0].selector)

    def penalize(self, key: str) -> None:
        """A keyed step failed to resolve — decay the leading selector (and this
        is where Teach Mode is triggered)."""
        top = self.known(key)
        if top:
            self.record_failure(key, top[0].selector)

    # ── reads ───────────────────────────────────────────────────────────
    def known(self, key: str) -> list[KnownSelector]:
        with self._conn() as c:
            rows = c.execute("""SELECT * FROM selectors WHERE key=?
                                ORDER BY confidence DESC, successes DESC""", (key,)).fetchall()
        return [KnownSelector(**dict(r)) for r in rows]

    def best(self, key: str, *, top: int = 3) -> str | None:
        """Highest-confidence selectors as a comma-CSS 'match any' string — the
        self-healing resolution the workflow actually uses."""
        sels = [k.selector for k in self.known(key) if k.confidence > 0.05][:top]
        return ", ".join(sels) if sels else None

    def stats(self, key: str) -> dict:
        ks = self.known(key)
        return {"key": key, "known": len(ks),
                "confidence": round(ks[0].confidence, 2) if ks else 0.0,
                "changed": len(ks), "sources": sorted({k.source for k in ks}),
                "last_verified": max((k.last_verified for k in ks), default=None)}

    def keys(self) -> list[str]:
        with self._conn() as c:
            return [r[0] for r in c.execute("SELECT DISTINCT key FROM selectors ORDER BY key").fetchall()]

    def overview(self) -> list[dict]:
        return [self.stats(k) for k in self.keys()]


_default = None
def default_registry() -> SelectorRegistry:
    global _default
    if _default is None:
        _default = SelectorRegistry()
    return _default
