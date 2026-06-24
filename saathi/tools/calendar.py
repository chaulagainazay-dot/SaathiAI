from __future__ import annotations
"""Calendar + Reminders via macOS built-in apps (AppleScript).

No cloud OAuth needed — uses the Calendar and Reminders apps already on the Mac.
Reminders fire REAL native notifications at their due time, so "remind me at 5pm"
actually alerts Ajay. Needs Automation permission (already granted).
"""
import subprocess
from datetime import datetime, timedelta


def _osa(script: str, timeout: int = 30) -> tuple[bool, str]:
    p = subprocess.run(["osascript", "-e", script], capture_output=True,
                       text=True, timeout=timeout)
    return p.returncode == 0, (p.stdout or p.stderr).strip()


# ---------- Reminders (these fire native alerts) ----------

def add_reminder(text: str, when: str = "") -> dict:
    """Create a reminder that pops a notification. `when` is natural-ish:
    'today 17:00', '2026-06-12 09:30', 'tomorrow 8am', or empty (no alarm)."""
    due = _parse_when(when)
    if due:
        ds = due.strftime("%-m/%-d/%Y %-I:%M:%S %p")
        script = (f'tell application "Reminders" to make new reminder with properties '
                  f'{{name:"{_esc(text)}", remind me date:date "{ds}"}}')
    else:
        script = (f'tell application "Reminders" to make new reminder with properties '
                  f'{{name:"{_esc(text)}"}}')
    ok, out = _osa(script)
    if not ok:
        return {"ok": False, "error": out}
    return {"ok": True, "reminder": text,
            "alerts_at": due.strftime("%Y-%m-%d %H:%M") if due else "no time set"}


def list_reminders() -> dict:
    """Open (incomplete) reminders."""
    script = ('set out to ""\n'
              'tell application "Reminders"\n'
              ' repeat with r in (reminders whose completed is false)\n'
              '  set out to out & (name of r) & "\\n"\n'
              ' end repeat\n'
              'end tell\n'
              'return out')
    ok, out = _osa(script, timeout=40)
    items = [l.strip() for l in out.splitlines() if l.strip()] if ok else []
    return {"reminders": items, "count": len(items)}


# ---------- Calendar ----------

def todays_events(days: int = 1) -> dict:
    """Events from now through the next `days` days."""
    start = datetime.now()
    end = start + timedelta(days=days)
    s = start.strftime("%-m/%-d/%Y %-I:%M:%S %p")
    e = end.strftime("%-m/%-d/%Y %-I:%M:%S %p")
    script = (
        'set out to ""\n'
        'tell application "Calendar"\n'
        f' set d1 to date "{s}"\n'
        f' set d2 to date "{e}"\n'
        ' repeat with cal in calendars\n'
        '  repeat with ev in (events of cal whose start date ≥ d1 and start date ≤ d2)\n'
        '   set out to out & (summary of ev) & " @ " & (start date of ev as string) & "\\n"\n'
        '  end repeat\n'
        ' end repeat\n'
        'end tell\n'
        'return out')
    ok, out = _osa(script, timeout=45)
    items = [l.strip() for l in out.splitlines() if l.strip()] if ok else []
    return {"events": items, "count": len(items),
            "note": "" if ok else "Calendar read failed: " + out[:120]}


def add_event(title: str, when: str, duration_min: int = 60) -> dict:
    """Add a calendar event to the default calendar."""
    start = _parse_when(when)
    if not start:
        return {"ok": False, "error": f"could not understand time: {when!r}"}
    end = start + timedelta(minutes=duration_min)
    ss = start.strftime("%-m/%-d/%Y %-I:%M:%S %p")
    es = end.strftime("%-m/%-d/%Y %-I:%M:%S %p")
    script = (
        'tell application "Calendar"\n'
        ' tell calendar 1\n'
        f'  make new event with properties {{summary:"{_esc(title)}", '
        f'start date:date "{ss}", end date:date "{es}"}}\n'
        ' end tell\n'
        'end tell')
    ok, out = _osa(script)
    return {"ok": ok, "event": title,
            "at": start.strftime("%Y-%m-%d %H:%M")} if ok else {"ok": False, "error": out}


# ---------- helpers ----------

def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _parse_when(when: str) -> datetime | None:
    if not when.strip():
        return None
    w = when.lower().strip()
    now = datetime.now()
    base = now
    if w.startswith("tomorrow"):
        base = now + timedelta(days=1)
        w = w.replace("tomorrow", "").strip()
    elif w.startswith("today"):
        w = w.replace("today", "").strip()
    # try explicit formats
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %I:%M %p", "%m/%d/%Y %H:%M"):
        try:
            return datetime.strptime(when, fmt)
        except ValueError:
            pass
    # time-only like "5pm", "17:00", "8:30am"
    import re
    m = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", w)
    if m:
        hr = int(m.group(1)); mn = int(m.group(2) or 0); ap = m.group(3)
        if ap == "pm" and hr < 12:
            hr += 12
        if ap == "am" and hr == 12:
            hr = 0
        cand = base.replace(hour=hr, minute=mn, second=0, microsecond=0)
        if cand < now and base.date() == now.date():
            cand += timedelta(days=1)  # time already passed today → tomorrow
        return cand
    return None
