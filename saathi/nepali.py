from __future__ import annotations
"""Nepali learning — local, private, gets better every time Saathi is used.

Two mechanisms:
  1. Correction memory: when Saathi mishears a Nepali word/phrase, Ajay corrects
     it once; the wrong→right mapping is stored and auto-applied to every future
     transcript. Accuracy improves over time without retraining any model.
  2. Passive vocabulary: every Nepali phrase Saathi overhears is logged locally
     (never uploaded) so the most common words can be reviewed and pre-seeded as
     corrections.

All data lives in the local SQLite db. Nothing leaves the Mac.
"""
import re
import sqlite3
import time

from . import config

_db = sqlite3.connect(config.DB_PATH, check_same_thread=False)
_db.executescript("""
    CREATE TABLE IF NOT EXISTS nepali_corrections(
        id INTEGER PRIMARY KEY, wrong TEXT UNIQUE, right TEXT,
        count INTEGER DEFAULT 1, ts REAL);
    CREATE TABLE IF NOT EXISTS nepali_heard(
        id INTEGER PRIMARY KEY, phrase TEXT, ts REAL);
""")

# A few common seed corrections for Nepali words Whisper routinely garbles.
_SEED = {
    "satie": "साथी", "sati": "साथी", "sotty": "साथी",
}
for w, r in _SEED.items():
    _db.execute("INSERT OR IGNORE INTO nepali_corrections(wrong, right, ts) "
                "VALUES(?,?,?)", (w, r, time.time()))
_db.commit()

_cache: dict[str, str] | None = None


def _load() -> dict[str, str]:
    global _cache
    if _cache is None:
        _cache = {w.lower(): r for w, r in
                  _db.execute("SELECT wrong, right FROM nepali_corrections")}
    return _cache


def apply_corrections(text: str) -> str:
    """Replace learned mishearings in a transcript (whole-word, case-insensitive)."""
    corr = _load()
    if not corr:
        return text
    def sub(m):
        return corr.get(m.group(0).lower(), m.group(0))
    # word-ish tokens incl. Devanagari
    return re.sub(r"[\wऀ-ॿ]+", sub, text)


def teach(wrong: str, right: str) -> dict:
    """Record a correction; applies to all future transcripts."""
    global _cache
    _db.execute(
        "INSERT INTO nepali_corrections(wrong, right, ts) VALUES(?,?,?) "
        "ON CONFLICT(wrong) DO UPDATE SET right=excluded.right, "
        "count=count+1, ts=excluded.ts", (wrong.strip(), right.strip(), time.time()))
    _db.commit()
    _cache = None
    return {"learned": f"{wrong} → {right}",
            "note": "I'll get this right from now on."}


def log_heard(phrase: str):
    """Passively record a Nepali phrase overheard (local only)."""
    if phrase.strip():
        _db.execute("INSERT INTO nepali_heard(phrase, ts) VALUES(?,?)",
                    (phrase.strip(), time.time()))
        _db.commit()


def progress() -> dict:
    """Summary of what Saathi has learned."""
    n_corr = _db.execute("SELECT COUNT(*) FROM nepali_corrections").fetchone()[0]
    n_heard = _db.execute("SELECT COUNT(*) FROM nepali_heard").fetchone()[0]
    recent = [c for (c,) in _db.execute(
        "SELECT wrong || ' → ' || right FROM nepali_corrections "
        "ORDER BY ts DESC LIMIT 8")]
    return {"corrections_learned": n_corr, "phrases_heard": n_heard,
            "recent_corrections": recent}
