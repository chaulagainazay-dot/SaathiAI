from __future__ import annotations
"""Daily auto-poster — Baadar posts to YouTube, Facebook, and Instagram automatically.

THREE posting layers:
  1. 9am  — AM text post to Facebook + Instagram (from 30-day content calendar)
  2. 6pm  — PM text post to Facebook + Instagram (from 30-day content calendar)
  3. 8pm  — Video post: YouTube upload + FB/IG image from video thumbnail

Posts use the 30-day content calendar (data/growth/strategy_30day_*.json) as the
source of truth. If no calendar exists, falls back to generating fresh content.
"""
import datetime as dt
import json
import os
from pathlib import Path

import httpx

from . import config

QUEUE = config.ROOT / "data" / "post_queue.json"
GROWTH_DIR = config.ROOT / "data" / "growth"
POST_LOG = config.ROOT / "data" / "autopost_log.json"


# ─────────────────────────────────────────────
# Queue helpers (video queue — unchanged)
# ─────────────────────────────────────────────

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


# ─────────────────────────────────────────────
# Post log — tracks what was already posted today
# ─────────────────────────────────────────────

def _post_log() -> dict:
    try:
        return json.loads(POST_LOG.read_text())
    except Exception:
        return {}


def _mark_posted(slot: str, result: dict):
    log = _post_log()
    today = dt.date.today().isoformat()
    log.setdefault(today, {})[slot] = {
        "posted_at": dt.datetime.now().isoformat(timespec="seconds"),
        **result,
    }
    POST_LOG.parent.mkdir(parents=True, exist_ok=True)
    POST_LOG.write_text(json.dumps(log, indent=2, ensure_ascii=False))


def _already_posted_today(slot: str) -> bool:
    return bool(_post_log().get(dt.date.today().isoformat(), {}).get(slot))


# ─────────────────────────────────────────────
# 30-day calendar helpers
# ─────────────────────────────────────────────

def _load_calendar() -> list:
    """Find the most recent 30-day strategy file and return its posts."""
    GROWTH_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(GROWTH_DIR.glob("strategy_30day_*.json"), reverse=True)
    if not files:
        return []
    data = json.loads(files[0].read_text())
    return data.get("strategy", [])


def _todays_posts(slot: str) -> dict | None:
    """Return today's AM or PM post from the 30-day calendar."""
    posts = _load_calendar()
    if not posts:
        return None
    # Figure out which day number today is relative to the calendar start
    files = sorted(GROWTH_DIR.glob("strategy_30day_*.json"), reverse=True)
    if not files:
        return None
    start_str = json.loads(files[0].read_text()).get("start_date", "")
    try:
        start = dt.date.fromisoformat(start_str)
    except Exception:
        return None
    day_num = (dt.date.today() - start).days + 1
    if day_num < 1 or day_num > 30:
        return None
    match = next(
        (p for p in posts if p.get("day") == day_num and p.get("slot") == slot),
        None
    )
    return match


# ─────────────────────────────────────────────
# Caption builder
# ─────────────────────────────────────────────

def _build_caption(post: dict, platform: str, hashtags: str = "") -> str:
    """Build a full caption from a calendar post entry."""
    hook = post.get("hook", "")
    core = post.get("core_message", "")
    starter = post.get("caption_starter", "")
    cta = post.get("cta", "")
    goal = post.get("goal", "GROW")

    # Goal-based signature
    sig_map = {
        "GROW": "🔁 Share this with someone preparing for IELTS!\nFree practice → pielts.web.app",
        "TRUST": "💙 Save this for when you study.\nFree practice → pielts.web.app",
        "SELL": "🚀 Try pielts.web.app FREE — no signup needed.\nLink in bio 👆",
    }
    sig = sig_map.get(goal, "Free practice → pielts.web.app")

    parts = [hook]
    if starter:
        parts.append(starter)
    elif core:
        parts.append(core)
    parts.append("")
    parts.append(cta)
    parts.append("")
    parts.append(sig)
    if hashtags:
        parts.append(hashtags)

    return "\n".join(parts)


