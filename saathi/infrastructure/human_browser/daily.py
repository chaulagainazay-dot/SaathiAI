"""Daily publisher — pick the next queued clip, publish via the proven browser
path, record it, and report to the platform so the Maturity dashboard reflects
real Applications activity.

Queue convention (on the Mac, where Chrome runs):
    queue/youtube/<clip>.mp4         + optional <clip>.json {title, description, visibility}
    queue/youtube/published/         ← moved here on success

Deterministic core with injected `publisher` / `store` / `reporter` (tested with
fakes; no browser, no network).
"""
from __future__ import annotations

import json
import time
from pathlib import Path


def next_in_queue(queue_dir: str) -> tuple[Path, dict] | None:
    q = Path(queue_dir)
    if not q.exists():
        return None
    vids = sorted((p for p in q.glob("*.mp4")), key=lambda p: p.stat().st_mtime)
    if not vids:
        return None
    vid = vids[0]
    meta = {}
    side = vid.with_suffix(".json")
    if side.exists():
        try:
            meta = json.loads(side.read_text())
        except Exception:
            pass
    return vid, meta


def publish_next(queue_dir: str, *, publisher, store=None, reporter=None,
                 default_visibility: str = "Unlisted") -> dict:
    """Publish the oldest queued clip. `publisher(path, title, description,
    visibility) -> dict` is the browser publish. Returns a status dict."""
    picked = next_in_queue(queue_dir)
    if picked is None:
        return {"status": "empty", "message": "no video queued"}
    vid, meta = picked
    title = meta.get("title", vid.stem)
    t0 = time.time()
    try:
        result = publisher(path=str(vid), title=title,
                           description=meta.get("description", ""),
                           visibility=meta.get("visibility", default_visibility)) or {}
        ok, error, video_url = True, "", result.get("video_url", "")
        timeline = result.get("timeline", [])
        # move the clip + sidecar into published/
        pub = Path(queue_dir) / "published"; pub.mkdir(parents=True, exist_ok=True)
        vid.rename(pub / vid.name)
        side = vid.with_suffix(".json")
        if side.exists():
            side.rename(pub / side.name)
    except Exception as e:
        ok, error, video_url, timeline = False, str(e), "", []

    run = {"workflow": "youtube_upload", "capability": "publish_video", "title": title,
           "ok": ok, "error": error, "video_url": video_url,
           "duration_ms": round((time.time() - t0) * 1000), "started": t0, "timeline": timeline}
    if store is not None:
        try:
            store.record(**run)
        except Exception:
            pass
    if reporter is not None:
        try:
            reporter(run)          # POST to the VM so the dashboard reflects it
        except Exception:
            pass
    return {"status": "ok" if ok else "failed", **run}
