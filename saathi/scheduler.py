"""Proactive scheduler — Baadar acts on a clock, not just when spoken to.

Runs lightweight jobs at set local times and delivers results via macOS
notification + Telegram (so they reach Ajay even when he's abroad). This is the
'9pm daily summary' from the HCGMS blueprint, plus a morning briefing and a
weekly memory backup.

Jobs are checked once a minute; each fires at most once per day.
"""
import shutil
import subprocess
import threading
import time
from datetime import datetime

from . import config


def _notify(title: str, message: str):
    """macOS banner + Telegram (best effort)."""
    try:
        subprocess.run(["osascript", "-e",
                        f'display notification "{message[:200]}" with title "{title}"'],
                       timeout=10)
    except Exception:
        pass
    try:
        from .tools import n8n_tools
        if config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID:
            n8n_tools.send_telegram(f"{title}\n{message}")
    except Exception:
        pass


# ---------- job implementations ----------

def morning_briefing():
    from .tools import calendar as cal
    from .agent import SaathiAgent
    events = cal.todays_events(1).get("events", [])
    rem = cal.list_reminders().get("reminders", [])
    ctx = (f"Today's events: {events or 'none'}\nOpen reminders: {rem[:5] or 'none'}")
    try:
        agent = SaathiAgent()
        msg = agent.complete(
            "You are Baadar giving Ajay a short spoken-style morning briefing. "
            "2-3 friendly sentences max, Nepali-English mix ok.",
            f"Good morning. Brief Ajay using this:\n{ctx}", max_tokens=200)
    except Exception:
        msg = f"Good morning Ajay! Events: {events or 'none'}. Reminders: {len(rem)}."
    _notify("☀️ Baadar — Morning Briefing", msg)


def canteen_summary():
    """The blueprint's 9pm daily summary (needs Supabase connected)."""
    from .agent import SaathiAgent
    try:
        from .tools import canteen
        sales = canteen.query("sales_today")
        missing = canteen.query("missing_reports")
        credit = canteen.query("credit_alerts")
        ctx = f"Sales: {sales}\nMissing reports: {missing}\nCredit: {credit}"
    except Exception as e:
        ctx = f"(Canteen data unavailable — connect Supabase. {str(e)[:80]})"
    try:
        agent = SaathiAgent()
        msg = agent.complete(
            "You are Baadar. Give Ajay a concise end-of-day canteen summary: "
            "today's sales vs NPR 30000 target, who missed reports, credit alerts. "
            "3-4 short lines.", ctx, max_tokens=250)
    except Exception:
        msg = ctx
    _notify("🍴 Baadar — Daily Canteen Summary", msg)