# ─────────────────────────────────────────────
# Fallback content generator (when no calendar)
# ─────────────────────────────────────────────

def _generate_fallback_content(slot: str) -> tuple[str, str]:
    """Generate a fresh FB+IG post on the fly if no calendar exists."""
    try:
        from .tools import content_studio
        kit = content_studio.make_daily_kit()
        fb_text = kit.get("facebook_post", "")
        ig_caption = kit.get("instagram_caption", "") + "\n" + kit.get("hashtags", "")
        # For AM use FB post, PM use IG-optimized caption on both
        if slot == "AM":
            return fb_text, ig_caption
        else:
            return fb_text + "\n\n(Evening reminder!)", ig_caption
    except Exception as e:
        fallback = f"🏔️ IELTS tip from Mr. Yeti!\n\nFree practice at pielts.web.app\n#IELTS #pielts"
        return fallback, fallback


# ─────────────────────────────────────────────
# Mr. Yeti card image generator
# ─────────────────────────────────────────────

def _make_yeti_card(hook: str, slot: str, topic: str = "") -> str | None:
    """Generate a branded Mr. Yeti quote card. Returns local path or None."""
    try:
        from .tools.quote_maker import make_quote_image
        pose_map = {"AM": "teaching", "PM": "pointing", "VIDEO": "thumbsup"}
        pose = pose_map.get(slot, "teaching")
        out_path = config.ROOT / "data" / "autopost_images" / f"post_{dt.date.today().isoformat()}_{slot}.jpg"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        path = make_quote_image(
            quote=hook,
            subtext=topic or "Free practice → pielts.web.app",
            pose=pose,
            size=(1080, 1080),
            slug=f"{dt.date.today().isoformat()}_{slot}",
        )
        return path
    except Exception:
        return None


# ─────────────────────────────────────────────
# Core: social text post (FB + IG) — AM + PM
# ─────────────────────────────────────────────

