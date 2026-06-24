from __future__ import annotations
"""
LinkedIn posting for pielts / Mr. Yeti content.

Auth flow (one-time):
  1. Visit http://127.0.0.1:8765/api/v1/linkedin/auth  → opens LinkedIn OAuth page
  2. Approve → LinkedIn redirects to /api/v1/linkedin/callback
  3. Access token stored in .env as LINKEDIN_ACCESS_TOKEN

Requires LinkedIn Developer App with scopes: openid, profile, w_member_social
Create at: https://www.linkedin.com/developers/apps

.env keys:
  LINKEDIN_CLIENT_ID
  LINKEDIN_CLIENT_SECRET
  LINKEDIN_ACCESS_TOKEN     (auto-set after OAuth)
  LINKEDIN_PERSON_URN       (auto-set after OAuth)
"""

import json
import os
import urllib.parse
from datetime import datetime, timedelta
from pathlib import Path

import requests as _requests

from .. import config

_API   = "https://api.linkedin.com/v2"
_AUTH  = "https://www.linkedin.com/oauth/v2"
_SCOPE = "openid profile w_member_social"
_REDIRECT = "http://127.0.0.1:8765/api/v1/linkedin/callback"

QUEUE_DIR  = config.ROOT / "data" / "linkedin"
QUEUE_DIR.mkdir(parents=True, exist_ok=True)
DAILY_FILE = QUEUE_DIR / "daily_posts.json"


# ── Credentials ───────────────────────────────────────────────────────────────

def _client_id()     -> str: return os.environ.get("LINKEDIN_CLIENT_ID", "")
def _client_secret() -> str: return os.environ.get("LINKEDIN_CLIENT_SECRET", "")
def _access_token()  -> str: return os.environ.get("LINKEDIN_ACCESS_TOKEN", "")
def _person_urn()    -> str: return os.environ.get("LINKEDIN_PERSON_URN", "")

def app_configured() -> bool:
    return bool(_client_id() and _client_secret())

def token_ok() -> bool:
    return bool(_access_token() and _person_urn())

def status() -> dict:
    return {
        "app_configured": app_configured(),
        "token_ok": token_ok(),
        "person_urn": _person_urn() if token_ok() else None,
    }


# ── OAuth helpers ─────────────────────────────────────────────────────────────

def get_auth_url() -> str:
    params = {
        "response_type": "code",
        "client_id": _client_id(),
        "redirect_uri": _REDIRECT,
        "scope": _SCOPE,
        "state": "baadar_linkedin",
    }
    return f"{_AUTH}/authorization?" + urllib.parse.urlencode(params)


def exchange_code(code: str) -> dict:
    """Exchange OAuth code for access token; persist to .env."""
    r = _requests.post(f"{_AUTH}/accessToken", data={
        "grant_type":    "authorization_code",
        "code":          code,
        "redirect_uri":  _REDIRECT,
        "client_id":     _client_id(),
        "client_secret": _client_secret(),
    }, timeout=20)
    r.raise_for_status()
    data = r.json()
    token = data.get("access_token", "")
    if not token:
        return {"ok": False, "error": "No access_token in response", "raw": data}

    # Extract person ID from id_token JWT (openid scope returns this)
    person_urn = ""
    id_token = data.get("id_token", "")
    if id_token:
        try:
            import base64, json as _json
            payload = id_token.split(".")[1]
            payload += "=" * (4 - len(payload) % 4)  # pad
            claims = _json.loads(base64.urlsafe_b64decode(payload))
            sub = claims.get("sub", "")
            if sub:
                person_urn = f"urn:li:person:{sub}"
        except Exception:
            pass

    # Fallback: try /v2/me (works if r_liteprofile available)
    if not person_urn:
        try:
            me = _requests.get(f"{_API}/me", headers={
                "Authorization": f"Bearer {token}",
                "X-Restli-Protocol-Version": "2.0.0",
            }, timeout=10).json()
            person_id = me.get("id", "")
            if person_id:
                person_urn = f"urn:li:person:{person_id}"
        except Exception:
            pass

    _persist_token(token, person_urn)
    return {"ok": True, "person_urn": person_urn}


def _persist_token(token: str, person_urn: str):
    """Write LINKEDIN_ACCESS_TOKEN and LINKEDIN_PERSON_URN to .env."""
    env_path = config.ROOT / ".env"
    text = env_path.read_text() if env_path.exists() else ""

    def _upsert(content: str, key: str, value: str) -> str:
        import re
        pattern = rf"^{key}=.*$"
        line = f"{key}={value}"
        if re.search(pattern, content, re.MULTILINE):
            return re.sub(pattern, line, content, flags=re.MULTILINE)
        return content.rstrip() + f"\n{line}\n"

    text = _upsert(text, "LINKEDIN_ACCESS_TOKEN", token)
    text = _upsert(text, "LINKEDIN_PERSON_URN", person_urn)
    env_path.write_text(text)

    # Hot-reload into current process
    os.environ["LINKEDIN_ACCESS_TOKEN"] = token
    os.environ["LINKEDIN_PERSON_URN"]   = person_urn


# ── Posting ───────────────────────────────────────────────────────────────────

