"""PIELTS project dashboard — uploads log, growth targets, and the money goal.

Powers the dashboard at the top of the Baadar app. Goal: grow the @pieltsapp
YouTube channel (and socials) to monetization so it pays for the app's running
costs (AI scoring, Google Flow, Firebase Blaze).
"""
import datetime as dt
import json
import os
import urllib.request

from . import config

DATA = config.ROOT / "data"
UPLOADS = DATA / "pielts_uploads.json"
TARGETS = DATA / "pielts_targets.json"
CHANNEL_ID = "UCn_iedVQ-suLE0hlRmszklg"

# Default goals. Subscriber goal = YouTube Partner Program threshold (monetization).
DEFAULT_TARGETS = {
    "subscribers_goal": 1000,
    "views_goal": 100000,
    "monthly_revenue_goal_usd": 60,
    "costs": [
        {"name": "AI scoring (LLM)", "usd": 20},
        {"name": "Google Flow (Veo)", "usd": 20},
        {"name": "Firebase Blaze", "usd": 20},
    ],
}


def _load(path, default):
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def targets() -> dict:
    t = dict(DEFAULT_TARGETS)
    t.update(_load(TARGETS, {}))
    return t


def set_targets(**kw) -> dict:
    t = targets()
    t.update({k: v for k, v in kw.items() if v is not None})
    DATA.mkdir(parents=True, exist_ok=True)
    TARGETS.write_text(json.dumps(t, indent=2))
    return t


def uploads() -> list:
    return _load(UPLOADS, [])


def log_upload(video_id: str, title: str, platform: str = "youtube") -> int:
    items = uploads()
    items.insert(0, {
        "video_id": video_id, "title": title, "platform": platform,
        "url": f"https://youtu.be/{video_id}" if platform == "youtube" else "",
        "ts": dt.datetime.now().isoformat(timespec="seconds"),
    })
    DATA.mkdir(parents=True, exist_ok=True)
    UPLOADS.write_text(json.dumps(items, indent=2))
    return len(items)


def yt_stats() -> dict:
    """Live channel stats — needs a free YouTube Data API key in env YT_API_KEY."""
    key = os.getenv("YT_API_KEY", "")
    if not key:
        return {}
    try:
        url = (f"https://www.googleapis.com/youtube/v3/channels?part=statistics"
               f"&id={CHANNEL_ID}&key={key}")
        with urllib.request.urlopen(url, timeout=10) as r:
            s = json.load(r)["items"][0]["statistics"]
        return {"subscribers": int(s.get("subscriberCount", 0)),
                "views": int(s.get("viewCount", 0)),
                "videos": int(s.get("videoCount", 0))}
    except Exception:
        return {}


def dashboard() -> dict:
    ups = uploads()
    t = targets()
    stats = yt_stats()
    # Day 1 = first upload date (the day the channel started shipping)
    dates = []
    for u in ups:
        try:
            dates.append(dt.date.fromisoformat(u["ts"][:10]))
        except Exception:
            pass
    start = min(dates) if dates else dt.date.today()
    day = (dt.date.today() - start).days + 1
    monthly_cost = sum(c["usd"] for c in t["costs"])
    return {
        "channel": "@pieltsapp", "channel_id": CHANNEL_ID,
        "day": day, "upload_count": len(ups), "uploads": ups[:20],
        "targets": t, "stats": stats, "monthly_cost": monthly_cost,
        "has_live_stats": bool(stats),
    }