def run_social_autopost(slot: str = "AM") -> dict:
    """Post the AM or PM slot to Facebook + Instagram + Twitter/X. Called by scheduler at 9am / 6pm."""
    from .scheduler import _notify
    from .tools import meta_post, growth_engine
    from . import connections

    if _already_posted_today(slot):
        return {"status": "already_posted", "slot": slot}

    conns = connections.get_all()
    if not conns.get("facebook", {}).get("connected"):
        return {"status": "facebook_not_connected"}

    # Get today's post from the 30-day calendar
    cal_post = _todays_posts(slot)
    results = {}

    if cal_post:
        topic = cal_post.get("core_message", "") or cal_post.get("hook", "IELTS tips")
        platform_target = cal_post.get("platform", "instagram")

        # Get hashtags from the SEO system
        try:
            seo = growth_engine.hashtag_seo_system(
                topic, platform_target, cal_post.get("goal", "GROW"))
            hashtags = seo.get("hashtags", {}).get("full_set", "")
        except Exception:
            hashtags = "#IELTS #IELTSTips #pielts #StudyAbroad #EnglishLearning"

        fb_caption = _build_caption(cal_post, "facebook", hashtags)
        ig_caption = _build_caption(cal_post, "instagram", hashtags)
    else:
        # No calendar — generate fresh
        fb_caption, ig_caption = _generate_fallback_content(slot)

    # Generate a branded quote image card
    hook_text = (cal_post or {}).get("hook", "IELTS tip from Mr. Yeti!")
    core_msg = (cal_post or {}).get("core_message", "Free practice → pielts.web.app")
    image_path = _make_yeti_card(hook_text, slot, topic=core_msg)

    # Post to Facebook (with image link if available)
    try:
        fb_img = image_path if (image_path and Path(image_path).exists()) else None
        if not fb_img:
            fb_fallback = config.ROOT / "client" / "assets" / "mr_yeti_reference.jpeg"
            if fb_fallback.exists():
                fb_img = str(fb_fallback)
        fb_result = meta_post.post_facebook(fb_caption)
        results["facebook"] = fb_result.get("status", "error")
    except Exception as e:
        results["facebook"] = f"error: {str(e)[:80]}"

    # Post to Instagram (with image if we have one, text-only fallback)
    try:
        if image_path and Path(image_path).exists():
            ig_result = meta_post.post_instagram_image_local(image_path, ig_caption)
        else:
            # Card generation failed — upload Mr. Yeti reference image as fallback
            fallback = config.ROOT / "client" / "assets" / "mr_yeti_reference.jpeg"
            if fallback.exists():
                ig_result = meta_post.post_instagram_image_local(str(fallback), ig_caption)
            else:
                ig_result = {"status": "error", "error": "No image available for Instagram post"}
        results["instagram"] = ig_result.get("status", "error")
    except Exception as e:
        results["instagram"] = f"error: {str(e)[:80]}"

    # ── Auto-publish blog (AM slot only) ────────────────────────────────────
    blog_status = ""
    if slot == "AM":
        try:
            from .tools import content_studio
            blog_topic = (cal_post or {}).get("core_message", "") or hook_text
            blog = content_studio.make_blog_post(blog_topic)
            if blog.get("title") and blog.get("content"):
                pub = content_studio.publish_blog(
                    blog["title"], blog["content"],
                    blog.get("excerpt", ""), blog.get("slug", "")
                )
                blog_status = pub.get("status", "")
        except Exception as e:
            blog_status = f"error: {str(e)[:60]}"

    # ── Post to Twitter/X ───────────────────────────────────────────────────
    if conns.get("x", {}).get("connected"):
        try:
            from .tools import twitter_post
            tweet_text = twitter_post.build_tweet(
                hook=hook_text,
                cta="Free practice → pielts.web.app",
                hashtags="#IELTS #IELTSTips #pielts #StudyAbroad",
            )
            if image_path and Path(image_path).exists():
                tw_result = twitter_post.tweet_with_image(tweet_text, image_path)
            else:
                tw_result = twitter_post.tweet(tweet_text)
            results["twitter"] = tw_result.get("status", "error")
        except Exception as e:
            results["twitter"] = f"error: {str(e)[:60]}"

    # Log + notify
    _mark_posted(slot, {"slot": slot, "topic": hook_text, "results": results, "blog": blog_status})

    status_line = " | ".join(f"{p}: {s}" for p, s in results.items())
    _notify(f"✅ Baadar auto-posted ({slot})", f"{hook_text[:60]}\n{status_line}")

    try:
        from .tools import n8n_tools
        if config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID:
            cal_info = ""
            if cal_post:
                cal_info = (f"\n📅 Day {cal_post.get('day')} {slot} · "
                            f"{cal_post.get('goal','?')} · {cal_post.get('format','?')}")
            n8n_tools.send_telegram(
                f"✅ Auto-posted {slot} slot{cal_info}\n"
                f"Hook: \"{hook_text[:80]}\"\n"
                f"FB: {results.get('facebook','?')} | IG: {results.get('instagram','?')} | X: {results.get('twitter','—')}"
                + (f"\n📝 Blog: {blog_status}" if blog_status else "")
            )
    except Exception:
        pass

    return {"status": "posted", "slot": slot, "results": results, "hook": hook_text, "blog": blog_status}


# ─────────────────────────────────────────────
# Quote fallback — when video queue is empty
# ─────────────────────────────────────────────

