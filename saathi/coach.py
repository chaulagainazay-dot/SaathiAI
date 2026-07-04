"""Saathi Coach (Learn box) — IELTS as part of running the operating system.

The insight: the problem isn't IELTS, it's the *learning experience*. So instead of
opening a test app, IELTS becomes today's **⭐ Learn** — a short conversational
speaking task about Ajay's OWN projects (SaathiAI, cafeteria, crypto, travel, the
Canada dream), scored live like an examiner, feeding the Learning Runtime and a
Band Predictor. Completing it lights the Learn box on the daily scorecard.

Deterministic scoring core (AP-17) so it's testable without an LLM; the LLM can
refine wording later. Episode recorder / clock / db injected (AP-12). Every session
is a Learning Episode → progress you can chase instead of exercises you must finish.
"""
from __future__ import annotations

import math
import re
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

# Ajay speaks fluently about his own life — use it as the exam material.
TOPICS = [
    "Explain how SaathiAI works and why you built it.",
    "Describe your hospital cafeteria and how you reduce food waste.",
    "Explain your dream of moving to Canada and why it matters to you.",
    "Describe how AI can improve education.",
    "Explain how your crypto signal system makes decisions.",
    "Describe a difficult business decision you made recently.",
    "Talk about how automation changed the way you run your businesses.",
    "Explain today's architecture work — but only in English.",
    "Describe Mr. Yeti and your plan to grow the channel.",
    "Explain why you prefer building systems over traditional studying.",
]

SKILLS = ["Listening", "Reading", "Writing", "Speaking"]
BASELINE = {"Listening": 7.5, "Reading": 8.0, "Writing": 6.5, "Speaking": 6.5}
FILLERS = {"actually", "basically", "like", "um", "uh", "really", "just", "so", "kinda", "stuff"}


def _clamp(x, lo=4.0, hi=9.0):
    return max(lo, min(hi, x))


def _half(x):
    return round(x * 2) / 2


def pick_topic(seed: int) -> str:
    return TOPICS[seed % len(TOPICS)]


@dataclass
class Challenge:
    skill: str
    topic: str
    minutes: int
    expected_band_gain: float
    reason: str

    def render(self) -> str:
        return (f"🎓  Today's Learn — {self.skill} · {self.minutes} min\n"
                f"     “{self.topic}”\n"
                f"     Expected band gain +{self.expected_band_gain:.2f} · {self.reason}")