def daily_content():
    """8am: Generate today's video script + blog post. FB+IG text posts fire automatically
    at 9am and 6pm via run_social_autopost(). Video posts at 8pm via run_daily_autopost()."""
    try:
        from .tools import content_studio, n8n_tools
        from . import autopost, tasks

        # Check if a 30-day calendar exists; generate one if it's missing or expired
        import json as _json
        from pathlib import Path
        growth_dir = config.ROOT / "data" / "growth"
        growth_dir.mkdir(parents=True, exist_ok=True)
        cal_files = sorted(growth_dir.glob("strategy_30day_*.json"), reverse=True)
        needs_calendar = True
        if cal_files:
            try:
                start_str = _json.loads(cal_files[0].read_text()).get("start_date", "")
                import datetime as _dt
                start = _dt.date.fromisoformat(start_str)
                days_in = (_dt.date.today() - start).days
                if 0 <= days_in < 30:
                    needs_calendar = False
            except Exception:
                pass

        if needs_calendar:
            from .tools.growth_engine import content_strategy_30day
            cal = content_strategy_30day()
            try:
                n8n_tools.send_telegram(
                    f"📅 New 30-day content calendar generated!\n"
                    f"{cal.get('total_posts',60)} posts planned.\n\n"
                    + cal.get("telegram_preview", "")[:3000]
                )
            except Exception:
                pass

        # Generate video script + blog for today
        kit = content_studio.make_daily_kit()
        topic = kit.get("topic", "")

        # Auto-publish blog
        blog_status = ""
        try:
            bf = config.ROOT / "data" / "content" / f"blog-{kit.get('date','')}.json"
            if bf.exists():
                b = _json.loads(bf.read_text())
                pub = content_studio.publish_blog(b["title"], b["content"],
                                                  b.get("excerpt", ""), b.get("slug", ""))
                blog_status = pub.get("status", "")
        except Exception:
            pass

        # Telegram: daily briefing (video script + blog only — FB/IG posting is automatic)
        lines = [
            f"☀️ Baadar — Day starts! ({kit.get('date','')})",
            f"📌 Today's topic: {topic}", "",
            "🎬 VIDEO SCRIPT (Mr Yeti):",
            kit.get("video_script", "")[:600], "",
            f"▶️ YouTube title: {kit.get('youtube_title','')}",
            "→ Render the video and add it to the queue so 8pm auto-post fires.", "",
            f"📝 Blog: {kit.get('blog_title','')}",
            (f"   ✅ Published → pielts.web.app/blog/{kit.get('blog_slug','')}"
             if blog_status == "published"
             else f"   Saved (auto-publish {blog_status or 'off'})"),
            "",
            "📸 FB + IG text posts: AUTO-POSTING at 9am and 6pm today ✅",
            "📹 Video post: AUTO-POSTING at 8pm (if video is in queue) ✅",
        ]
        try:
            n8n_tools.send_telegram("\n".join(lines)[:4000])
        except Exception:
            pass

        tasks.add(f"🎬 Render video: {kit.get('youtube_title','')}", kind="task",
                  body=f"Script:\n{kit.get('video_script','')[:500]}")
        if blog_status == "published":
            tasks.add(f"Blog live: {kit.get('blog_title','')}", kind="note",
                      link=f"https://pielts.web.app/blog/{kit.get('blog_slug','')}")

        _notify("☀️ Baadar — Day started",
                f"Topic: {topic}\nFB+IG auto at 9am+6pm | Video auto at 8pm")
    except Exception as e:
        _notify("📲 Baadar", f"Daily content error: {str(e)[:120]}")


def memory_backup():
    ts = datetime.now().strftime("%Y%m%d")
    dst = config.ROOT / "data" / "backups"
    dst.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copy2(config.DB_PATH, dst / f"saathi-{ts}.db")
        # keep only the last 8 backups
        backups = sorted(dst.glob("saathi-*.db"))
        for old in backups[:-8]:
            old.unlink(missing_ok=True)
    except Exception:
        pass


def social_autopost_am():
    """9am: auto-post the AM slot to Facebook + Instagram from the 30-day calendar."""
    from . import autopost
    autopost.run_social_autopost("AM")


def social_autopost_pm():
    """6pm: auto-post the PM slot to Facebook + Instagram from the 30-day calendar."""
    from . import autopost
    autopost.run_social_autopost("PM")


def daily_autopost():
    """8pm: post the next queued video to YouTube + Facebook + Instagram."""
    from . import autopost
    autopost.run_daily_autopost()


def daily_health():
    """7:30am: self-health watchdog — catch silent failures, alert in-app + Telegram."""
    try:
        from . import health, tasks
        h = health.health_check()
        if h["overall"] == "ok":
            return  # all good, stay quiet
        bad = h["fails"] + h["warns"]
        lines = ["🩺 Baadar health check — needs attention:"]
        for c in bad:
            icon = "🔴" if c["status"] == "fail" else "🟡"
            lines.append(f"{icon} {c['name']}: {c['status']}" + (f" ({c['detail']})" if c["detail"] else ""))
        msg = "\n".join(lines)
        tasks.add("⚠️ Baadar health issue — check systems", kind="task", body=msg)
        try:
            from .tools import n8n_tools
            n8n_tools.send_telegram(msg)
        except Exception:
            pass
        _notify("🩺 Baadar health", f"{len(h['fails'])} failed, {len(h['warns'])} warnings")
    except Exception as e:
        _notify("🩺 Baadar health", f"check error: {str(e)[:100]}")

    # TikTok token expiry alert (Option B: Telegram when expires soon / already expired)
    try:
        from .tools.tiktok_post import token_expiry_days, app_configured
        if app_configured():
            days = token_expiry_days()
            if days == 0:
                msg = ("⚠️ TikTok token has EXPIRED — videos cannot be posted.\n"
                       "Re-auth: http://localhost:8765/api/v1/tiktok/auth")
                try:
                    from .tools import n8n_tools
                    n8n_tools.send_telegram(msg)
                except Exception:
                    pass
                _notify("🔴 TikTok token expired", "Re-auth required")
            elif 0 < days <= 7:
                msg = (f"⚠️ TikTok token expires in {days} day(s).\n"
                       "Re-auth now: http://localhost:8765/api/v1/tiktok/auth")
                try:
                    from .tools import n8n_tools
                    n8n_tools.send_telegram(msg)
                except Exception:
                    pass
    except Exception:
        pass