def _run_quote_autopost() -> dict:
    """No video queued: generate a quote Short + image and post to YT + FB + IG."""
    from .scheduler import _notify
    from .tools import meta_post, n8n_tools, content_studio
    from .tools.quote_maker import make_full_quote_kit

    _notify("🎨 Baadar", "No video in queue — generating quote Short automatically...")

    # Get today's topic from the calendar if available
    cal_post = _todays_posts("AM") or _todays_posts("PM") or {}
    topic = cal_post.get("core_message") or cal_post.get("hook") or ""
    pose_options = ["teaching", "pointing", "thumbsup", "excited", "thinking"]
    import random
    pose = random.choice(pose_options)

    try:
        kit = make_full_quote_kit(topic=topic, pose=pose)
    except Exception as e:
        return {"status": "error", "error": f"quote kit failed: {str(e)[:120]}"}

    results = {}
    quote = kit.get("quote", "")
    subtext = kit.get("subtext", "Free practice → pielts.web.app")
    yt_title = kit.get("youtube_title", f"IELTS tip: {quote} | Mr. Yeti #Shorts")
    img_square = kit.get("image_square", "")
    video_path = kit.get("video_short", "")

    # ── Instagram: square image + caption ──
    ig_caption = (
        f"{quote}\n\n"
        f"{subtext}\n\n"
        f"💙 Save this for your IELTS prep!\n"
        f"Free practice → pielts.web.app\n\n"
        f"#{kit.get('topic_tag','IELTSTips')} #IELTS #MrYeti #pielts "
        f"#StudyAbroad #IELTSPrep #EnglishLearning #Band7 #IELTSTips"
    )
    try:
        if img_square and Path(img_square).exists():
            ig_r = meta_post.post_instagram_image_local(img_square, ig_caption)
        else:
            fallback = config.ROOT / "client" / "assets" / "mr_yeti_reference.jpeg"
            if fallback.exists():
                ig_r = meta_post.post_instagram_image_local(str(fallback), ig_caption)
            else:
                ig_r = {"status": "error", "error": "No image available"}
        results["instagram"] = ig_r.get("status", "error")
    except Exception as e:
        results["instagram"] = f"error: {str(e)[:60]}"

    # ── Facebook: short quote post + image ──
    fb_caption = (
        f"💡 IELTS tip from Mr. Yeti:\n\n"
        f"\"{quote}\"\n\n"
        f"{subtext}\n\n"
        f"What's your current IELTS band score? Comment below! 👇\n"
        f"Free practice → pielts.web.app"
    )
    try:
        fb_r = meta_post.post_facebook(fb_caption)
        results["facebook"] = fb_r.get("status", "error")
    except Exception as e:
        results["facebook"] = f"error: {str(e)[:60]}"

    # ── YouTube Shorts: 5-second video ──
    if video_path and Path(video_path).exists():
        try:
            from . import connections
            conns = connections.get_all()
            if conns.get("youtube", {}).get("connected"):
                yt_desc = (
                    f"{quote}\n\n"
                    f"{subtext}\n\n"
                    f"🎓 Mr. Yeti is your free IELTS professor from the Himalayas.\n"
                    f"📱 Free practice app: pielts.web.app\n\n"
                    f"#{kit.get('topic_tag','IELTSTips')} #IELTS #Shorts #MrYeti #pielts #IELTSTips #StudyAbroad"
                )
                yt_r = content_studio.publish_to_youtube(
                    video_path, yt_title, yt_desc,
                    tags="IELTS,IELTS tips,Mr Yeti,pielts,Study abroad,English,Shorts"
                )
                yt_status = yt_r.get("status", "error") if isinstance(yt_r, dict) else str(yt_r)
                # Map verbose statuses to human-readable labels
                _yt_labels = {"published": "posted", "not_configured": "needs_oauth", "failed": "failed", "skipped": "skipped(ci)"}
                results["youtube"] = _yt_labels.get(yt_status, yt_status)
        except Exception as e:
            results["youtube"] = f"error: {str(e)[:60]}"
    else:
        results["youtube"] = "skipped"

    # ── Twitter/X: quote tweet ─────────────────────────────────────────────
    try:
        from . import connections as _conns
        from .tools import twitter_post
        if _conns.get_all().get("x", {}).get("connected"):
            tw_text = twitter_post.build_tweet(
                hook=quote,
                cta=subtext or "Free practice → pielts.web.app",
                hashtags=f"#{kit.get('topic_tag','IELTSTips')} #IELTS #pielts #MrYeti",
            )
            if img_square and Path(img_square).exists():
                tw_r = twitter_post.tweet_with_image(tw_text, img_square)
            else:
                tw_r = twitter_post.tweet(tw_text)
            results["twitter"] = tw_r.get("status", "error")
    except Exception as e:
        results["twitter"] = f"error: {str(e)[:60]}"

    # ── Auto-publish blog ──────────────────────────────────────────────────────
    blog_status = ""
    try:
        blog_topic = topic or quote
        blog = content_studio.make_blog_post(blog_topic)
        if blog.get("title") and blog.get("content"):
            pub = content_studio.publish_blog(
                blog["title"], blog["content"],
                blog.get("excerpt", ""), blog.get("slug", "")
            )
            blog_status = pub.get("status", "")
    except Exception as e:
        blog_status = f"error: {str(e)[:60]}"

    # ── Log + notify ──
    _mark_posted("QUOTE", {"quote": quote, "results": results, "blog": blog_status})
    status_line = " | ".join(f"{p}: {s}" for p, s in results.items())
    _notify("✅ Baadar quote Short posted", f'"{quote[:50]}"\n{status_line}')

    try:
        if config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID:
            n8n_tools.send_telegram(
                f"✅ Auto-posted quote Short (no video in queue)\n\n"
                f"💬 \"{quote}\"\n"
                f"📝 {subtext}\n\n"
                f"📸 IG: {results.get('instagram','?')}\n"
                f"📘 FB: {results.get('facebook','?')}\n"
                f"▶️  YT: {results.get('youtube','?')}\n"
                f"📝 Blog: {blog_status or 'error'}\n\n"
                f"→ Add a rendered video to the queue to post tomorrow!"
            )
    except Exception:
        pass

    return {"status": "quote_posted", "quote": quote, "results": results, "blog": blog_status}


