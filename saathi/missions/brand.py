"""Brand Identity Department — per-Mission brand assets, incl. Voice Identity.

Voice becomes a reusable company asset, like the Character Bible and Knowledge
Graph — not a global setting. Each Mission owns a Brand Identity (logo, colours,
fonts, writing style, character, intro/outro, music, watermark, guidelines) and a
versioned Voice Registry. Every Director (Script, Voice, Render, Publishing) reads
the Mission's active voice, so Mr. Yeti stays patient/encouraging while Surmount
Travels is warm/adventurous and HCG is confident/analytical — same pipeline,
different personality.

This module is the ASSET + REGISTRY layer (structured, versioned, Director-read).
The audio recording/analysis/embedding backend plugs in later behind `provider`
without changing anything here — same adapter pattern as the Model Router.
"""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from pathlib import Path

# the recording prompts the Voice Setup wizard reads out (cover the TTS spectrum)
SAMPLE_PROMPTS = [
    {"id": 1, "label": "Intro", "text": "Hi. My name is Ajay. I created SaathiAI to help "
     "businesses become more intelligent. Today I'm recording my voice."},
    {"id": 2, "label": "Grammar Lesson", "text": "Today we're learning the Present Perfect Tense. "
     "Many students confuse it with the Past Simple. Let's make it easy."},
    {"id": 3, "label": "Conversation", "text": "Hello everyone. Welcome back to another lesson. "
     "Today we'll solve one IELTS Speaking question together."},
    {"id": 4, "label": "Story", "text": "Yesterday I met a traveler from Canada. He had visited "
     "Nepal for two weeks. He loved the mountains and the people."},
    {"id": 5, "label": "Emotion", "text": "Amazing! Excellent! Don't worry. Let's try again. You can do this."},
]

PURPOSES = ("own_voice", "mr_yeti", "ceo", "narrator", "sales", "support", "podcast", "news", "other")

# per-business voice personality defaults (department key → voice character)
_VOICE_DEFAULTS = {
    "ai_studio": {"style": "teacher", "emotion": "patient, encouraging", "energy": "medium-high"},
    "education": {"style": "teacher", "emotion": "patient, encouraging", "energy": "medium-high"},
    "travel": {"style": "narrator", "emotion": "warm, adventurous", "energy": "medium-high"},
    "hcg": {"style": "analyst", "emotion": "confident, concise", "energy": "medium"},
    "cafeteria": {"style": "friendly", "emotion": "warm", "energy": "medium"},
}

_BRAND_FIELDS = ("logo", "colors", "fonts", "writing_style", "character", "intro", "outro",
                 "music", "watermark", "guidelines", "active_voice_id")


def default_brand(mission: dict) -> dict:
    dept = mission.get("department", "")
    v = _VOICE_DEFAULTS.get(dept, {"style": "narrator", "emotion": "neutral", "energy": "medium"})
    return {"colors": [], "fonts": [], "writing_style": "", "character": mission.get("name", ""),
            "voice_defaults": v, "guidelines": "", "active_voice_id": ""}


def analyze_samples(samples: list) -> dict:
    """Honest analysis: WPM from provided text+duration; the rest is what the user
    stated. Marked estimated=True until a real audio backend measures acoustics."""
    words = sum(len(str(s.get("text", "")).split()) for s in samples)
    secs = sum(float(s.get("duration", 0) or 0) for s in samples)
    wpm = round(words / (secs / 60), 0) if secs > 0 else None
    return {"estimated": True, "words": words, "wpm": wpm,
            "note": "WPM from text/duration; acoustic metrics (pitch/energy/accent) require the "
                    "audio backend — recorded here as declared, measured later."}