def post_text(text: str) -> dict:
    """Post a text-only update to LinkedIn."""
    if not token_ok():
        return {"ok": False, "error": "Not connected — visit /api/v1/linkedin/auth first"}

    headers = {
        "Authorization": f"Bearer {_access_token()}",
        "Content-Type":  "application/json",
        "X-Restli-Protocol-Version": "2.0.0",
    }
    payload = {
        "author": _person_urn(),
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": text},
                "shareMediaCategory": "NONE",
            }
        },
        "visibility": {
            "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
        },
    }
    r = _requests.post(f"{_API}/ugcPosts", json=payload, headers=headers, timeout=20)
    if r.status_code in (200, 201):
        post_id = r.headers.get("x-restli-id", "")
        return {"ok": True, "post_id": post_id,
                "post_url": f"https://www.linkedin.com/feed/update/{post_id}/" if post_id else ""}
    elif r.status_code == 401:
        return {"ok": False, "error": "Token expired — reconnect at Settings → LinkedIn"}
    else:
        return {"ok": False, "error": f"LinkedIn API {r.status_code}", "detail": r.text[:300]}


# ── Daily post drafting ───────────────────────────────────────────────────────

_LI_SYSTEM = """You write LinkedIn posts for Ajay, a solo founder building pielts.web.app —
a free IELTS practice app for Nepali and South Asian students.

His LinkedIn voice:
- Personal storytelling: "I was building X when I realized…"
- Founder journey: small team (just him), real challenges, real wins
- Honest and specific: numbers, dates, real events preferred over vague claims
- Professional but warm — not corporate, not bro-marketing
- Ends with a soft CTA or question to spark comments
- 150–220 words
- Max 3 hashtags: always include #IELTS, pick 2 more from context
- Never say "game-changer", "I'm excited to announce", "synergy"
"""

_TOPICS = [
    "Behind the scenes building pielts.web.app as a solo founder",
    "A lesson I learned from real IELTS students using pielts",
    "How pielts helps Nepali students crack IELTS",
    "The hardest part of building an ed-tech app alone",
    "Feature I shipped this week on pielts.web.app and why",
    "What IELTS students really struggle with (from user feedback)",
    "Why I built pielts free when everyone else charges",
    "Milestone: pielts growth story",
    "A mistake I made building pielts and what I learned",
    "IELTS writing tip that actually moves the band score",
]


def draft_daily_post(cal_post: dict | None = None) -> dict:
    from ._llm_helper import ask_llm

    # Rotate topic by day-of-year
    day = datetime.now().timetuple().tm_yday
    topic = _TOPICS[day % len(_TOPICS)]
    if cal_post:
        topic = cal_post.get("core_message") or cal_post.get("hook") or topic

    prompt = f"""
Write a LinkedIn post for Ajay today.
Topic: {topic}
pielts.web.app URL: https://pielts.web.app
Today: {datetime.now().strftime('%A, %B %d')}

Return ONLY the finished LinkedIn post text (no JSON, no wrapper).
150-220 words. Include 2-3 hashtags at the end.
"""
    text = ask_llm(prompt, system=_LI_SYSTEM, timeout=45).strip()
    return {
        "text": text,
        "date": datetime.now().strftime("%Y-%m-%d"),
        "status": "pending",
        "created_at": datetime.now().isoformat(),
        "posted_at": None,
        "post_id": None,
        "post_url": None,
    }


# ── Queue management ──────────────────────────────────────────────────────────

def _load_daily() -> list[dict]:
    if DAILY_FILE.exists():
        try: return json.loads(DAILY_FILE.read_text())
        except Exception: pass
    return []


def _save_daily(posts: list[dict]):
    DAILY_FILE.write_text(json.dumps(posts, indent=2, ensure_ascii=False))


def queue_daily_post(cal_post: dict | None = None) -> dict:
    """Draft and queue today's LinkedIn post (idempotent)."""
    posts = _load_daily()
    today = datetime.now().strftime("%Y-%m-%d")
    if any(p["date"] == today for p in posts):
        return {"ok": True, "skipped": True, "reason": "Already queued for today"}
    draft = draft_daily_post(cal_post)
    posts.append(draft)
    _save_daily(posts[-30:])
    print(f"  💼 LinkedIn daily post queued: {draft['text'][:60]}…")
    return {"ok": True, "draft": draft}


def get_pending() -> list[dict]:
    today = datetime.now().strftime("%Y-%m-%d")
    return [p for p in _load_daily() if p["date"] == today and p["status"] == "pending"]


def mark_sent(date: str, post_id: str = "", post_url: str = "") -> dict:
    posts = _load_daily()
    for p in posts:
        if p["date"] == date and p["status"] == "pending":
            p.update({"status": "posted", "posted_at": datetime.now().isoformat(),
                      "post_id": post_id, "post_url": post_url})
            break
    _save_daily(posts)
    return {"ok": True}


def skip_today(date: str) -> dict:
    posts = _load_daily()
    for p in posts:
        if p["date"] == date: p["status"] = "skipped"; break
    _save_daily(posts)
    return {"ok": True}


def post_and_mark(date: str, text: str) -> dict:
    """Post to LinkedIn API and mark as sent."""
    result = post_text(text)
    if result.get("ok"):
        mark_sent(date, result.get("post_id", ""), result.get("post_url", ""))
    return result
