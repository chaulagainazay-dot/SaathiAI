"""
referral.py — Detect band score improvements → trigger referral offer.
Polls Firebase RTDB every 6 hours via Baadar background task.
"""
import json, os, random, sqlite3, string
from datetime import datetime, timezone, timedelta
from pathlib import Path

from .. import config
from ._llm_helper import ask_llm, extract_json

DB_PATH = os.getenv("BAADAR_DB", str(config.ROOT / "data" / "baadar.db"))
FIREBASE_DB_URL = "https://ielts-and-language-practice-default-rtdb.firebaseio.com"
_SA_KEY = os.path.expanduser(os.getenv("FIREBASE_SA_KEY", "~/SaathiAI/firebase-admin.json"))

# Minimum band improvement to trigger referral
MIN_IMPROVEMENT = 0.5


def _conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def generate_referral_code(uid: str) -> str:
    """Generate a unique 8-char referral code based on uid + random suffix."""
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=5))
    return f"{uid[:3].upper()}{suffix}"


def check_and_trigger_referral(uid: str, old_score: float, new_score: float) -> dict:
    """If band improvement >= 0.5, generate referral code and save event."""
    improvement = new_score - old_score
    if improvement < MIN_IMPROVEMENT:
        return {"triggered": False, "uid": uid, "improvement": improvement}
    code = generate_referral_code(uid)
    with _conn() as c:
        # Avoid duplicate events for same uid within 30 days
        existing = c.execute(
            "SELECT id FROM referral_events WHERE uid=? AND sent_at > datetime('now', '-30 days')",
            (uid,)
        ).fetchone()
        if existing:
            return {"triggered": False, "uid": uid, "reason": "already_sent_recently"}
        c.execute(
            "INSERT INTO referral_events (uid, old_score, new_score, referral_code) VALUES (?,?,?,?)",
            (uid, old_score, new_score, code)
        )
        c.commit()
    # Send Telegram alert to Ajay
    try:
        from .n8n_tools import send_telegram
        send_telegram(
            f"Referral triggered!\n\nUser {uid} improved from {old_score} to {new_score} band\n"
            f"Referral code: {code}\nOffer sent: Invite 3 friends to unlock Pro 7 days"
        )
    except Exception:
        pass
    return {"triggered": True, "uid": uid, "referral_code": code,
            "old_score": old_score, "new_score": new_score}


def poll_score_improvements() -> list:
    """Check Firebase RTDB for users whose band score improved. Called every 6h."""
    try:
        import firebase_admin
        from firebase_admin import credentials, db as rtdb
        if not firebase_admin._apps:
            cred = credentials.Certificate(_SA_KEY)
            firebase_admin.initialize_app(cred, {"databaseURL": FIREBASE_DB_URL})
        users_ref = rtdb.reference("users")
        all_users = users_ref.get() or {}
    except Exception as e:
        return [{"error": str(e)}]

    triggered = []
    with _conn() as c:
        known = {r["uid"]: r for r in c.execute(
            "SELECT uid, new_score FROM referral_events"
        ).fetchall()}

    for uid, profile in all_users.items():
        if not isinstance(profile, dict):
            continue
        current_score = profile.get("bandScore") or profile.get("band_score") or 0
        if not current_score:
            continue
        prev_score = known.get(uid, {}).get("new_score", current_score)
        result = check_and_trigger_referral(uid, prev_score, float(current_score))
        if result.get("triggered"):
            triggered.append(result)

    return triggered
