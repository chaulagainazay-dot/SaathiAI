"""Growth Engine — 7 systems wired into Baadar.

1. content_strategy_30day  — 30-day 2x/day content calendar → Telegram
2. viral_hook_generator    — scroll-stopping hooks in <2 seconds
3. profile_optimizer       — rewrites bios for instant trust + conversion
4. engagement_booster      — rewrites posts to maximise comments/saves
5. dm_sales_converter      — DM reply for commenters asking about the product
6. hashtag_seo_system      — platform-specific hashtag + SEO strategy
7. monthly_analytics       — pulls FB/IG + YouTube stats, formats for Baadar
"""
import json
import os
from datetime import datetime, timedelta
from pathlib import Path

from ._llm_helper import ask_llm, extract_json

_DATA = Path.home() / "SaathiAI" / "data" / "growth"
_DATA.mkdir(parents=True, exist_ok=True)

# ─────────────────────────────────────────────
# Shared brand context (injected into every prompt)
# ─────────────────────────────────────────────
_BRAND = """
Brand: pielts (pielts.web.app) — free IELTS practice app for Nepali & South-Asian students.
Face: MR. YETI — large fluffy white yeti professor, round glasses, tweed blazer.
Handles: @pieltsofficial (IG/FB), @pieltsapp (YouTube/TikTok)
Audience: IELTS students aged 18-35, targeting band 6.5-8.0, Nepal/South Asia/abroad aspirants.
Goals: grow followers → build trust → convert to premium plan or IELTS coaching.
Tone: warm, encouraging, a touch playful. Mix Nepali + English naturally.
Niche pillars: IELTS tips, study-abroad stories, grammar hacks, band-score secrets.
CTA universe: "Free practice → pielts.web.app", "Comment your band score", "Save this",
              "Send to a friend preparing for IELTS", "DM me 'IELTS' to get the free guide".
"""

# ─────────────────────────────────────────────
# 1. 30-DAY CONTENT STRATEGY
# ─────────────────────────────────────────────
_30DAY_PROMPT = """
{brand}

Create a 30-day social media content calendar with 2 posts per day (AM + PM slots).
Start date: {start_date}

GOAL MIX — every post must serve exactly ONE goal:
  GROW   = grow following (shareable, relatable, broad reach)
  TRUST  = build trust (value, proof, behind-scenes, story)
  SELL   = drive sales (pielts premium, coaching, app downloads)

Ratio: 40% GROW, 40% TRUST, 20% SELL

For EACH of the 60 posts return this exact JSON object:
{{
  "day": 1,
  "slot": "AM",           // AM or PM
  "goal": "GROW",
  "platform": "instagram",  // primary platform
  "format": "Reel",         // Reel | Carousel | Story | Static | FB Post | YouTube Short
  "hook": "...",            // scroll-stopping first line (under 10 words)
  "core_message": "...",    // 1 sentence: what value/insight they get
  "caption_starter": "...", // first 2 lines of the caption
  "cta": "..."              // exact call to action text
}}

Return a JSON object: {{ "strategy": [ ...60 post objects... ] }}
"""


_7DAY_PROMPT = """
{brand}

Create a 7-day social media content calendar with 2 posts per day (AM + PM slots).
Days {day_start} through {day_end}. Goal mix: 40% GROW, 40% TRUST, 20% SELL.

Return EXACTLY 14 post objects in this JSON (no extra text):
{{"strategy":[
{{"day":{day_start},"slot":"AM","goal":"GROW","platform":"instagram","format":"Reel","hook":"<10 word hook>","core_message":"<1 sentence>","caption_starter":"<2 lines>","cta":"<action>"}},
{{"day":{day_start},"slot":"PM","goal":"TRUST","platform":"facebook","format":"FB Post","hook":"<hook>","core_message":"<1 sentence>","caption_starter":"<2 lines>","cta":"<action>"}},
... continue for days {day_start} to {day_end} ...
]}}
"""