def nightly_analytics():
    """2:30am nightly: pull analytics → update content weights → send insight to Telegram."""
    try:
        from .tools.analytics_loop import run_analytics_loop
        result = run_analytics_loop()
        if result.get("ok") and result.get("videos_analyzed", 0) > 0:
            insight = result.get("insight", "")
            top = result.get("top_performers", [])
            msg = (
                f"📊 Analytics Loop\n"
                f"Videos analysed: {result['videos_analyzed']}\n"
                f"💡 {insight}\n"
            )
            if top:
                msg += "🏆 Top: " + " | ".join(v["title"][:40] for v in top[:3])
            try:
                from .tools import n8n_tools
                n8n_tools.send_telegram(msg)
            except Exception:
                pass
    except Exception as e:
        _notify("📊 Analytics", f"error: {str(e)[:100]}")


def nightly_comment_miner():
    """3:00am nightly: mine YouTube comments → generate video ideas."""
    try:
        from .tools.comment_miner import run_comment_miner
        result = run_comment_miner()
        if result.get("ideas_generated", 0) > 0:
            top = result.get("top_ideas", [])
            msg = (
                f"💬 Comment Miner\n"
                f"Comments read: {result['comments_read']} → "
                f"{result['ideas_generated']} video ideas\n"
            )
            if top:
                msg += "Top ideas:\n" + "\n".join(f"• {i.get('video_title','')}" for i in top[:3])
            try:
                from .tools import n8n_tools
                n8n_tools.send_telegram(msg)
            except Exception:
                pass
    except Exception as e:
        pass


def daily_trend_hunt():
    """5:00am daily: scan Reddit + YouTube trends → save to trending_topics.json for Flow 1."""
    try:
        from .tools.trend_hunter import run_trend_hunter
        result = run_trend_hunter()
        if result.get("topics_generated", 0) > 0:
            top = result.get("top_topics", [])
            msg = (
                f"🔥 Trend Hunter\n"
                f"Reddit: {result['reddit_posts']} posts | YT: {result['yt_videos']} videos\n"
                f"→ {result['topics_generated']} trending Mr. Yeti topics generated\n"
            )
            if top:
                msg += "\n".join(f"• {t.get('video_title','')}" for t in top[:3])
            try:
                from .tools import n8n_tools
                n8n_tools.send_telegram(msg)
            except Exception:
                pass
    except Exception as e:
        pass


def memory_reflector():
    """2am nightly: Suna-style memory reflector — reads recent activity + feedback,
    updates saathi/memory/ files so every session starts with current context."""
    from pathlib import Path
    import json as _json

    memory_dir = Path(__file__).parent / "memory"
    memory_dir.mkdir(exist_ok=True)
    integrations_file = memory_dir / "integrations.md"

    try:
        from .agent import SaathiAgent
        from . import selfimprove

        # Read recent feedback entries (last 20)
        recent_feedback = []
        try:
            import sqlite3
            conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
            rows = conn.execute(
                "SELECT kind, detail FROM feedback ORDER BY ts DESC LIMIT 20"
            ).fetchall()
            conn.close()
            recent_feedback = [f"{r[0]}: {r[1][:200]}" for r in rows if r[1]]
        except Exception:
            pass

        if not recent_feedback:
            return  # nothing to reflect on

        # Ask the LLM to produce memory update notes
        agent = SaathiAgent()
        prompt = (
            "You are Baadar's memory reflector. Review this feedback log and produce "
            "a brief update (3-5 bullet points) for the conventions.md memory file. "
            "Focus on NEW patterns, mistakes to avoid, or preferences Ajay expressed. "
            "Output ONLY the bullet points — no preamble, no explanation.\n\n"
            "Recent feedback:\n" + "\n".join(recent_feedback)
        )
        notes = agent.complete(
            "You are a memory reflector. Output only brief bullet-point updates.",
            prompt, max_tokens=300)

        if not notes or len(notes) < 20:
            return

        # Append new learnings to conventions.md under a dated section
        conv_file = memory_dir / "conventions.md"
        if conv_file.exists():
            ts = datetime.now().strftime("%Y-%m-%d")
            existing = conv_file.read_text(encoding="utf-8")
            # Only append if this date isn't already there
            if ts not in existing:
                with open(conv_file, "a", encoding="utf-8") as f:
                    f.write(f"\n\n## Auto-learned {ts}\n{notes}\n")
    except Exception:
        pass  # memory reflector must never crash the scheduler