def recommend(profile: dict) -> dict:
    style = (profile.get("style") or "").lower()
    best, avoid = ["Explainer", "YouTube"], []
    if style in ("teacher", "narrator"):
        best += ["IELTS Teacher", "Podcast"]
        avoid += ["High-energy advertisements", "Movie trailer narration"]
    if style == "analyst":
        best += ["Market updates", "Briefings"]
        avoid += ["Children's content"]
    return {"best_for": list(dict.fromkeys(best)), "not_ideal": avoid}


class BrandStore:
    def __init__(self, db_path: str | None = None):
        self.db_path = Path(db_path) if db_path else (Path.home() / ".saathi" / "mission_brand.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.execute("CREATE TABLE IF NOT EXISTS brand(mission_id TEXT PRIMARY KEY, identity TEXT, updated REAL)")
            c.execute("CREATE TABLE IF NOT EXISTS voice(id TEXT PRIMARY KEY, mission_id TEXT, name TEXT, "
                      "version INTEGER, data TEXT, status TEXT, created REAL)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_voice_m ON voice(mission_id)")

    def _conn(self):
        return sqlite3.connect(str(self.db_path))

    # ── brand ─────────────────────────────────────────────────────────────────
    def get_brand(self, mission_id: str) -> dict:
        with self._conn() as c:
            r = c.execute("SELECT identity FROM brand WHERE mission_id=?", (mission_id,)).fetchone()
        return json.loads(r[0]) if r else {}

    def save_brand(self, mission_id: str, identity: dict) -> None:
        cur = self.get_brand(mission_id)
        cur.update({k: v for k, v in identity.items() if k in _BRAND_FIELDS})
        with self._conn() as c:
            c.execute("INSERT OR REPLACE INTO brand VALUES(?,?,?)",
                      (mission_id, json.dumps(cur), time.time()))

    # ── voice registry (versioned, like the Prompt Registry) ──────────────────
    def register_voice(self, mission_id: str, name: str, data: dict) -> dict:
        with self._conn() as c:
            prev = c.execute("SELECT MAX(version) FROM voice WHERE mission_id=? AND name=?",
                             (mission_id, name)).fetchone()[0]
            version = (prev or 0) + 1
            vid = uuid.uuid4().hex[:16]
            payload = dict(data)
            payload["recommendation"] = recommend(payload)
            if payload.get("samples"):
                payload["analysis"] = analyze_samples(payload["samples"])
            c.execute("INSERT INTO voice VALUES(?,?,?,?,?,?,?)",
                      (vid, mission_id, name, version, json.dumps(payload), "active", time.time()))
        return self.get_voice(vid)

    def get_voice(self, vid: str) -> dict | None:
        with self._conn() as c:
            r = c.execute("SELECT id,mission_id,name,version,data,status,created FROM voice WHERE id=?",
                          (vid,)).fetchone()
        if not r:
            return None
        d = dict(zip(["id", "mission_id", "name", "version", "status", "created"],
                     [r[0], r[1], r[2], r[3], r[5], r[6]]))
        d.update(json.loads(r[4] or "{}"))
        return d

    def list_voices(self, mission_id: str) -> list[dict]:
        with self._conn() as c:
            ids = [r[0] for r in c.execute("SELECT id FROM voice WHERE mission_id=? ORDER BY created DESC",
                                           (mission_id,)).fetchall()]
        return [self.get_voice(i) for i in ids]

    def set_active_voice(self, mission_id: str, vid: str) -> bool:
        v = self.get_voice(vid)
        if not v or v["mission_id"] != mission_id:
            return False
        self.save_brand(mission_id, {"active_voice_id": vid})
        return True

    def active_voice(self, mission_id: str) -> dict | None:
        """What every Director reads for this Mission's voice."""
        vid = self.get_brand(mission_id).get("active_voice_id")
        if vid:
            v = self.get_voice(vid)
            if v:
                return v
        voices = self.list_voices(mission_id)
        return voices[0] if voices else None


_default = None
def default_store() -> BrandStore:
    global _default
    if _default is None:
        _default = BrandStore()
    return _default
