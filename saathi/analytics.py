"""Performance feedback loop — pull YouTube stats so Baadar learns what works."""
import os

import httpx

from . import pielts


def performance_report() -> dict:
    key = os.getenv("YT_API_KEY", "")
    ups = pielts.uploads()
    vids = [u["video_id"] for u in ups if u.get("video_id")][:30]
    if not key or not vids:
        return {"error": "no YouTube data yet (need API key + uploads)"}
    try:
        r = httpx.get("https://www.googleapis.com/youtube/v3/videos",
                      params={"part": "statistics,snippet", "id": ",".join(vids), "key": key},
                      timeout=15).json()
        items = [{"title": i["snippet"]["title"],
                  "views": int(i["statistics"].get("viewCount", 0)),
                  "likes": int(i["statistics"].get("likeCount", 0))}
                 for i in r.get("items", [])]
        items.sort(key=lambda x: -x["views"])
        return {"channel": pielts.yt_stats(),
                "top": items[:5], "worst": items[-3:] if len(items) > 5 else [],
                "total_videos": len(items)}
    except Exception as e:
        return {"error": str(e)[:150]}
