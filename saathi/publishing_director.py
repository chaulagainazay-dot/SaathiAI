"""Publishing Director — the last department in the studio chain.

Consumes the structured artifacts the upstream Directors emitted (Script Doc +
Render Package + plan) and produces ONE more structured artifact: a **Publishing
Package** — a per-platform, ready-to-post manifest. It decides HOW each platform
wants the same episode framed (title length, hashtag style, aspect, caption,
schedule slot) but never posts anything itself — publishing/connectors do that,
exactly like the Render Director never renders pixels.

Platforms: youtube, tiktok, instagram, facebook, linkedin, telegram, blog,
website, pielts. Deterministic — no LLM call — so it never hard-fails and the
whole produce() chain stays cheap. Adapt, don't regenerate: every platform reuses
the same episode assets, reshaped to the platform's rules.
"""
from __future__ import annotations

import re

# platform rules: title cap, description cap, tag count, aspect, hashtag prefix
PLATFORMS = {
    "youtube":   {"title": 100, "desc": 5000, "tags": 15, "aspect": "9:16", "hashtag": True,  "cross": "video"},
    "tiktok":    {"title": 100, "desc": 2200, "tags": 8,  "aspect": "9:16", "hashtag": True,  "cross": "video"},
    "instagram": {"title": 125, "desc": 2200, "tags": 12, "aspect": "9:16", "hashtag": True,  "cross": "reel"},
    "facebook":  {"title": 120, "desc": 5000, "tags": 6,  "aspect": "9:16", "hashtag": True,  "cross": "video"},
    "linkedin":  {"title": 150, "desc": 3000, "tags": 5,  "aspect": "1:1",  "hashtag": True,  "cross": "post"},
    "telegram":  {"title": 120, "desc": 1024, "tags": 4,  "aspect": "9:16", "hashtag": True,  "cross": "video"},
    "blog":      {"title": 70,  "desc": 160,  "tags": 10, "aspect": "16:9", "hashtag": False, "cross": "article"},
    "website":   {"title": 70,  "desc": 160,  "tags": 10, "aspect": "16:9", "hashtag": False, "cross": "article"},
    "pielts":    {"title": 80,  "desc": 300,  "tags": 8,  "aspect": "9:16", "hashtag": False, "cross": "lesson"},
}

# default publish order across the day (staggered so one episode fans out)
SCHEDULE = ["youtube", "tiktok", "instagram", "facebook", "telegram", "linkedin", "blog", "website", "pielts"]


def _clip(text: str, cap: int) -> str:
    text = (text or "").strip()
    if len(text) <= cap:
        return text
    return text[: cap - 1].rsplit(" ", 1)[0].rstrip() + "…"


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")[:60]


def _hashtags(tags: list, n: int, on: bool) -> list:
    tags = [t for t in (tags or []) if t][:n]
    if not on:
        return tags
    return ["#" + re.sub(r"[^A-Za-z0-9]", "", t.title().replace(" ", "")) for t in tags]


def _platform_entry(name: str, rules: dict, *, title, desc, tags, cta, thumb, slot, aspect_avail) -> dict:
    body = desc if not cta else f"{desc}\n\n{cta}"
    return {
        "platform": name,
        "format": rules["cross"],
        "title": _clip(title, rules["title"]),
        "description": _clip(body, rules["desc"]),
        "hashtags": _hashtags(tags, rules["tags"], rules["hashtag"]),
        "aspect": rules["aspect"] if rules["aspect"] in aspect_avail or True else "9:16",
        "thumbnail": thumb,
        "schedule_slot": slot,
    }


def package(script: dict, *, render_plan: dict | None = None, plan: dict | None = None,
            episode: str = "", platforms: list | None = None) -> dict:
    """Script Doc (+ Render Package + plan) → Publishing Package (per-platform manifest)."""
    script = script or {}
    render_plan = render_plan or {}
    plan = plan or {}
    episode = episode or script.get("episode", "")

    seo = script.get("seo") or {}
    title = seo.get("title") or script.get("topic") or plan.get("topic", "IELTS lesson")
    desc = seo.get("description") or script.get("hook") or ""
    tags = seo.get("tags") or plan.get("tags") or []
    cta = script.get("cta", "")
    thumbs = script.get("thumbnail_ideas") or []
    thumb = thumbs[0] if thumbs else ""
    aspect_avail = {render_plan.get("settings", {}).get("aspect", "9:16"), "9:16", "16:9", "1:1"}

    names = platforms or SCHEDULE
    order = [p for p in SCHEDULE if p in names] + [p for p in names if p not in SCHEDULE]
    entries = []
    for i, name in enumerate(order):
        rules = PLATFORMS.get(name)
        if not rules:
            continue
        entries.append(_platform_entry(name, rules, title=title, desc=desc, tags=tags,
                                        cta=cta, thumb=thumb, slot=i, aspect_avail=aspect_avail))

    issues = []
    if not title:
        issues.append("missing title")
    if not entries:
        issues.append("no target platforms")

    return {
        "episode": episode,
        "slug": _slug(title),
        "platform_count": len(entries),
        "platforms": entries,
        "master": {"title": title, "description": desc, "tags": tags, "cta": cta, "thumbnail": thumb},
        "schedule": [e["platform"] for e in entries],
        "ok": not issues,
        "issues": issues,
    }
