"""
Flow 9 — Analytics Feedback Loop

Nightly at 2am:
  1. Pull YouTube / TikTok / Instagram analytics
  2. Score every video (views × retention × engagement)
  3. Find top 10% and bottom 10%
  4. Update analytics_weights.json
  5. Flow 2 reads weights before writing next script → makes more of what works
"""

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .. import config
from .mr_yeti_strategy import DEFAULT_ANALYTICS_WEIGHTS, ANALYTICS_WEIGHTS_FILE

_WEIGHTS_PATH = config.ROOT / ANALYTICS_WEIGHTS_FILE
_VIDEOS_LOG   = config.ROOT / "data" / "mr_yeti_videos" / "published_log.json"


# ── helpers ────────────────────────────────────────────────────────────────────

def _load_weights() -> dict:
    try:
        if _WEIGHTS_PATH.exists():
            return json.loads(_WEIGHTS_PATH.read_text())
    except Exception:
        pass
    return dict(DEFAULT_ANALYTICS_WEIGHTS)


def _save_weights(w: dict):
    _WEIGHTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    w["last_updated"] = datetime.now(timezone.utc).isoformat()
    _WEIGHTS_PATH.write_text(json.dumps(w, indent=2, ensure_ascii=False))


def _load_published_log() -> list:
    try:
        if _VIDEOS_LOG.exists():
            return json.loads(_VIDEOS_LOG.read_text())
    except Exception:
        pass
    return []


def _save_published_log(log: list):
    _VIDEOS_LOG.parent.mkdir(parents=True, exist_ok=True)
    _VIDEOS_LOG.write_text(json.dumps(log[-500:], indent=2, ensure_ascii=False))  # keep last 500


# ── YouTube Analytics API ──────────────────────────────────────────────────────

def pull_youtube_analytics(days_back: int = 30) -> list:
    """
    Pull video performance from YouTube Data API v3.
    Returns list of {video_id, title, views, watch_time_minutes, avg_view_percent, likes, comments}.
    Requires YOUTUBE_API_KEY or OAuth token in .env.
    """
    api_key = os.environ.get("YOUTUBE_API_KEY", "")
    channel_id = os.environ.get("YOUTUBE_CHANNEL_ID", "")

    if not api_key and not channel_id:
        return []

    try:
        from saathi.infrastructure.connectors import default_registry
        reg = default_registry()
        # Step 1: get recent uploads
        search = reg.execute(
            capability="search", connector_id="youtube",
            channelId=channel_id, part="id,snippet", order="date",
            maxResults=50, type="video",
            publishedAfter=(datetime.now(timezone.utc) - timedelta(days=days_back)).isoformat())

        items = search.get("items", [])
        video_ids = [i["id"]["videoId"] for i in items if i.get("id", {}).get("videoId")]
        if not video_ids:
            return []

        # Step 2: get stats for each video
        stats = reg.execute(capability="get_video", connector_id="youtube",
                            id=",".join(video_ids), part="statistics,contentDetails,snippet")

        results = []
        for item in stats.get("items", []):
            stats = item.get("statistics", {})
            snippet = item.get("snippet", {})
            results.append({
                "video_id":     item["id"],
                "title":        snippet.get("title", ""),
                "published_at": snippet.get("publishedAt", ""),
                "views":        int(stats.get("viewCount", 0)),
                "likes":        int(stats.get("likeCount", 0)),
                "comments":     int(stats.get("commentCount", 0)),
                "watch_time_minutes": 0,   # requires OAuth Analytics API — stub
                "avg_view_percent":   0,   # requires OAuth Analytics API — stub
                "source": "youtube",
            })
        return results
    except Exception as e:
        return []


def pull_tiktok_analytics() -> list:
    """Pull TikTok video stats via Research API (if available)."""
    from .tiktok_post import _token, token_ok
    if not token_ok():
        return []
    try:
        import httpx
        r = httpx.post(
            "https://open.tiktokapis.com/v2/video/list/",
            headers={"Authorization": f"Bearer {_token()}", "Content-Type": "application/json"},
            json={"max_count": 20, "fields": ["id", "title", "view_count", "like_count",
                                               "comment_count", "share_count", "play_url"]},
            timeout=20,
        )
        if r.status_code != 200:
            return []
        videos = r.json().get("data", {}).get("videos", [])
        return [{
            "video_id":     v.get("id", ""),
            "title":        v.get("title", ""),
            "views":        int(v.get("view_count", 0)),
            "likes":        int(v.get("like_count", 0)),
            "comments":     int(v.get("comment_count", 0)),
            "shares":       int(v.get("share_count", 0)),
            "watch_time_minutes": 0,
            "avg_view_percent":   0,
            "source": "tiktok",
        } for v in videos]
    except Exception:
        return []


# ── Scoring ────────────────────────────────────────────────────────────────────

def score_video(v: dict) -> float:
    """
    Composite performance score:
      views × (1 + like_rate) × (1 + retention_bonus)
    Higher is better.
    """
    views    = max(v.get("views", 0), 1)
    likes    = v.get("likes", 0)
    comments = v.get("comments", 0)
    shares   = v.get("shares", 0)
    avg_pct  = v.get("avg_view_percent", 0)   # 0–100

    like_rate    = likes / views
    engage_rate  = (likes + comments * 2 + shares * 3) / views
    retention    = avg_pct / 100 if avg_pct > 0 else 0.3  # assume 30% if unknown

    score = views * (1 + engage_rate) * (1 + retention)
    return round(score, 2)


