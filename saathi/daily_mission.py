"""Daily IELTS Mission — turns today's curriculum Lesson into a zero-choice
morning mission, and records that Ajay actually did it (streak + episodes).

Fixes the real problem: not missing features, but not feeling like opening the
app. The briefing assigns a mission; Saathi becomes a coach, not a dashboard.
One lesson drives both the content factory AND Ajay's own study.

Storage: ~/.saathi/study.json (date → which mission items are done). No app to
open — mark items via /api/v1/mission/complete or the Telegram commands.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

# the four daily actions (matches the morning-briefing mock)
ITEMS = [("lesson", "Watch today's lesson"), ("speaking", "Complete Speaking"),
         ("writing", "Complete Writing"), ("quiz", "Complete Quiz")]
REWARD = {"episodes": 1, "streak": 1, "dream_pct": 0.03}


def _path() -> Path:
    p = Path(os.path.expanduser("~/.saathi/study.json"))
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _load() -> dict:
    p = _path()
    if p.exists():
        try:
            return json.loads(p.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save(data: dict) -> None:
    _path().write_text(json.dumps(data, indent=2))


def _key(now: float) -> str:
    return time.strftime("%Y-%m-%d", time.localtime(now))


def status(now: float | None = None) -> dict:
    now = now or time.time()
    return _load().get(_key(now), {})


def mark(item: str, done: bool = True, now: float | None = None) -> dict:
    now = now or time.time()
    data = _load()
    day = data.setdefault(_key(now), {})
    day[item] = bool(done)
    _save(data)
    return day


def streak(now: float | None = None) -> int:
    """Consecutive days (ending today or yesterday) with the lesson watched."""
    now = now or time.time()
    data = _load()
    n, cur = 0, now
    # allow today to be unfinished: start counting from today if done, else yesterday
    if not data.get(_key(now), {}).get("lesson"):
        cur = now - 86400
    while data.get(_key(cur), {}).get("lesson"):
        n += 1
        cur -= 86400
    return n


def mission(now: float | None = None) -> dict:
    from saathi.curriculum import today, program
    now = now or time.time()
    les = today(now)
    prog = program(now)
    st = status(now)
    checklist = [{"key": k, "label": lbl, "done": bool(st.get(k))} for k, lbl in ITEMS]
    done_n = sum(1 for c in checklist if c["done"])
    return {
        "program": prog.title, "day": les.day, "episode": les.episode,
        "youtube_number": les.youtube_number, "topic": les.topic, "phase": les.phase,
        "skill": les.skill, "difficulty": les.difficulty,
        "estimated_minutes": les.estimated_minutes,
        "video_status": "Ready to Generate", "checklist": checklist,
        "completed": done_n, "total": len(checklist), "streak": streak(now),
        "reward": REWARD,
    }


def briefing_lines(now: float | None = None) -> list[str]:
    m = mission(now)
    lines = ["", "────────────────────────", "",
             f"🎓  {m['program']} — Day {m['day']} / {m['episode']}",
             f"     Today: {m['topic']}  ({m['difficulty']})",
             f"🎥  {m['youtube_number']} · {m['video_status']}",
             f"⏱️  ~{m['estimated_minutes']} min  ·  🔥 streak {m['streak']}d", "",
             "Today's Mission"]
    for c in m["checklist"]:
        lines.append(f"  {'✅' if c['done'] else '⬜'} {c['label']}")
    lines += ["", "Reply:  /start  /practice  /publish  /skip"]
    return lines


def review(now: float | None = None) -> str:
    """Night review — coach tone."""
    m = mission(now)
    lines = ["🌙  Daily Review", "", f"{m['program']} · Day {m['day']}"]
    for c in m["checklist"]:
        lines.append(f"  {'✅' if c['done'] else '❌'} {c['label']}")
    lines += ["", f"Current streak   {m['streak']} day(s)",
              f"Tomorrow         Day {m['day'] + 1}"]
    return "\n".join(lines)