def disaster_recovery_backup():
    """Sunday 2:05am: full disaster-recovery backup — Firebase + MailerLite.

    Runs the two scripts in ~/SaathiAI/scripts/ and sends a combined
    Telegram report so Ajay always has an off-site summary even when abroad.
    Safe to run weekly; each script keeps only the last 8 snapshots.
    """
    from pathlib import Path
    import subprocess

    scripts_dir = config.ROOT / "scripts"
    results: list[str] = []
    had_error = False

    for script in ("backup_firebase.py", "backup_mailerlite.py"):
        script_path = scripts_dir / script
        if not script_path.exists():
            results.append(f"⚠️ {script}: not found at {script_path}")
            had_error = True
            continue
        try:
            proc = subprocess.run(
                [__import__("sys").executable, str(script_path)],
                capture_output=True, text=True, timeout=300
            )
            output = (proc.stdout or "").strip()
            stderr = (proc.stderr or "").strip()
            if proc.returncode != 0:
                had_error = True
                results.append(
                    f"🔴 {script} failed (exit {proc.returncode})\n"
                    + (stderr or output)[:400]
                )
            else:
                # First non-empty line is the script's own summary line
                first_line = next((l for l in output.splitlines() if l.strip()), script)
                results.append(first_line)
        except subprocess.TimeoutExpired:
            had_error = True
            results.append(f"🔴 {script}: timed out after 300s")
        except Exception as e:
            had_error = True
            results.append(f"🔴 {script}: {e}")

    header = "🗄️ Baadar — Sunday Disaster-Recovery Backup"
    body   = "\n".join(results)
    _notify(header, body[:200])
    try:
        from .tools import n8n_tools
        n8n_tools.send_telegram(f"{header}\n\n{body}"[:4000])
    except Exception:
        pass


def weekly_performance():
    """Sunday 10am: what's working on YouTube → feed insight back."""
    try:
        from . import analytics, tasks
        from .tools import n8n_tools
        rep = analytics.performance_report()
        if "error" in rep:
            return
        top = rep.get("top", [])
        ch = rep.get("channel", {})
        lines = [f"📊 Baadar weekly performance — {ch.get('subscribers','?')} subs, {ch.get('views','?')} views",
                 "Top videos:"]
        for v in top[:5]:
            lines.append(f"  {v['views']} views · {v['title'][:50]}")
        lines.append("→ Make more like the top performers; drop formats that flop.")

        # ── Analytics feedback loop: write top-performing topics to guide next week ──
        try:
            import json
            from pathlib import Path
            from . import config as _cfg
            feedback_file = _cfg.ROOT / "data" / "content_feedback.json"
            top_topics = [v["title"][:80] for v in top[:5]]
            existing = json.loads(feedback_file.read_text()) if feedback_file.exists() else {}
            existing["top_topics_last_week"] = top_topics
            existing["updated"] = __import__("datetime").datetime.now().isoformat()
            feedback_file.write_text(json.dumps(existing, indent=2))
            lines.append(f"\n📌 Top topics saved → content_feedback.json (used in next week's Mr. Yeti videos)")
        except Exception:
            pass

        msg = "\n".join(lines)
        tasks.add("📊 Weekly performance report", kind="note", body=msg)
        try:
            n8n_tools.send_telegram(msg)
        except Exception:
            pass
    except Exception:
        pass


