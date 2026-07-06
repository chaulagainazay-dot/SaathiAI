"""SaathiAI Studio — the movie studio inside SaathiAI OS.

First slice: the Director/Planner. Decides WHAT to produce today from the
curriculum, skips anything Content Memory already covered, and assembles a
StudioBrief the production pipeline (AIStudio) executes. Baadar is the executive
producer (goals/analytics); this module is HOW production is planned.

Reuses existing pieces — curriculum (what to teach), character Bible (who Mr.
Yeti is), Content Memory (avoid repetition). Later slices add Trend Hunter,
Storyboard, QA, Shorts, Social Adapter, Learning Engine agents.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class StudioBrief:
    day: int
    topic: str
    skill: str
    phase: str
    objective: str
    episode: str
    already_covered: bool
    avoid: list = field(default_factory=list)      # recent topics — don't repeat
    character: dict = field(default_factory=dict)   # Mr. Yeti reference
    voice_tone: str = "friendly"

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def plan_today(now: float | None = None, *, lookahead: int = 30) -> StudioBrief:
    """Pick the day's lesson; if Content Memory already covered it, advance to the
    next uncovered curriculum day (up to `lookahead`). Returns a production brief."""
    from saathi.curriculum import today, lesson_for_day
    from saathi.content_memory import default_memory
    mem = default_memory()

    lesson = today(now)
    covered = mem.is_covered(lesson.topic)
    if covered:
        for d in range(lesson.day + 1, lesson.day + 1 + lookahead):
            nxt = lesson_for_day(d)
            if not mem.is_covered(nxt.topic):
                lesson, covered = nxt, False
                break

    character, tone = {}, "friendly"
    try:
        from saathi.character import BIBLE, voice_tone
        character = {"name": BIBLE["name"], "appearance": BIBLE["appearance"],
                     "style": BIBLE["style"], "palette": BIBLE["palette"]}
        tone = voice_tone()
    except Exception:
        pass

    return StudioBrief(
        day=lesson.day, topic=lesson.topic, skill=lesson.skill, phase=lesson.phase,
        objective=lesson.objective, episode=lesson.episode, already_covered=covered,
        avoid=mem.recent_topics(15), character=character, voice_tone=tone)
