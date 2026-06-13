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
    """AUTOPILOT (approve-to-post mode): every morning Baadar drafts the day's Mr Yeti video
    pack — Google Flow scene prompts + caption + hashtags — and Telegrams it to Ajay so he can
    generate the clips and approve posting. Baadar NEVER posts publicly or spends money on its
    own; FB/LinkedIn publishing happens only after Ajay replies 'post it'."""
    try:
        from .tools import content_studio, n8n_tools
        pack = content_studio.make_flow_prompts()
        scenes = pack.get("scenes", [])
        if not scenes:
            _notify("📲 Baadar", "Couldn't draft today's video — say 'make flow prompts'.")
            return
        lines = ["🏔️ Baadar — Today's Mr Yeti video", "",
                 f"📌 Topic: {pack.get('topic', '')}",
                 f"▶️ YouTube title: {pack.get('youtube_title', '')}", "",
                 "🎬 Google Flow scene prompts (paste each with the Mr Yeti character):"]
        for i, s in enumerate(scenes, 1):
            lines.append(f"{i}. {s}")
        lines += ["", f"📝 Caption: {pack.get('caption', '')}",
                  f"#️⃣ {pack.get('hashtags', '')}", "",
                  "→ Generate the 7 clips in Flow, stitch + caption in CapCut, post to "
                  "@pieltsapp/YouTube. Reply 'post it' and I'll publish the caption to "
                  "Facebook & LinkedIn for you."]
        try:
            n8n_tools.send_telegram("\n".join(lines)[:4000])
        except Exception:
            pass
        _notify("📲 Baadar — Today's Mr Yeti video ready",
                f"Topic: {pack.get('topic', '')}. Flow prompts sent to your Telegram.")
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


# ---------- schedule table: (HH, MM, weekday_or_None, fn) ----------
JOBS = [
    (7, 0, None, morning_briefing),    # every day 7:00am
    (8, 0, None, daily_content),       # every day 8:00am — draft social content
    (21, 0, None, canteen_summary),    # every day 9:00pm
    (23, 30, 6, memory_backup),        # Sunday 11:30pm (weekday 6 = Sunday)
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


if __name__ == "__main__":
    print("Running scheduler (Ctrl-C to stop)…")
    start()
    while True:
        time.sleep(3600)
