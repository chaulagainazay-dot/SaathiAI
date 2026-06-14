"""Daily auto-poster — at 8pm Baadar posts the next queued Mr Yeti video to every
connected platform (YouTube now; Facebook + Instagram once their n8n webhook is set).

Posts from a QUEUE (data/post_queue.json) so quality stays controlled and no heavy
daily video rendering is needed. Keep the queue stocked; Baadar pings when it's low.
Runs only while the Mac + n8n + Baadar are on.
"""
import datetime as dt
import json
import os

import httpx

from . import config

QUEUE = config.ROOT / "data" / "post_queue.json"


def _load() -> list:
    try:
        return json.loads(QUEUE.read_text())
    except Exception:
        return []


def _save(q: list):
    QUEUE.parent.mkdir(parents=True, exist_ok=True)
    QUEUE.write_text(json.dumps(q, indent=2))


def add(video_path: str, title: str, description: str = "", tags: str = "", caption: str = "") -> int:
    """Add a ready video to the posting queue. Returns the number of pending items."""
    q = _load()
    q.append({
        "video_path": os.path.expanduser(video_path),
        "title": title, "description": description, "tags": tags,
        "caption": caption or description, "posted": False,
        "added": dt.datetime.now().isoformat(timespec="seconds"),
    })
    _save(q)
    return len([i for i in q if not i.get("posted")])


def pending() -> list:
    return [i for i in _load() if not i.get("posted")]


def _post_fb_ig(item: dict) -> dict:
    """Post a Reel to Facebook + Instagram via the configured n8n webhook."""
    from . import connections
    fb = connections.get_all().get("facebook", {})
    url = fb.get("webhook")
    if not (fb.get("connected") and url):
        return {"status": "fb_ig_not_configured"}
    r = httpx.post(url, json={"videoPath": item["video_path"],
                              "caption": item.get("caption", "")}, timeout=600)
    return {"status": "ok" if r.status_code < 400 else "failed", "http": r.status_code}


def run_daily_autopost() -> dict:
    """Post the next queued video to all connected platforms. Called by the 8pm scheduler."""
    from .scheduler import _notify
    from .tools import content_studio
    from . import connections

    q = _load()
    nxt = next((i for i in q if not i.get("posted")), None)
    if not nxt:
        _notify("📭 Baadar autopost", "Video queue is empty — add videos so I can post tomorrow.")
        return {"status": "empty"}

    results = {}
    conns = connections.get_all()
    # YouTube (works today)
    if conns.get("youtube", {}).get("connected"):
        results["youtube"] = content_studio.publish_to_youtube(
            nxt["video_path"], nxt["title"], nxt.get("description", ""), nxt.get("tags", ""))
    # Facebook + Instagram (once their webhook is set)
    if conns.get("facebook", {}).get("connected"):
        results["facebook_instagram"] = _post_fb_ig(nxt)

    nxt["posted"] = True
    nxt["posted_at"] = dt.datetime.now().isoformat(timespec="seconds")
    nxt["result"] = {k: (v.get("status") if isinstance(v, dict) else v) for k, v in results.items()}
    _save(q)

    left = len(pending())
    _notify("✅ Baadar posted today's video",
            f"{nxt['title']}\nPlatforms: {nxt['result']}\n{left} videos left in queue.")
    if left <= 2:
        _notify("⚠️ Baadar — queue running low", f"Only {left} videos left. Add more so I keep posting daily.")
    return {"status": "posted", "title": nxt["title"], "platforms": nxt["result"], "left": left}
