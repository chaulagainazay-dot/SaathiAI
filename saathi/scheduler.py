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
        msg = "\n".join(lines)
        tasks.add("📊 Weekly performance report", kind="note", body=msg)
        try:
            n8n_tools.send_telegram(msg)
        except Exception:
            pass
    except Exception:
        pass


def daily_outreach():
    """9am: find fresh Reddit/Quora IELTS questions + draft ready-to-paste answers, Telegram them.
    Ajay posts manually (Baadar never auto-posts to communities — that gets banned)."""
    try:
        from .tools import content_studio, n8n_tools
        kit = content_studio.community_outreach_kit()
        entries = kit.get("entries", [])
        if not entries:
            return
        from . import tasks
        lines = ["💬 Baadar — Today's community outreach (paste these yourself):", ""]
        for i, e in enumerate(entries, 1):
            lines += [f"━━ {i}. {e.get('question','')}",
                      f"🔗 {e.get('link','')}",
                      "✍️ Ready answer:", e.get("answer", ""), ""]
            # add to the in-app task panel (clickable link + the ready answer)
            tasks.add(f"Answer on Reddit/Quora: {e.get('question','')[:70]}",
                      kind="task", link=e.get("link", ""), body=e.get("answer", ""))
        lines.append("Tip: tweak a few words so it sounds like you, then post. Engage first, link only where it fits.")
        try:
            n8n_tools.send_telegram("\n".join(lines)[:4000])
        except Exception:
            pass
    except Exception as e:
        _notify("💬 Baadar", f"Outreach error: {str(e)[:120]}")


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


JOBS = [
    (7, 0, None, morning_briefing),         # every day 7:00am  — morning briefing
    (7, 30, None, daily_health),            # every day 7:30am  — health watchdog
    (8, 0, None, daily_content),            # every day 8:00am  — video script + blog + calendar check
    (9, 0, None, social_autopost_am),       # every day 9:00am  — AUTO-POST AM slot → FB + IG ✅
    (9, 30, None, daily_outreach),          # every day 9:30am  — Reddit/Quora outreach kit
    (10, 0, 6, weekly_performance),         # Sunday 10:00am    — YouTube performance report
    (10, 30, 6, _weekly_engagement_audit),  # Sunday 10:30am    — engagement audit + bio tip
    (18, 0, None, social_autopost_pm),      # every day 6:00pm  — AUTO-POST PM slot → FB + IG ✅
    (20, 0, None, daily_autopost),          # every day 8:00pm  — AUTO-POST video → YT + FB + IG ✅
    (21, 0, None, canteen_summary),         # every day 9:00pm  — canteen summary
    (23, 30, 6, memory_backup),             # Sunday 11:30pm    — memory backup
    (2, 0, None, memory_reflector),         # every day 2:00am  — memory reflection
    (0, 1, None, _monthly_analytics_job),   # 1st of month 00:01am — analytics review
]


def _run_loop():
    fired: dict = {}  # (job_index) -> date already fired
    while True:
        now = datetime.now()
        for i, (hh, mm, wd, fn) in enumerate(JOBS):
            if now.hour == hh and now.minute == mm:
                if wd is not None and now.isoweekday() % 7 != wd % 7:
                    continue
                key = i
                if fired.get(key) == now.date():
                    continue
                fired[key] = now.date()
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


if __name__ == "__main__":
    print("Running scheduler (Ctrl-C to stop)…")
    start()
    while True:
        time.sleep(3600)