# ─────────────────────────────────────────────
# Core: video post (YouTube + FB + IG) — 8pm
# ─────────────────────────────────────────────

def run_daily_autopost() -> dict:
    """Post the next queued video to YouTube + notify FB/IG. Called by the 8pm scheduler."""
    from .scheduler import _notify
    from .tools import content_studio, meta_post
    from . import connections

    q = _load()
    nxt = next((i for i in q if not i.get("posted")), None)
    if not nxt:
        # No video queued → try Google Flow (Veo 2) 3D auto-generation first
        try:
            from .tools.google_flow import generate_full_video
            flow_result = generate_full_video(use_veo=True)
            if flow_result.get("ok") and flow_result.get("video_path"):
                # Inject as a one-off queued item and let the rest of the function post it
                nxt = {
                    "video_path":    flow_result["video_path"],
                    "title":         flow_result["title"],
                    "description":   flow_result.get("caption_fb", ""),
                    "caption":       flow_result.get("caption_ig", ""),
                    "tags":          "IELTS,IELTSTips,MrYeti,pielts,Shorts",
                    "thumbnail_path": "",
                    "auto_generated": True,
                    "method":        flow_result.get("method", "static"),
                }
        except Exception as _gf_err:
            print(f"⚠️  Google Flow failed: {_gf_err} — falling back to quote")
        if not nxt:
            return _run_quote_autopost()


    results = {}
    conns = connections.get_all()

    # YouTube upload
    if conns.get("youtube", {}).get("connected"):
        results["youtube"] = content_studio.publish_to_youtube(
            nxt["video_path"], nxt["title"], nxt.get("description", ""), nxt.get("tags", ""))

    # Post thumbnail/cover as image to Instagram + Facebook (so IG feed stays active)
    thumbnail = nxt.get("thumbnail_path", "")
    caption = (
        f"🎬 New Mr. Yeti video is LIVE on YouTube!\n\n"
        f"{nxt.get('caption') or nxt.get('description') or nxt['title']}\n\n"
        f"▶️ Watch FREE → link in bio\n"
        f"pielts.web.app — free IELTS practice\n\n"
        f"#IELTS #IELTSTips #MrYeti #pielts #StudyAbroad #YouTubeVideo"
    )

    if conns.get("instagram", {}).get("connected"):
        try:
            if thumbnail and Path(thumbnail).exists():
                results["instagram"] = meta_post.post_instagram_image_local(thumbnail, caption).get("status")
            else:
                results["instagram"] = "skipped (no thumbnail)"
        except Exception as e:
            results["instagram"] = f"error: {str(e)[:60]}"

    if conns.get("facebook", {}).get("connected"):
        try:
            yt_res = results.get("youtube", {})
            yt_link = ""
            if isinstance(yt_res, dict):
                try:
                    yt_link = json.loads(yt_res.get("response", "{}")).get("videoId", "")
                    if yt_link:
                        yt_link = f"https://youtu.be/{yt_link}"
                except Exception:
                    pass
            fb_text = caption + (f"\n\n{yt_link}" if yt_link else "")
            results["facebook"] = meta_post.post_facebook(fb_text).get("status")
        except Exception as e:
            results["facebook"] = f"error: {str(e)[:60]}"

    # ── Twitter/X: video announcement tweet ──────────────────────────────────
    if conns.get("x", {}).get("connected"):
        try:
            from .tools import twitter_post
            yt_res = results.get("youtube", {})
            yt_link = ""
            if isinstance(yt_res, dict):
                try:
                    vid_id = json.loads(yt_res.get("response", "{}")).get("videoId", "")
                    if vid_id:
                        yt_link = f"https://youtu.be/{vid_id}"
                except Exception:
                    pass
            tw_text = twitter_post.build_tweet(
                hook=f"🎬 New video: {nxt['title']}",
                cta=yt_link or "pielts.web.app",
                hashtags="#IELTS #IELTSTips #pielts #MrYeti #Shorts",
            )
            results["twitter"] = twitter_post.tweet(tw_text).get("status", "error")
        except Exception as e:
            results["twitter"] = f"error: {str(e)[:60]}"

    nxt["posted"] = True
    nxt["posted_at"] = dt.datetime.now().isoformat(timespec="seconds")
    nxt["result"] = results
    _save(q)

    left = len(pending())
    status_line = " | ".join(f"{p}: {s}" for p, s in results.items())
    _notify("✅ Baadar posted today's video", f"{nxt['title']}\n{status_line}\n{left} left in queue.")

    try:
        from .tools import n8n_tools
        from . import tasks
        yt_r = results.get("youtube", {})
        vid_id = ""
        if isinstance(yt_r, dict):
            try:
                vid_id = json.loads(yt_r.get("response", "{}")).get("uploadId", "")
            except Exception:
                pass
        tasks.add(f"✅ Video posted: {nxt['title']}", kind="note",
                  link=f"https://youtu.be/{vid_id}" if vid_id else "")
        if left <= 2:
            tasks.add(f"⚠️ Video queue low ({left} left) — add more!", kind="task")
        if config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID:
            n8n_tools.send_telegram(
                f"✅ 8pm auto-post complete!\n"
                f"📹 {nxt['title']}\n"
                f"YouTube: {results.get('youtube', {}).get('status', '?') if isinstance(results.get('youtube'), dict) else results.get('youtube','?')}\n"
                f"Instagram: {results.get('instagram','?')}\n"
                f"Facebook: {results.get('facebook','?')}\n"
                f"Queue: {left} videos left"
            )
    except Exception:
        pass

    if left <= 2:
        _notify("⚠️ Queue low", f"Only {left} videos left — add more!")

    return {"status": "posted", "title": nxt["title"], "platforms": results, "left": left}