def daily_outreach():
    """9:30am: draft today's Reddit post + LinkedIn post + find reply opportunities."""
    try:
        from .tools import content_studio, n8n_tools
        from .tools.reddit_outreach import queue_daily_post, scan_and_draft
        from .tools.linkedin_post import queue_daily_post as li_queue
        from .autopost import _todays_posts

        # ── 1. Draft today's Reddit submission from content calendar ─────────
        cal_post = _todays_posts("AM") or _todays_posts("PM") or {}
        result = queue_daily_post(cal_post)
        draft = result.get("draft", {})

        # ── 2. Draft today's LinkedIn post ────────────────────────────────────
        try:
            li_result = li_queue(cal_post)
            li_draft = li_result.get("draft", {})
        except Exception as li_err:
            li_draft = {}
            print(f"LinkedIn queue error: {li_err}")

        # ── 3. Scan for reply opportunities (background, non-blocking) ───────
        import threading
        threading.Thread(target=scan_and_draft, kwargs={"max_new": 5}, daemon=True).start()

        # ── 4. Telegram notification ─────────────────────────────────────────
        lines = ["📮 Baadar — Today's Content Queue", ""]
        if draft:
            lines += [
                "🔴 Reddit:",
                f"📌 r/{draft.get('subreddit','IELTS')}",
                f"Title: {draft.get('title','')}",
                draft.get("body", "")[:300],
                "",
            ]
        if li_draft:
            lines += [
                "💼 LinkedIn:",
                li_draft.get("text", "")[:300],
                "",
            ]
        lines.append("👆 Open Baadar → Settings to post")
        if not draft and not li_draft:
            lines.append("Already queued for today.")

        try:
            n8n_tools.send_telegram("\n".join(lines)[:4000])
        except Exception:
            pass

    except Exception as e:
        _notify("💬 Baadar", f"Outreach error: {str(e)[:120]}")


def daily_mr_yeti_video():
    """8:00am: Generate master video → extract clips → queue for 4 daily slots."""
    try:
        from .tools.mr_yeti_pipeline import run_pipeline
        run_pipeline()
    except Exception as e:
        _notify("🎬 Mr. Yeti", f"Pipeline error: {str(e)[:120]}")


def ceo_dashboard_job():
    """8:00am NPT (2:15am UTC): Send CEO morning dashboard to Telegram."""
    try:
        from .tools.intelligence import send_ceo_dashboard
        send_ceo_dashboard()
    except Exception as e:
        _notify("📊 CEO Dashboard", f"Error: {str(e)[:120]}")
    # Platform CEO briefing (Mission Control) — learning/knowledge/publishing/storage
    # aggregated from the Event Fabric. Guarded; never breaks the existing dashboard.
    try:
        from .ceo_dashboard import send_morning_briefing
        send_morning_briefing()
    except Exception:
        pass


def mr_yeti_7am():
    """7:00am: Post 2 Shorts → YouTube Shorts + TikTok."""
    try:
        from .tools.mr_yeti_pipeline import post_slot
        post_slot("7am")
    except Exception as e:
        _notify("📲 Mr. Yeti 7am", f"Post error: {str(e)[:120]}")


def mr_yeti_12pm():
    """12:00pm: Post 2 Shorts → YouTube Shorts + Instagram."""
    try:
        from .tools.mr_yeti_pipeline import post_slot
        post_slot("12pm")
    except Exception as e:
        _notify("📲 Mr. Yeti 12pm", f"Post error: {str(e)[:120]}")


def mr_yeti_5pm():
    """5:00pm: Post 2 Shorts → TikTok + Instagram."""
    try:
        from .tools.mr_yeti_pipeline import post_slot
        post_slot("5pm")
    except Exception as e:
        _notify("📲 Mr. Yeti 5pm", f"Post error: {str(e)[:120]}")


def mr_yeti_8pm():
    """8:00pm: Post long video → YouTube + Reel → Facebook."""
    try:
        from .tools.mr_yeti_pipeline import post_slot
        post_slot("8pm")
    except Exception as e:
        _notify("🌙 Mr. Yeti 8pm", f"Post error: {str(e)[:120]}")


