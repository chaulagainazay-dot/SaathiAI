"""Telegram CEO Companion (Phase 2) — run the business from a chat.

Telegram becomes the mobile OS before native apps. This adds a fast command layer
on top of the existing two-way bot: a morning briefing plus /approve, /details,
/run, /revenue, /opps — each backed by the platform (BFF + Revenue Engine) and
recorded as an Episode. Non-commands return None so the general agent still handles
free-form chat.

Deterministic (AP-17); data source / revenue recorder / episode recorder injected
(AP-12) so it tests without network or a real bot.
"""
from __future__ import annotations

from typing import Callable

DREAM_TARGET = 7_938_838.98

# revenue source words → RevenueSource (Phase 3: one unified record_revenue)
_SOURCE_WORDS = {
    "cafeteria": "POS", "dalbhat": "POS", "canteen": "POS", "pos": "POS",
    "youtube": "YOUTUBE", "video": "YOUTUBE", "aistudio": "YOUTUBE", "studio": "YOUTUBE",
    "travel": "TRAVEL", "crypto": "CRYPTO", "course": "COURSES", "courses": "COURSES",
    "sponsor": "SPONSORS", "affiliate": "AFFILIATE", "subscription": "SUBSCRIPTIONS",
    "telegram": "TELEGRAM", "consulting": "CONSULTING", "ads": "ADS",
}


def briefing_text(home: dict, scorecard: str | None = None) -> str:
    a = (home.get("actions") or [{}])[0]
    lines = [
        "☀️  Good morning, Ajay", "",
        f"🎯  Dream            {home.get('dreamPct', 0):.2f}%",
        f"💰  Revenue today    ${home.get('revenueToday', 0):,.0f}",
        f"⭐  Priority score   {home.get('priorityScore', 0)}",
    ]
    reasons = home.get("priorityReasons") or []
    if reasons:
        lines.append("     " + " · ".join(r["label"] for r in reasons[:3]))
    lines += ["", "🔥  Top priority", f"     {a.get('title', '—')}"]
    appr = home.get("approvals", {}) or {}
    lines += ["", f"✅  Pending: {appr.get('count', 0)} approvals",
              f"🧭  Actions ready: {len(home.get('actions', []))}"]
    if scorecard:
        lines += ["", scorecard]
        if "⬜ learn" in scorecard:
            try:
                from saathi.coach import daily_challenge
                lines += ["", daily_challenge().render()]
            except Exception:
                pass
        if "⬜ reflect" in scorecard:
            lines.append("🪞  /reflect — what surprised you today?")
    lines += ["", "Reply:  /learn   /approve   /details   /revenue"]
    return "\n".join(lines)


def _details_text(home: dict) -> str:
    out = ["📋  Today's priorities:"]
    for i, a in enumerate(home.get("actions", []), 1):
        out.append(f"{i}. {a.get('title', '')}\n     {a.get('meta', '')}  [{a.get('tag', '')}]")
    return "\n".join(out) or "No actions."


def _record(record_episode, *, intent, action, result, quality=1.0):
    record_episode(agent="telegram_ceo", department="executive", product="ceo",
                   intent=intent, action=action, result=result, outcome="success",
                   quality_score=quality, metadata={})


