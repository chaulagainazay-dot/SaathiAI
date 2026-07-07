"""Credit Manager — knows what each generation provider can do TODAY.

Every provider has daily credits that reset. Saathi tracks remaining credits so the
Provider Scheduler can decide which engine generates each scene without any manual
work. Local FFmpeg is the always-available, unlimited, medium-quality safety net.

This tracks credits + availability; the actual generation calls live behind provider
adapters (deferred until API keys exist). Honest: a provider is only 'available' if
it's active AND has credits (or is unlimited) — never assumes access it can't prove.
"""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path

# seed providers: name, kind, daily, unit, cost/unit (USD), quality_tier(1 best), reset_hour, api_env
_SEED_PROVIDERS = [
    ("google_flow", "video", 10, "clip", 0.0, 1, 0, "GOOGLE_FLOW_API_KEY"),
    ("heygen", "avatar", 3, "clip", 0.0, 1, 0, "HEYGEN_API_KEY"),
    ("kling", "video", 6, "clip", 0.0, 2, 0, "KLING_API_KEY"),
    ("seedance", "video", 20, "clip", 0.02, 2, 0, "SEEDANCE_API_KEY"),
    ("runway", "video", 5, "clip", 0.50, 1, 0, "RUNWAY_API_KEY"),
    ("ffmpeg", "local", -1, "clip", 0.0, 3, 0, ""),   # -1 = unlimited
]
_COLS = ["name", "kind", "daily", "remaining", "unit", "cost", "quality_tier",
         "reset_hour", "api_env", "status", "reset_day"]


class CreditManager:
    def __init__(self, db_path: str | None = None):
        self.db_path = Path(db_path) if db_path else (Path.home() / ".saathi" / "provider_credits.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.execute("CREATE TABLE IF NOT EXISTS provider(name TEXT PRIMARY KEY, kind TEXT, daily INTEGER, "
                      "remaining INTEGER, unit TEXT, cost REAL, quality_tier INTEGER, reset_hour INTEGER, "
                      "api_env TEXT, status TEXT, reset_day TEXT)")
        self._seed()

    def _conn(self):
        return sqlite3.connect(str(self.db_path))

    def _seed(self):
        import os
        with self._conn() as c:
            have = {r[0] for r in c.execute("SELECT name FROM provider").fetchall()}
            for name, kind, daily, unit, cost, qt, rh, env in _SEED_PROVIDERS:
                if name in have:
                    continue
                # a keyed provider starts 'inactive' until its API key is set (honest)
                status = "active" if (not env or os.getenv(env)) else "no_key"
                if name == "ffmpeg":
                    status = "active"
                c.execute("INSERT INTO provider VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                          (name, kind, daily, daily if daily >= 0 else -1, unit, cost, qt, rh, env,
                           status, _today()))

    def refresh(self):
        """Midnight-style reset: restore each provider's daily credits, re-check API keys."""
        import os
        today = _today()
        with self._conn() as c:
            for r in c.execute("SELECT name, daily, api_env, status FROM provider").fetchall():
                name, daily, env, status = r
                new_status = status
                if env:
                    new_status = "active" if os.getenv(env) else "no_key"
                elif name == "ffmpeg":
                    new_status = "active"
                c.execute("UPDATE provider SET remaining=?, reset_day=?, status=? WHERE name=?",
                          (daily if daily >= 0 else -1, today, new_status, name))

    def status(self) -> list[dict]:
        self._auto_reset()
        with self._conn() as c:
            rows = c.execute("SELECT " + ",".join(_COLS) + " FROM provider ORDER BY quality_tier, cost").fetchall()
        return [_row(r) for r in rows]

    def get(self, name: str) -> dict | None:
        self._auto_reset()
        with self._conn() as c:
            r = c.execute("SELECT " + ",".join(_COLS) + " FROM provider WHERE name=?", (name,)).fetchone()
        return _row(r) if r else None

    def available(self, *, need: int = 1, kind: str = "") -> list[dict]:
        """Providers that can generate right now, cheapest-then-best-quality first."""
        out = []
        for p in self.status():
            if p["status"] != "active":
                continue
            if kind and p["kind"] != kind and p["kind"] != "local":
                continue
            if p["remaining"] == -1 or p["remaining"] >= 1:
                out.append(p)
        out.sort(key=lambda p: (p["cost"], p["quality_tier"], -(p["remaining"] if p["remaining"] >= 0 else 10**9)))
        return out

    def reserve(self, name: str, n: int = 1) -> bool:
        """Consume n credits (unlimited providers always succeed)."""
        p = self.get(name)
        if not p or p["status"] != "active":
            return False
        if p["remaining"] == -1:
            return True
        if p["remaining"] < n:
            return False
        with self._conn() as c:
            c.execute("UPDATE provider SET remaining=remaining-? WHERE name=?", (n, name))
        return True

    def _auto_reset(self):
        with self._conn() as c:
            days = {r[0] for r in c.execute("SELECT DISTINCT reset_day FROM provider").fetchall()}
        if days and _today() not in days:
            self.refresh()


def _today() -> str:
    return time.strftime("%Y-%m-%d")


def _row(r) -> dict:
    d = dict(zip(_COLS, r))
    d["unlimited"] = d["remaining"] == -1
    return d


_default = None
def default_manager() -> CreditManager:
    global _default
    if _default is None:
        _default = CreditManager()
    return _default