def daily_linkedin_post():
    """10:00am: Auto-post today's LinkedIn draft via API (hands-free)."""
    try:
        from .tools.linkedin_post import get_pending, post_and_mark
        from .tools import n8n_tools
        pending = get_pending()
        if not pending:
            return
        p = pending[0]
        result = post_and_mark(p["date"], p["text"])
        if result.get("ok"):
            msg = f"💼 LinkedIn posted!\n{p['text'][:200]}…\n{result.get('post_url','')}"
        else:
            msg = f"💼 LinkedIn post failed: {result.get('error','unknown')}"
        try:
            n8n_tools.send_telegram(msg)
        except Exception:
            pass
    except Exception as e:
        _notify("💼 LinkedIn", f"Auto-post error: {str(e)[:120]}")


def auto_reddit_post():
    """10:05am: Auto-submit today's Reddit post via Brave browser JS (hands-free)."""
    try:
        from .tools.reddit_outreach import get_pending_daily_posts, mark_daily_post_sent
        from .tools import n8n_tools
        import subprocess

        pending = get_pending_daily_posts()
        if not pending:
            return
        p = pending[0]

        title   = p["title"].replace("\\", "\\\\").replace('"', '\\"')
        body    = p.get("body", "").replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
        subreddit = p["subreddit"]

        script = f'''tell application "Brave Browser"
    activate
    set newTab to make new tab at end of tabs of window 1
    set URL of newTab to "https://www.reddit.com"
    delay 4
    execute newTab javascript "(async()=>{{const r=await fetch('/api/me.json',{{credentials:'include'}});const d=await r.json();const uh=d?.data?.modhash;if(!uh){{window.__rdErr='no_modhash';return;}}const fd=new FormData();fd.append('api_type','json');fd.append('kind','self');fd.append('sr','{subreddit}');fd.append('title',\\"{title}\\");fd.append('text',\\"{body}\\");fd.append('uh',uh);const sr=await fetch('/api/submit',{{method:'POST',credentials:'include',body:fd}});const sd=await sr.json();window.__rdAutoResult=sd;}})();"
    delay 5
    set res to execute newTab javascript "JSON.stringify(window.__rdAutoResult||window.__rdErr||'pending')"
    close newTab
    return res
end tell'''

        r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=40)

        # AppleScript errors (e.g. JS disabled in Brave) come through stderr
        if r.returncode != 0 or "execution error" in r.stderr:
            err = r.stderr.strip()[:200] or r.stdout.strip()[:200]
            print(f"  ❌ Reddit AppleScript failed: {err}")
            # DON'T mark as sent — leave pending so it can be retried
            _notify("🔴 Reddit", f"Auto-post FAILED (enable JS in Brave → View → Developer): {err[:80]}")
            try:
                n8n_tools.send_telegram(
                    f"❌ Reddit post FAILED\n"
                    f"Reason: {err[:150]}\n"
                    f"Fix: Brave → View → Developer → Allow JavaScript from Apple Events ✓"
                )
            except Exception:
                pass
            return

        output = r.stdout.strip()
        # Check for Reddit API error in JS result
        if "no_modhash" in output or '"errors"' in output:
            print(f"  ❌ Reddit JS error: {output[:200]}")
            _notify("🔴 Reddit", f"Post failed — not logged in or Reddit blocked: {output[:80]}")
            try:
                n8n_tools.send_telegram(f"❌ Reddit post blocked\nResult: {output[:200]}")
            except Exception:
                pass
            return

        # Only mark sent if everything looks good
        import json as _json
        post_url = ""
        try:
            data = _json.loads(output)
            post_url = (data.get("json", {}).get("data", {}) or {}).get("url", "")
        except Exception:
            pass

        mark_daily_post_sent(p["date"], post_url)
        try:
            n8n_tools.send_telegram(
                f"✅ Reddit posted!\nr/{subreddit}: {p['title']}\n"
                + (f"🔗 {post_url}" if post_url else output[:200])
            )
        except Exception:
            pass
    except Exception as e:
        _notify("🔴 Reddit", f"Auto-post error: {str(e)[:120]}")