def daily_challenge(*, last_practiced_days: dict[str, int] | None = None,
                    now: float | None = None) -> Challenge:
    """Pick today's challenge — prefer the skill you've neglected longest."""
    now = now or time.time()
    lp = last_practiced_days or {}
    # the skill you've gone longest without → today's focus (Speaking wins ties)
    skill = max(SKILLS, key=lambda s: (lp.get(s, 99), s == "Speaking"))
    days = lp.get(skill, 99)
    reason = (f"You haven't practiced {skill.lower()} for {days} days."
              if days < 99 else f"Let's build momentum on {skill.lower()}.")
    seed = int(now // 86400)
    return Challenge(skill=skill, topic=pick_topic(seed), minutes=8,
                     expected_band_gain=0.03, reason=reason)


@dataclass
class SpeakingScore:
    grammar: float
    vocabulary: float
    fluency: float
    pronunciation: float
    band: float
    weakness: str
    words: int
    fillers: dict[str, int] = field(default_factory=dict)

    def render(self) -> str:
        return (f"🗣️  Grammar {self.grammar} · Vocabulary {self.vocabulary} · "
                f"Fluency {self.fluency} · Pronunciation {self.pronunciation}\n"
                f"    Estimated band {self.band}\n    Weakness: {self.weakness}")


def score_speaking(transcript: str, *, pronunciation_hint: float | None = None) -> SpeakingScore:
    """Deterministic examiner-style heuristic. Real, testable signal from text:
    length (fluency), lexical diversity (vocabulary), sentence structure (grammar),
    and filler overuse (the classic weakness)."""
    tokens = re.findall(r"[a-zA-Z']+", transcript.lower())
    n = len(tokens)
    if n < 8:
        return SpeakingScore(4.0, 4.0, 4.0, 4.0, 4.0,
                             "Too short — keep talking for the full time.", n, {})
    types = len(set(tokens))
    ttr = types / n                                    # lexical diversity
    fillers = {w: c for w, c in Counter(t for t in tokens if t in FILLERS).items() if c}
    filler_ratio = sum(fillers.values()) / n
    sentences = [s for s in re.split(r"[.!?]+", transcript) if s.strip()]
    avg_len = n / max(1, len(sentences))

    fluency = _clamp(5.5 + min(2.0, n / 70.0) - filler_ratio * 18)
    vocabulary = _clamp(4.8 + ttr * 6.5)
    grammar = _clamp(6.0 + (1.0 - abs(avg_len - 14) / 14) * 2.0)
    pronunciation = pronunciation_hint if pronunciation_hint is not None else _half(fluency - 0.3)

    band = _half((grammar + vocabulary + fluency + pronunciation) / 4)
    top_filler = max(fillers.items(), key=lambda kv: kv[1]) if fillers else None
    if top_filler and top_filler[1] >= 4:
        weakness = f'You repeated "{top_filler[0]}" {top_filler[1]} times.'
    elif filler_ratio > 0.06:
        weakness = "Too many filler words — pause instead."
    elif avg_len < 8:
        weakness = "Sentences are short — link ideas with because / although / which."
    elif vocabulary < 6.5:
        weakness = "Reach for more precise, less common vocabulary."
    else:
        weakness = "Strong — keep extending answers with concrete examples."
    return SpeakingScore(_half(grammar), _half(vocabulary), _half(fluency),
                         _half(pronunciation), band, weakness, n, fillers)


class BandPredictor:
    def __init__(self, db_path: "str | Path", *, now: Callable[[], float] = time.time):
        self.path = str(db_path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        import sqlite3
        self.db = sqlite3.connect(self.path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("CREATE TABLE IF NOT EXISTS coach_sessions "
                        "(id INTEGER PRIMARY KEY, skill TEXT, band REAL, ts REAL)")
        self.db.commit()
        self.now = now

    def record(self, skill: str, band: float) -> None:
        self.db.execute("INSERT INTO coach_sessions (skill,band,ts) VALUES (?,?,?)",
                        (skill, band, self.now()))
        self.db.commit()

    def current_bands(self) -> dict[str, float]:
        bands = dict(BASELINE)
        for skill in SKILLS:
            r = self.db.execute("SELECT band FROM coach_sessions WHERE skill=? "
                                "ORDER BY ts DESC LIMIT 1", (skill,)).fetchone()
            if r:
                bands[skill] = round(r["band"], 1)
        return bands

    def overall(self) -> float:
        b = self.current_bands()
        return _half(sum(b.values()) / len(b))

    def predict(self, *, days_left: int, sessions_per_day: int = 1) -> dict:
        n_sessions = self.db.execute("SELECT COUNT(*) c FROM coach_sessions").fetchone()["c"]
        overall = self.overall()
        remaining = max(0, days_left) * sessions_per_day
        # ~+0.03 band per focused session, front-loaded, capped at band 9
        gain = min(1.0, remaining * 0.03)
        predicted = _half(min(9.0, overall + gain))
        confidence = round(_clamp(0.5 + n_sessions * 0.04, 0.5, 0.95), 2)
        return {"current": self.current_bands(), "overall": overall,
                "predicted_overall": predicted, "days_left": days_left,
                "confidence": confidence, "sessions": n_sessions}


class SaathiCoach:
    """Ties challenge → score → Learning Episode → Band Predictor. Completing a
    session lights the Learn box on the daily scorecard (intent contains 'ielts')."""

    def __init__(self, predictor: BandPredictor, *,
                 record_episode: Callable[..., int] | None = None,
                 publish: Callable[[str, dict], object] | None = None):
        self.predictor = predictor
        if record_episode is None:
            from saathi.integration import ingest_episode as record_episode
        if publish is None:
            from saathi.events import bus
            publish = bus.publish_sync
        self._episode = record_episode
        self._publish = publish

    def practice_speaking(self, transcript: str, *, topic: str = "",
                          pronunciation_hint: float | None = None) -> dict:
        s = score_speaking(transcript, pronunciation_hint=pronunciation_hint)
        self.predictor.record("Speaking", s.band)
        self._episode(
            agent="saathi_coach", department="Saathi Coach", product="pielts",
            intent="ielts_speaking_practice", action=topic or "speaking practice",
            result=f"band {s.band} · weakness: {s.weakness}",
            outcome="success" if s.band >= 6 else "needs_work",
            quality_score=round(s.band / 9.0, 3),
            metadata={"grammar": s.grammar, "vocabulary": s.vocabulary,
                      "fluency": s.fluency, "pronunciation": s.pronunciation,
                      "weakness": s.weakness, "words": s.words})
        self._publish("coach.session", {"skill": "Speaking", "band": s.band})
        return {"score": s, "band": s.band, "prediction": self.predictor.predict(days_left=11)}