def _repair_json(raw: str) -> dict:
    """Try to extract and repair JSON even if truncated."""
    import re
    # Try normal extract first
    m = re.search(r'\{.*\}', raw, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass
    # Try to find the strategy array and parse what we can
    m2 = re.search(r'"strategy"\s*:\s*\[(.+)', raw, re.DOTALL)
    if m2:
        arr_str = m2.group(1)
        # Find complete objects
        objects = []
        depth, start_i = 0, None
        for i, ch in enumerate(arr_str):
            if ch == '{':
                if depth == 0:
                    start_i = i
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0 and start_i is not None:
                    try:
                        objects.append(json.loads(arr_str[start_i:i+1]))
                    except Exception:
                        pass
                    start_i = None
        if objects:
            return {"strategy": objects}
    return {}


def content_strategy_30day(start_date: str = "") -> dict:
    """Generate a full 30-day 2x/day content calendar (in four 7-day batches) and save it."""
    if not start_date:
        start_date = datetime.now().strftime("%Y-%m-%d")

    system = "You are an elite social media growth strategist. Return ONLY valid compact JSON."
    all_posts = []

    batches = [(1, 7), (8, 14), (15, 21), (22, 30)]
    for batch_start, batch_end in batches:
        prompt = _7DAY_PROMPT.format(
            brand=_BRAND, day_start=batch_start, day_end=batch_end
        )
        try:
            raw = ask_llm(prompt, system=system, timeout=90)
            data = _repair_json(raw)
            batch_posts = data.get("strategy", [])
            all_posts.extend(batch_posts)
        except Exception as e:
            return {"ok": False, "error": f"Batch days {batch_start}-{batch_end}: {str(e)[:200]}"}

    posts = all_posts

    # Save to disk
    out_file = _DATA / f"strategy_30day_{start_date}.json"
    out_file.write_text(json.dumps({"start_date": start_date, "strategy": posts}, indent=2, ensure_ascii=False))

    # Build a readable Telegram summary (first 7 days)
    lines = [f"📅 30-DAY CONTENT CALENDAR — starting {start_date}\n"]
    current_day = None
    for p in posts[:14]:  # first 7 days × 2 slots
        day = p.get("day", "?")
        if day != current_day:
            current_day = day
            date_str = (datetime.strptime(start_date, "%Y-%m-%d") + timedelta(days=day - 1)).strftime("%b %d")
            lines.append(f"\n📆 DAY {day} — {date_str}")
        slot = p.get("slot", "")
        goal_emoji = {"GROW": "📈", "TRUST": "🤝", "SELL": "💰"}.get(p.get("goal", ""), "•")
        lines.append(
            f"  {slot} {goal_emoji} {p.get('format', '')} on {p.get('platform', '').upper()}\n"
            f"     Hook: \"{p.get('hook', '')}\"\n"
            f"     Message: {p.get('core_message', '')}\n"
            f"     CTA: {p.get('cta', '')}"
        )
    lines.append(f"\n✅ Full 60-post plan saved. Showing Days 1-7 above.")
    telegram_preview = "\n".join(lines)

    return {
        "ok": True,
        "total_posts": len(posts),
        "start_date": start_date,
        "file": str(out_file),
        "telegram_preview": telegram_preview,
        "strategy": posts,
    }


# ─────────────────────────────────────────────
# 2. VIRAL HOOK GENERATOR
# ─────────────────────────────────────────────
_HOOK_PROMPT = """
{brand}

Platform: {platform}
Topic: {topic}
Post goal: {goal}

Generate 5 viral hooks for this post. Each hook must:
- Stop scrolling in under 2 SECONDS
- Be under 10 words for video / under 15 for caption
- Use ONE of these proven formulas:
  A) Loss-aversion: "You're losing band score because..."
  B) Number promise: "3 words that instantly sound Band 8"
  C) Direct call-out: "If you say X in your essay, stop."
  D) Curiosity gap: "Examiners never tell you this about..."
  E) Contrast: "Band 5 says this. Band 8 says this."
  F) Challenge: "I bet you can't answer this IELTS question."
  G) Relatability: "POV: You just got your IELTS score."

Return JSON: {{ "hooks": [
  {{ "hook": "...", "formula": "A", "platform_note": "..." }},
  ...5 items...
]}}
"""


def viral_hook_generator(topic: str, platform: str = "instagram", goal: str = "GROW") -> dict:
    """Generate 5 scroll-stopping hooks for a topic."""
    system = "You are a viral social media copywriter. Return ONLY valid JSON."
    prompt = _HOOK_PROMPT.format(brand=_BRAND, topic=topic, platform=platform, goal=goal)
    try:
        raw = ask_llm(prompt, system=system, timeout=45)
        data = extract_json(raw)
        hooks = data.get("hooks", [])
        return {"ok": True, "topic": topic, "platform": platform, "hooks": hooks,
                "best": hooks[0] if hooks else {}}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


# ─────────────────────────────────────────────
# 3. PROFILE OPTIMIZER
# ─────────────────────────────────────────────
_PROFILE_PROMPT = """
{brand}

Platform: {platform}
Current bio/about text:
\"\"\"{current_bio}\"\"\"

Rewrite this profile bio so that:
1. In 3 SECONDS a visitor knows EXACTLY what they get from following
2. It builds instant trust (social proof, specificity, or transformation promise)
3. It ends with ONE strong call-to-action that converts visitors to followers/subscribers
4. It uses the platform's natural character limit and style:
   - Instagram: 150 chars, line breaks, 1-2 emojis max, link-in-bio CTA
   - Facebook: 255 chars, warm tone, link to website
   - YouTube: 1000 chars, keyword-rich, include search terms, website + social links
5. The tone matches Mr. Yeti: warm, expert, encouraging

Return JSON: {{
  "platform": "{platform}",
  "optimized_bio": "...",
  "why_it_works": "One sentence explanation",
  "char_count": 0
}}
"""


def profile_optimizer(platform: str, current_bio: str = "") -> dict:
    """Rewrite the profile bio for maximum conversion."""
    if not current_bio:
        defaults = {
            "instagram": "IELTS practice app 📚 Free practice at pielts.web.app",
            "facebook": "Free IELTS practice app for students going abroad.",
            "youtube": "Mr. Yeti teaches IELTS. Free practice app at pielts.web.app"
        }
        current_bio = defaults.get(platform, "IELTS practice app")

    system = "You are a conversion copywriter expert. Return ONLY valid JSON."
    prompt = _PROFILE_PROMPT.format(brand=_BRAND, platform=platform, current_bio=current_bio)
    try:
        raw = ask_llm(prompt, system=system, timeout=45)
        data = extract_json(raw)
        return {"ok": True, **data}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


def optimize_all_profiles() -> dict:
    """Optimize bios for Instagram, Facebook, and YouTube at once."""
    results = {}
    for platform in ["instagram", "facebook", "youtube"]:
        results[platform] = profile_optimizer(platform)
    return {"ok": True, "profiles": results}


# ─────────────────────────────────────────────
# 4. ENGAGEMENT BOOSTER
# ─────────────────────────────────────────────
_ENGAGEMENT_PROMPT = """
{brand}

Platform: {platform}
Original post:
\"\"\"{original_post}\"\"\"

Rewrite this post to MAXIMISE engagement. Rules:
1. Keep the SAME core message — do not change the topic
2. Replace the opening with a STRONGER hook (stops scroll in 2 seconds)
3. Make the call-to-action MORE specific (not just "follow me" — be exact)
4. Add ONE question at the END that makes people WANT to comment their answer
   (e.g. "What score do you need? Comment below 👇")
5. Keep the same approximate length
6. Use line breaks for readability (short sentences, white space)

Return JSON: {{
  "rewritten_post": "...",
  "hook_used": "...",
  "question_added": "...",
  "cta_improved": "...",
  "why_more_engaging": "..."
}}
"""


def engagement_booster(original_post: str, platform: str = "instagram") -> dict:
    """Rewrite a post to maximise likes, comments, and saves."""
    system = "You are a social media engagement expert. Return ONLY valid JSON."
    prompt = _ENGAGEMENT_PROMPT.format(brand=_BRAND, platform=platform, original_post=original_post)
    try:
        raw = ask_llm(prompt, system=system, timeout=45)
        data = extract_json(raw)
        return {"ok": True, "platform": platform, **data}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


# ─────────────────────────────────────────────
# 5. DM SALES CONVERTER
# ─────────────────────────────────────────────
_DM_PROMPT = """
{brand}

Someone commented on our post and is asking about the product/app.
Their comment/question: \"\"\"{comment}\"\"\"
Platform: {platform}

Write a DM response that:
1. Thanks them GENUINELY (1 line, specific to their comment)
2. Answers their question directly and briefly
3. Shows the VALUE of pielts.web.app in 1-2 sentences
4. Gives them ONE clear next step (visit site, try free practice, etc.)
5. Ends warm and inviting (like a helpful friend, not a salesperson)
6. Is under 150 words
7. Feels like it was written by a human, not a bot

Return JSON: {{
  "dm_message": "...",
  "tone_note": "...",
  "follow_up_if_no_reply": "..."
}}
"""


def dm_sales_converter(comment: str, platform: str = "instagram") -> dict:
    """Generate a genuine DM response for someone who commented about the product."""
    system = "You are a warm, helpful customer success writer. Return ONLY valid JSON."
    prompt = _DM_PROMPT.format(brand=_BRAND, comment=comment, platform=platform)
    try:
        raw = ask_llm(prompt, system=system, timeout=45)
        data = extract_json(raw)
        return {"ok": True, "platform": platform, "comment_received": comment, **data}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


# ─────────────────────────────────────────────
# 6. HASHTAG & SEO SYSTEM
# ─────────────────────────────────────────────
_HASHTAG_PROMPT = """
{brand}

Post topic: {topic}
Platform: {platform}
Post goal: {goal}   (GROW | TRUST | SELL)

Generate a unique multi-layer hashtag strategy. Baadar's approach:
- TIER 1 (Broad reach, 100K-5M posts): 3 tags — max audience discovery
- TIER 2 (Mid-tail, 10K-100K posts): 5 tags — targeted reach, less competition
- TIER 3 (Niche, <10K posts): 4 tags — high-relevance, community depth
- BRAND tags: 2 tags — #pielts #mrYeti (always include)
- ENGAGEMENT tags: 1 tag based on goal (e.g. #SaveThis #ShareThis #FreeDownload)

Also provide:
- Best posting TIME for this platform + goal
- 3 ENGAGEMENT ACTIONS to do within first 30 min of posting (to boost algorithm)
- 1 UNIQUE growth tactic for this post specifically

Return JSON: {{
  "platform": "{platform}",
  "topic": "{topic}",
  "hashtags": {{
    "tier1": ["..."],
    "tier2": ["..."],
    "tier3": ["..."],
    "brand": ["#pielts", "#mrYeti"],
    "engagement": ["..."],
    "full_set": "copy-paste ready string"
  }},
  "best_posting_time": "...",
  "post_launch_actions": ["action1", "action2", "action3"],
  "unique_growth_tactic": "..."
}}
"""


def hashtag_seo_system(topic: str, platform: str = "instagram", goal: str = "GROW") -> dict:
    """Generate tiered hashtag strategy + growth tactics for a post."""
    system = "You are a social media SEO and hashtag strategist. Return ONLY valid JSON."
    prompt = _HASHTAG_PROMPT.format(brand=_BRAND, topic=topic, platform=platform, goal=goal)
    try:
        raw = ask_llm(prompt, system=system, timeout=45)
        data = extract_json(raw)
        # Save to cache
        cache = _DATA / "hashtag_cache.json"
        history = json.loads(cache.read_text()) if cache.exists() else []
        history.append({"topic": topic, "platform": platform, "data": data,
                        "saved_at": datetime.now().isoformat()})
        cache.write_text(json.dumps(history[-50:], indent=2, ensure_ascii=False))
        return {"ok": True, **data}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


# ─────────────────────────────────────────────
# 7. MONTHLY ANALYTICS REVIEW
# ─────────────────────────────────────────────
def _get_ig_insights(page_token: str, ig_id: str) -> dict:
    """Pull basic Instagram Business account metrics."""
    import httpx
    API = "https://graph.facebook.com/v19.0"
    try:
        # Account-level metrics
        r = httpx.get(f"{API}/{ig_id}", params={
            "fields": "followers_count,media_count,name,username",
            "access_token": page_token
        }, timeout=15)
        account = r.json()

        # Recent media performance
        r2 = httpx.get(f"{API}/{ig_id}/media", params={
            "fields": "id,caption,like_count,comments_count,timestamp,media_type",
            "limit": 12,
            "access_token": page_token
        }, timeout=15)
        media = r2.json().get("data", [])

        total_likes = sum(m.get("like_count", 0) for m in media)
        total_comments = sum(m.get("comments_count", 0) for m in media)
        avg_likes = round(total_likes / len(media), 1) if media else 0
        avg_comments = round(total_comments / len(media), 1) if media else 0
        top_post = max(media, key=lambda m: m.get("like_count", 0)) if media else {}

        return {
            "followers": account.get("followers_count", 0),
            "total_posts": account.get("media_count", 0),
            "last_12_posts_avg_likes": avg_likes,
            "last_12_posts_avg_comments": avg_comments,
            "top_post_likes": top_post.get("like_count", 0),
            "top_post_caption": (top_post.get("caption") or "")[:80],
        }
    except Exception as e:
        return {"error": str(e)[:100]}


def _get_yt_stats() -> dict:
    """Pull YouTube channel stats."""
    try:
        from .. import pielts
        return pielts.yt_stats() or {}
    except Exception as e:
        return {"error": str(e)[:100]}


def _get_fb_insights(page_token: str, page_id: str) -> dict:
    """Pull basic Facebook Page metrics."""
    import httpx
    API = "https://graph.facebook.com/v19.0"
    try:
        r = httpx.get(f"{API}/{page_id}", params={
            "fields": "fan_count,followers_count,name",
            "access_token": page_token
        }, timeout=15)
        d = r.json()
        return {
            "page_likes": d.get("fan_count", 0),
            "followers": d.get("followers_count", 0),
            "name": d.get("name", ""),
        }
    except Exception as e:
        return {"error": str(e)[:100]}


def monthly_analytics_review() -> dict:
    """Pull all platform analytics and return a formatted monthly report."""
    import json as _json
    conn_file = Path.home() / "SaathiAI" / "data" / "connections.json"
    try:
        conn = _json.loads(conn_file.read_text())
    except Exception:
        conn = {}

    fb = conn.get("facebook", {})
    ig = conn.get("instagram", {})
    page_token = fb.get("page_access_token", "")
    page_id = fb.get("page_id", "")
    ig_id = ig.get("ig_account_id", "")

    report = {
        "report_date": datetime.now().strftime("%Y-%m-%d"),
        "instagram": _get_ig_insights(page_token, ig_id) if page_token and ig_id else {"error": "not configured"},
        "facebook": _get_fb_insights(page_token, page_id) if page_token and page_id else {"error": "not configured"},
        "youtube": _get_yt_stats(),
    }

    # Save report
    report_file = _DATA / f"analytics_{datetime.now().strftime('%Y%m')}.json"
    report_file.write_text(json.dumps(report, indent=2, ensure_ascii=False))

    # Build readable summary
    ig_data = report["instagram"]
    fb_data = report["facebook"]
    yt_data = report["youtube"]

    now = datetime.now().strftime("%B %Y")
    lines = [
        f"📊 BAADAR MONTHLY ANALYTICS — {now}",
        "",
        "📸 INSTAGRAM (@pieltsofficial)",
        f"  Followers: {ig_data.get('followers', 'N/A'):,}",
        f"  Avg Likes/Post: {ig_data.get('last_12_posts_avg_likes', 'N/A')}",
        f"  Avg Comments/Post: {ig_data.get('last_12_posts_avg_comments', 'N/A')}",
        f"  Top Post Likes: {ig_data.get('top_post_likes', 'N/A')}",
        "",
        "📘 FACEBOOK (pielts page)",
        f"  Page Likes: {fb_data.get('page_likes', 'N/A'):,}" if isinstance(fb_data.get('page_likes'), int) else f"  Page Likes: {fb_data.get('page_likes', 'N/A')}",
        f"  Followers: {fb_data.get('followers', 'N/A')}",
        "",
        "▶️  YOUTUBE (@pieltsapp)",
        f"  Subscribers: {yt_data.get('subscribers', 'N/A')}",
        f"  Total Views: {yt_data.get('views', 'N/A')}",
        f"  Videos: {yt_data.get('video_count', 'N/A')}",
        "",
        f"📁 Full report → {report_file.name}",
    ]
    summary = "\n".join(lines)

    return {"ok": True, "report": report, "summary": summary}