# ---------- schedule table: (HH, MM, weekday_or_None, fn) ----------
def _monthly_analytics_job():
    """Run on the 1st of each month — pull all platform analytics and send to Telegram."""
    if datetime.now().day != 1:
        return
    try:
        from .tools.growth_engine import monthly_analytics_review
        result = monthly_analytics_review()
        summary = result.get("summary", "Analytics unavailable")
        _notify("📊 Baadar Monthly Review", summary[:200])
        from .tools import n8n_tools
        if config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID:
            n8n_tools.send_telegram(summary[:4000])
    except Exception as e:
        _notify("📊 Analytics Error", str(e)[:120])


def _weekly_engagement_audit():
    """Every Sunday — send engagement tips and profile optimisation reminder."""
    try:
        from .tools.growth_engine import profile_optimizer
        ig_bio = profile_optimizer("instagram")
        msg = (
            "📈 WEEKLY GROWTH CHECK\n\n"
            "🔥 Optimized Instagram Bio:\n"
            f"{ig_bio.get('optimized_bio', 'Run profile_optimizer in Baadar.')}\n\n"
            "💡 Why it works: " + ig_bio.get("why_it_works", "") +
            "\n\nTip: Use engagement_booster on your lowest-performing post this week."
        )
        from .tools import n8n_tools
        if config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID:
            n8n_tools.send_telegram(msg[:4000])
    except Exception as e:
        _notify("📈 Engagement Audit", f"Error: {str(e)[:100]}")


def ab_result_check():
    """4:00am daily: find A/B tests from 48h ago, pull analytics, close the loop."""
    try:
        from .tools.ab_tester import _load_log, record_result, _save_log
        from .tools.analytics_loop import pull_youtube_analytics
        import json
        from datetime import datetime, timedelta

        log = _load_log()
        now = datetime.now()
        closed = 0

        for entry in log:
            if entry.get("winner"):
                continue  # already resolved
            try:
                test_date = datetime.strptime(entry["date"], "%Y-%m-%d")
            except Exception:
                continue
            age_hours = (now - test_date).total_seconds() / 3600
            if age_hours < 48:
                continue  # too early

            # Attempt to pull real views; fall back to 0/0 so the loop still closes
            try:
                videos = pull_youtube_analytics(days_back=3)
                title_a = (entry.get("variant_a") or {}).get("title", {})
                title_b = (entry.get("variant_b") or {}).get("title", {})
                title_a_text = title_a.get("text", "") if isinstance(title_a, dict) else str(title_a)
                title_b_text = title_b.get("text", "") if isinstance(title_b, dict) else str(title_b)
                views_a = next((v.get("views", 0) for v in videos if title_a_text and title_a_text[:20] in v.get("title", "")), 0)
                views_b = next((v.get("views", 0) for v in videos if title_b_text and title_b_text[:20] in v.get("title", "")), 0)
            except Exception:
                views_a, views_b = 0, 0

            record_result(entry["test_id"], views_a, views_b)
            closed += 1

        if closed:
            try:
                from .tools.n8n_tools import send_telegram
                send_telegram(f"🧪 A/B loop closed {closed} test(s) — winning patterns updated.")
            except Exception:
                pass
    except Exception:
        pass


def referral_score_check():
    """6-hour job: Poll Firebase RTDB for users with band score improvements."""
    try:
        from .tools.referral import poll_score_improvements
        poll_score_improvements()
    except Exception:
        pass


def nightly_storage_cleanup():
    """Nightly Storage Intelligence cleanup pass (SES-019A Part 9)."""
    try:
        from .storage.service import get_storage_service
        get_storage_service().cleanup.nightly()
    except Exception:
        pass  # cleanup must never crash the scheduler