def find_top_bottom(videos: list, pct: float = 0.10) -> tuple[list, list]:
    """Returns (top_N, bottom_N) videos by score."""
    if not videos:
        return [], []
    scored = sorted(videos, key=lambda v: v.get("_score", 0), reverse=True)
    n = max(1, int(len(scored) * pct))
    return scored[:n], scored[-n:]


# ── Weight updater ─────────────────────────────────────────────────────────────

def _infer_clip_type(title: str) -> str:
    """Guess clip type from video title keywords."""
    t = title.lower()
    if any(w in t for w in ["mistake", "wrong", "stop", "never say", "don't"]):
        return "mistake"
    if any(w in t for w in ["quiz", "test yourself", "can you", "seconds"]):
        return "quiz"
    if any(w in t for w in ["funny", "reaction", "wait", "pov", "when"]):
        return "funny"
    if any(w in t for w in ["vocabulary", "phrase", "word", "say instead"]):
        return "vocabulary"
    if any(w in t for w in ["band 7", "band 8", "improved", "from band", "went from"]):
        return "success_story"
    return "hook"


def _infer_pillar(title: str) -> str:
    t = title.lower()
    if any(w in t for w in ["before", "after", "vs", "compare"]):
        return "before_after"
    if any(w in t for w in ["don't say", "stop saying", "never say", "wrong"]):
        return "dont_say"
    if any(w in t for w in ["quiz", "question", "answer"]):
        return "quiz"
    if any(w in t for w in ["interview", "alien", "zombie", "dragon"]):
        return "interview"
    return "horror_story"


def update_weights(videos: list) -> dict:
    """
    Recalculate strategy weights from video performance.
    Returns updated weights dict.
    """
    if not videos:
        return _load_weights()

    # Score all videos
    for v in videos:
        v["_score"] = score_video(v)

    top, bottom = find_top_bottom(videos, pct=0.10)

    # Tally scores by clip type and pillar
    clip_totals:  dict[str, list] = {}
    pillar_totals: dict[str, list] = {}

    for v in videos:
        ct = _infer_clip_type(v.get("title", ""))
        p  = _infer_pillar(v.get("title", ""))
        clip_totals.setdefault(ct, []).append(v["_score"])
        pillar_totals.setdefault(p, []).append(v["_score"])

    def _avg(lst): return sum(lst) / len(lst) if lst else 1.0

    # Normalise: divide each average by global average → relative multiplier
    all_scores = [v["_score"] for v in videos]
    global_avg = _avg(all_scores)

    clip_weights   = {ct: round(_avg(sc) / global_avg, 3) for ct, sc in clip_totals.items()}
    pillar_weights = {p:  round(_avg(sc) / global_avg, 3) for p,  sc in pillar_totals.items()}

    # Extract winning hook keywords from top videos
    hook_keywords = []
    for v in top:
        title = v.get("title", "").lower()
        for kw in ["mistake", "secret", "never", "stop", "this one", "instantly",
                   "% of students", "examiner", "band 7", "band 5", "actually"]:
            if kw in title and kw not in hook_keywords:
                hook_keywords.append(kw)

    # Optimal duration: average duration of top videos
    top_durations = [v.get("duration_seconds", 45) for v in top if v.get("duration_seconds")]
    optimal_duration = int(sum(top_durations) / len(top_durations)) if top_durations else 45

    weights = _load_weights()
    weights["clip_type_scores"].update(clip_weights)
    weights["pillar_scores"].update(pillar_weights)
    weights["hook_patterns"] = hook_keywords[:20]
    weights["optimal_duration"] = optimal_duration
    weights["top_video_titles"] = [v.get("title", "") for v in top[:5]]
    weights["bottom_video_titles"] = [v.get("title", "") for v in bottom[:5]]

    _save_weights(weights)
    return weights


# ── Main nightly job ───────────────────────────────────────────────────────────

def run_analytics_loop() -> dict:
    """
    Full nightly analytics pass.
    Called by scheduler at 2am and by Flow 9 webhook.
    """
    yt_videos = pull_youtube_analytics(days_back=30)
    tt_videos = pull_tiktok_analytics()
    all_videos = yt_videos + tt_videos

    if not all_videos:
        return {"ok": True, "note": "No analytics data yet — channel too new or API not configured"}

    weights = update_weights(all_videos)

    # Score for report
    for v in all_videos:
        v["_score"] = score_video(v)
    top, bottom = find_top_bottom(all_videos)

    report = {
        "ok":            True,
        "videos_analyzed": len(all_videos),
        "top_performers":  [{"title": v["title"], "views": v["views"], "score": v["_score"]}
                             for v in top],
        "worst_performers":[{"title": v["title"], "views": v["views"], "score": v["_score"]}
                             for v in bottom],
        "updated_weights": weights,
        "insight": _generate_insight(weights),
    }

    # Save report
    report_path = config.ROOT / "data" / "analytics_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))

    return report


def _generate_insight(weights: dict) -> str:
    """Plain-English summary of what the data says to make more of."""
    ct = weights.get("clip_type_scores", {})
    if not ct:
        return "Not enough data yet."
    best_clip  = max(ct, key=lambda k: ct[k])
    worst_clip = min(ct, key=lambda k: ct[k])
    ratio = round(ct[best_clip] / max(ct[worst_clip], 0.01), 1)
    patterns = ", ".join(weights.get("hook_patterns", [])[:5]) or "none yet"
    return (
        f"'{best_clip}' clips outperform '{worst_clip}' by {ratio}x — make more {best_clip}s. "
        f"Winning hook keywords: {patterns}. "
        f"Optimal clip length: {weights.get('optimal_duration', 45)}s."
    )


def get_weights() -> dict:
    """Called by Flow 2 (script writer) before generating a script."""
    return _load_weights()