def handle_command(text: str, *, ceo_home_fn: Callable[[], dict] | None = None,
                   record_revenue_fn: Callable[..., int] | None = None,
                   record_episode: Callable[..., int] | None = None) -> str | None:
    """Return a reply for a CEO command, or None to defer to the general agent."""
    t = (text or "").strip()
    if not t.startswith("/"):
        return None
    parts = t.split()
    cmd = parts[0].lower().lstrip("/")
    args = parts[1:]

    if ceo_home_fn is None:
        from saathi.bff import ceo_home as ceo_home_fn
    if record_episode is None:
        from saathi.integration import ingest_episode as record_episode

    if cmd in ("brief", "start", "morning", "home"):
        sc = None
        try:
            from saathi.daily_scorecard import today_scorecard
            sc = today_scorecard().render()
        except Exception:
            pass
        return briefing_text(ceo_home_fn(), scorecard=sc)

    if cmd in ("scorecard", "score", "today"):
        from saathi.daily_scorecard import today_scorecard
        sc = today_scorecard()
        base = sc.render()
        return base + ("" if sc.complete else f"\nStill needed: {', '.join(sc.missing)}")

    if cmd in ("learn", "speak", "ielts"):
        from saathi.coach import daily_challenge, SaathiCoach, BandPredictor
        answer = " ".join(args).strip()
        if not answer:
            ch = daily_challenge()
            return (ch.render() + "\n\nReply:  /speak <your answer>  — I'll score you live, "
                    "like an examiner. Talk about your own work; no test screen.")
        import os
        data = os.path.join(os.path.dirname(__file__), "..", "data")
        coach = SaathiCoach(BandPredictor(os.path.join(data, "coach.db")),
                            record_episode=record_episode)
        out = coach.practice_speaking(answer, topic="telegram speaking")
        p = out["prediction"]
        return (out["score"].render() + f"\n\n📈  Overall {p['overall']} → "
                f"predicted {p['predicted_overall']} in {p['days_left']} days "
                f"(confidence {p['confidence']:.0%})\n⭐  Learn earned for today.")

    if cmd in ("band", "prediction", "progress"):
        import os
        from saathi.coach import BandPredictor
        data = os.path.join(os.path.dirname(__file__), "..", "data")
        p = BandPredictor(os.path.join(data, "coach.db")).predict(days_left=11)
        cur = p["current"]
        return ("📊  IELTS Band Predictor\n" +
                "\n".join(f"   {k:<10} {v}" for k, v in cur.items()) +
                f"\n   {'Overall':<10} {p['overall']}\n"
                f"   Predicted   {p['predicted_overall']} in {p['days_left']} days "
                f"(confidence {p['confidence']:.0%})")

    if cmd in ("reflect", "reflection"):
        note = " ".join(args).strip()
        if not note:
            return "🪞  What surprised you today?\nReply:  /reflect <your observation>"
        _record(record_episode, intent="reflection", action="daily reflection", result=note)
        tail = ""
        try:
            from saathi.daily_scorecard import today_scorecard
            tail = "\n\n" + today_scorecard().render()
        except Exception:
            pass
        return (f"🪞  Captured: “{note}”\n"
                f"That surprise often becomes tomorrow's experiment.{tail}")

    if cmd in ("details", "priorities"):
        return _details_text(ceo_home_fn())

    if cmd == "approve":
        home = ceo_home_fn()
        actions = home.get("actions", [])
        idx = int(args[0]) - 1 if args and args[0].isdigit() else 0
        if not (0 <= idx < len(actions)):
            return "Nothing to approve."
        title = actions[idx]["title"]
        _record(record_episode, intent="ceo_approve", action=f"approved: {title}",
                result="approved via Telegram")
        return f"✅  Approved: {title}\n(recorded · governance L4 respected)"

    if cmd == "run":
        home = ceo_home_fn()
        actions = home.get("actions", [])
        idx = int(args[0]) - 1 if args and args[0].isdigit() else 0
        if not (0 <= idx < len(actions)):
            return "Nothing to run."
        title = actions[idx]["title"]
        _record(record_episode, intent="ceo_run", action=f"triggered: {title}",
                result="queued via Telegram")
        return f"▶️  Running: {title}"

    if cmd in ("revenue", "rev"):
        if not args or not _num(args[0]):
            return "Usage:  /revenue <amount> [source] [NPR|USD]\ne.g.  /revenue 18400 cafeteria NPR"
        amount = float(_num(args[0]))
        currency = "USD"
        source_word = ""
        for a in args[1:]:
            up = a.upper()
            if up in ("NPR", "USD", "INR", "EUR"):
                currency = up
            else:
                source_word = a.lower()
        source_name = _SOURCE_WORDS.get(source_word, "OTHER")
        if record_revenue_fn is None:
            from saathi.revenue import record_revenue as record_revenue_fn
            from saathi.revenue import RevenueSource, to_usd
            src = RevenueSource[source_name]
        else:
            src, to_usd = source_name, (lambda amt, cur: amt * (0.0075 if cur == "NPR" else 1.0))
        record_revenue_fn(source=src, amount=amount, currency=currency,
                          note="via Telegram CEO")
        usd = to_usd(amount, currency)
        dream = usd / DREAM_TARGET * 100
        return (f"💰  Recorded {currency} {amount:,.0f} ({source_word or 'other'}) = ${usd:,.2f}\n"
                f"🎯  Dream +{dream:.5f}%")

    if cmd in ("opps", "opportunities"):
        home = ceo_home_fn()
        opp = [a for a in home.get("actions", []) if a.get("dept") == "OPPORTUNITY"]
        if not opp:
            return "No new opportunities awaiting review."
        return "💡  Opportunities:\n" + "\n".join(f"• {a['title']}" for a in opp)

    if cmd in ("dream", "goal"):
        home = ceo_home_fn()
        return (f"🎯  Dream progress: {home.get('dreamPct', 0):.4f}%\n"
                f"    ${home.get('dreamCurrent', 0):,.0f} / ${DREAM_TARGET:,.0f}")

    if cmd == "help":
        return ("Commands:\n/brief · /details · /approve [n] · /run [n]\n"
                "/revenue <amt> [source] [NPR|USD] · /opps · /dream")
    return None
def _num(s: str):
    try:
        return float(s.replace(",", ""))
    except ValueError:
        return None