JOBS = [
    (3, 0, None, nightly_storage_cleanup),  # every day 3:00am  — Storage Intelligence cleanup ✅
    (7, 0, None, morning_briefing),         # every day 7:00am  — morning briefing
    (7, 0, None, mr_yeti_7am),              # every day 7:00am  — 2 Shorts → YT Shorts + TikTok ✅
    (7, 30, None, daily_health),            # every day 7:30am  — health watchdog
    (8, 0, None, daily_mr_yeti_video),      # every day 8:00am  — generate master video → extract clips ✅
    (2, 15, None, ceo_dashboard_job),       # every day 2:15am (UTC) = 8:00am NPT — CEO morning dashboard ✅
    (12, 0, None, mr_yeti_12pm),            # every day 12:00pm — 2 Shorts → YT Shorts + Instagram ✅
    (17, 0, None, mr_yeti_5pm),             # every day 5:00pm  — 2 Shorts → TikTok + Instagram ✅
    (20, 0, None, mr_yeti_8pm),             # every day 8:00pm  — long video → YouTube + Reel → Facebook ✅
    (8, 15, None, daily_content),           # every day 8:15am  — video script + blog + calendar check
    (9, 0, None, social_autopost_am),       # every day 9:00am  — AUTO-POST AM slot → FB + IG ✅
    (9, 30, None, daily_outreach),          # every day 9:30am  — Reddit/Quora outreach kit
    (10, 0, None, daily_linkedin_post),     # every day 10:00am — LinkedIn auto-post ✅
    (10, 5, None, auto_reddit_post),        # every day 10:05am — Reddit auto-post ✅
    (10, 0, 6, weekly_performance),         # Sunday 10:00am    — YouTube performance report
    (10, 30, 6, _weekly_engagement_audit),  # Sunday 10:30am    — engagement audit + bio tip
    (18, 0, None, social_autopost_pm),      # every day 6:00pm  — AUTO-POST PM slot → FB + IG ✅
    # 8:00pm Mr. Yeti slot (mr_yeti_8pm above) handles video posting — daily_autopost removed
    (21, 0, None, canteen_summary),         # every day 9:00pm  — canteen summary
    (23, 30, 6, memory_backup),             # Sunday 11:30pm    — memory backup
    (2, 0, None, memory_reflector),         # every day 2:00am  — memory reflection
    (2, 5, 6, disaster_recovery_backup),   # Sunday  2:05am    — Firebase + MailerLite DR backup ✅
    (2, 30, None, nightly_analytics),       # every day 2:30am  — analytics loop → update content weights ✅
    (3, 0, None, nightly_comment_miner),    # every day 3:00am  — mine YouTube comments → video ideas ✅
    (5, 0, None, daily_trend_hunt),         # every day 5:00am  — Reddit + YT trends → topic feed ✅
    (4, 0, None, ab_result_check),          # every day 4:00am  — close A/B loops from 48h ago ✅
    (0, 1, None, _monthly_analytics_job),   # 1st of month 00:01am — analytics review
    (0,  0, None, referral_score_check),    # 00:00 — poll Firebase RTDB for band score improvements
    (6,  0, None, referral_score_check),    # 06:00 — poll Firebase RTDB (every 6h)
    (12, 0, None, referral_score_check),    # 12:00 — poll Firebase RTDB (every 6h)
    (18, 0, None, referral_score_check),    # 18:00 — poll Firebase RTDB (every 6h)
]


def _run_loop():
    fired: dict = {}  # job_index -> date already fired
    CATCHUP_WINDOW_MINS = 10  # fire missed jobs up to 10 min late (handles restarts)
    while True:
        now = datetime.now()
        now_mins = now.hour * 60 + now.minute
        for i, (hh, mm, wd, fn) in enumerate(JOBS):
            job_mins = hh * 60 + mm
            # Fire if within the catchup window and not already fired today
            if 0 <= now_mins - job_mins <= CATCHUP_WINDOW_MINS:
                if wd is not None and now.isoweekday() % 7 != wd % 7:
                    continue
                if fired.get(i) == now.date():
                    continue
                fired[i] = now.date()
                threading.Thread(target=fn, daemon=True).start()
        time.sleep(30)


def start():
    """Launch the scheduler in a background thread."""
    threading.Thread(target=_run_loop, daemon=True).start()
    # two-way Telegram: let Ajay command Baadar from his phone (anywhere)
    try:
        from . import telegram_bot
        telegram_bot.start()
    except Exception:
        pass
    # Storage Intelligence: 1-minute disk watchdog + event-first Mission Control
    # + Telegram alerts. Emergency cleanup fires automatically at 95%.
    try:
        from .storage.service import get_storage_service
        svc = get_storage_service(enable_telegram=True)
        svc.start(interval_seconds=60)
    except Exception:
        pass  # storage monitoring must never block server startup


if __name__ == "__main__":
    print("Running scheduler (Ctrl-C to stop)…")
    start()
    while True:
        time.sleep(3600)

