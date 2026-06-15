"""In-app tasks + notifications feed for Baadar.

So Ajay sees, INSIDE the Baadar app, what Baadar did (notifications) and what's left
to do (tasks with one-click links) — no need to open Telegram or type any URL.
"""
import datetime as dt
import json
import threading

from . import config

PATH = config.ROOT / "data" / "tasks.json"
_LOCK = threading.Lock()


def _load() -> dict:
    try:
        return json.loads(PATH.read_text())
    except Exception:
        return {"items": [], "seq": 0}


def _save(d: dict):
    PATH.parent.mkdir(parents=True, exist_ok=True)
    PATH.write_text(json.dumps(d, indent=2))


def add(title: str, kind: str = "task", link: str = "", body: str = "") -> int:
    """kind: 'task' (a to-do, usually with a link) or 'note' (a done/info notification)."""
    with _LOCK:
        d = _load()
        d["seq"] += 1
        d["items"].insert(0, {
            "id": d["seq"], "title": title, "kind": kind, "link": link, "body": body,
            "done": False, "ts": dt.datetime.now().isoformat(timespec="seconds"),
        })
        d["items"] = d["items"][:120]
        _save(d)
        return d["seq"]


def list_items(include_done: bool = False) -> list:
    d = _load()
    return [t for t in d["items"] if include_done or not t.get("done")]


def mark_done(tid: int) -> bool:
    with _LOCK:
        d = _load()
        hit = False
        for t in d["items"]:
            if t["id"] == tid:
                t["done"] = True
                hit = True
        _save(d)
        return hit


def clear_done():
    with _LOCK:
        d = _load()
        d["items"] = [t for t in d["items"] if not t.get("done")]
        _save(d)
