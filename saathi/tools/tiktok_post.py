"""
TikTok Content Posting API v2 — auto-upload Mr. Yeti videos.

One-time setup:
  1. Create a TikTok Developer app at https://developers.tiktok.com
  2. Add product: "Content Posting API"
  3. Set redirect URL: http://127.0.0.1:8765/api/v1/tiktok/callback
  4. Visit http://127.0.0.1:8765/api/v1/tiktok/auth → approve → done

.env keys auto-written after OAuth:
  TIKTOK_CLIENT_KEY
  TIKTOK_CLIENT_SECRET
  TIKTOK_ACCESS_TOKEN
  TIKTOK_OPEN_ID
"""

import json
import math
import os
import time
import urllib.parse
from pathlib import Path

import requests as _req

from .. import config

_AUTH_URL    = "https://www.tiktok.com/v2/auth/authorize/"
_TOKEN_URL   = "https://open.tiktokapis.com/v2/oauth/token/"
_INIT_URL    = "https://open.tiktokapis.com/v2/post/publish/video/init/"
_STATUS_URL  = "https://open.tiktokapis.com/v2/post/publish/status/fetch/"
_REVOKE_URL  = "https://open.tiktokapis.com/v2/oauth/revoke/"
_SCOPE       = "video.upload,video.publish"
_REDIRECT    = os.environ.get("TIKTOK_REDIRECT_URI", "http://127.0.0.1:8765/api/v1/tiktok/callback")
_CHUNK_SIZE  = 10 * 1024 * 1024   # 10 MB chunks

QUEUE_DIR  = config.ROOT / "data" / "tiktok"
QUEUE_DIR.mkdir(parents=True, exist_ok=True)
QUEUE_FILE = QUEUE_DIR / "queue.json"


# ── Credentials ───────────────────────────────────────────────────────────────

def _key()    -> str: return os.environ.get("TIKTOK_CLIENT_KEY", "")
def _secret() -> str: return os.environ.get("TIKTOK_CLIENT_SECRET", "")
def _token()  -> str: return os.environ.get("TIKTOK_ACCESS_TOKEN", "")
def _open_id()-> str: return os.environ.get("TIKTOK_OPEN_ID", "")

def app_configured() -> bool: return bool(_key() and _secret())

def token_ok() -> bool:
    """True only if token + open_id exist AND the token hasn't expired."""
    if not (_token() and _open_id()):
        return False
    expiry = os.environ.get("TIKTOK_TOKEN_EXPIRY", "")
    if expiry:
        try:
            import time
            if int(time.time()) >= int(expiry):
                return False  # expired — needs re-auth
        except ValueError:
            pass
    return True

def token_expired() -> bool:
    """True if a token exists but has passed its expiry timestamp."""
    expiry = os.environ.get("TIKTOK_TOKEN_EXPIRY", "")
    if not expiry or not _token():
        return False
    try:
        import time
        return int(time.time()) >= int(expiry)
    except ValueError:
        return False

def status() -> dict:
    expired = token_expired()
    return {
        "app_configured": app_configured(),
        "token_ok":       token_ok(),
        "token_expired":  expired,
        "open_id":        _open_id() if _token() else None,
        "reauth_needed":  expired,
    }


# ── OAuth ──────────────────────────────────────────────────────────────────────

# Store PKCE verifier in memory for the duration of the auth flow
_pkce_store: dict = {}


def _pkce_pair() -> tuple[str, str]:
    """Return (code_verifier, code_challenge) using S256 method."""
    import secrets, hashlib, base64
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


def get_auth_url() -> str:
    import secrets
    state = secrets.token_urlsafe(16)
    verifier, challenge = _pkce_pair()
    _pkce_store["verifier"] = verifier
    _pkce_store["state"] = state
    params = {
        "client_key":            _key(),
        "response_type":         "code",
        "scope":                 _SCOPE,
        "redirect_uri":          _REDIRECT,
        "state":                 state,
        "code_challenge":        challenge,
        "code_challenge_method": "S256",
    }
    return _AUTH_URL + "?" + urllib.parse.urlencode(params)


def exchange_code(code: str) -> dict:
    verifier = _pkce_store.get("verifier", "")
    payload = {
        "client_key":    _key(),
        "client_secret": _secret(),
        "code":          code,
        "grant_type":    "authorization_code",
        "redirect_uri":  _REDIRECT,
    }
    if verifier:
        payload["code_verifier"] = verifier
    r = _req.post(_TOKEN_URL, data=payload, timeout=20)
    r.raise_for_status()
    data = r.json()
    if data.get("error"):
        return {"ok": False, "error": data.get("error_description", data["error"])}

    token   = data.get("access_token", "")
    open_id = data.get("open_id", "")
    if not token:
        return {"ok": False, "error": "No access_token", "raw": data}

    expires_in = data.get("expires_in", 0)  # seconds until expiry
    _persist_token(token, open_id, expires_in)
    return {"ok": True, "open_id": open_id}


def _persist_token(token: str, open_id: str, expires_in: int = 0):
    import re as _re
    from datetime import datetime as _dt, timezone as _tz
    env_path = config.ROOT / ".env"
    text = env_path.read_text() if env_path.exists() else ""

    def _upsert(content: str, key: str, value: str) -> str:
        pat = rf"^{key}=.*$"
        line = f"{key}={value}"
        if _re.search(pat, content, _re.MULTILINE):
            return _re.sub(pat, line, content, flags=_re.MULTILINE)
        return content.rstrip() + f"\n{line}\n"

    text = _upsert(text, "TIKTOK_ACCESS_TOKEN", token)
    text = _upsert(text, "TIKTOK_OPEN_ID",      open_id)
    if expires_in:
        expiry_ts = int(_dt.now(_tz.utc).timestamp()) + expires_in
        text = _upsert(text, "TIKTOK_TOKEN_EXPIRY", str(expiry_ts))
        os.environ["TIKTOK_TOKEN_EXPIRY"] = str(expiry_ts)
    env_path.write_text(text)
    os.environ["TIKTOK_ACCESS_TOKEN"] = token
    os.environ["TIKTOK_OPEN_ID"]      = open_id


def token_expiry_days() -> int:
    """Returns days until TikTok token expires. -1 if unknown, 0 if already expired."""
    from datetime import datetime as _dt, timezone as _tz
    expiry_str = os.environ.get("TIKTOK_TOKEN_EXPIRY", "")
    if not expiry_str:
        # Try reading from .env
        try:
            for line in (config.ROOT / ".env").read_text().splitlines():
                if line.startswith("TIKTOK_TOKEN_EXPIRY="):
                    expiry_str = line.split("=", 1)[1].strip()
                    break
        except Exception:
            pass
    if not expiry_str:
        return -1  # unknown
    try:
        expiry_ts = int(expiry_str)
        now_ts = int(_dt.now(_tz.utc).timestamp())
        days = max(0, (expiry_ts - now_ts) // 86400)
        return days
    except Exception:
        return -1


# ── Video upload ───────────────────────────────────────────────────────────────

def post_video(
    video_path: str,
    title: str,
    description: str = "",
    privacy: str = "PUBLIC_TO_EVERYONE",
) -> dict:
    """
    Upload a video to TikTok via the Content Posting API PUSH method.
    privacy: PUBLIC_TO_EVERYONE | MUTUAL_FOLLOW_FRIENDS | SELF_ONLY
    Returns {"ok": True, "publish_id": "...", "share_url": "..."}
    """
    if not token_ok():
        return {"ok": False, "error": "Not connected — visit /api/v1/tiktok/auth first"}

    p = Path(video_path)
    if not p.exists():
        return {"ok": False, "error": f"Video not found: {video_path}"}

    file_size  = p.stat().st_size
    chunk_count = math.ceil(file_size / _CHUNK_SIZE)

    headers = {
        "Authorization": f"Bearer {_token()}",
        "Content-Type":  "application/json; charset=UTF-8",
    }

    # Step 1 — init upload
    caption = f"{title}\n\n{description}".strip()[:2200]
    init_body = {
        "post_info": {
            "title":           caption,
            "privacy_level":   privacy,
            "disable_duet":    False,
            "disable_comment": False,
            "disable_stitch":  False,
            "video_cover_timestamp_ms": 1000,
        },
        "source_info": {
            "source":          "FILE_UPLOAD",
            "video_size":      file_size,
            "chunk_size":      _CHUNK_SIZE,
            "total_chunk_count": chunk_count,
        },
    }
    r = _req.post(_INIT_URL, json=init_body, headers=headers, timeout=30)
    if r.status_code != 200:
        return {"ok": False, "error": f"Init failed {r.status_code}", "detail": r.text[:300]}

    resp = r.json().get("data", {})
    upload_url  = resp.get("upload_url", "")
    publish_id  = resp.get("publish_id", "")
    if not upload_url:
        return {"ok": False, "error": "No upload_url returned", "raw": r.json()}

    # Step 2 — upload chunks
    with open(p, "rb") as fh:
        for chunk_idx in range(chunk_count):
            chunk = fh.read(_CHUNK_SIZE)
            start = chunk_idx * _CHUNK_SIZE
            end   = start + len(chunk) - 1
            upload_headers = {
                "Content-Range":  f"bytes {start}-{end}/{file_size}",
                "Content-Length": str(len(chunk)),
                "Content-Type":   "video/mp4",
            }
            ur = _req.put(upload_url, data=chunk, headers=upload_headers, timeout=120)
            if ur.status_code not in (200, 201, 206):
                return {"ok": False, "error": f"Chunk {chunk_idx} upload failed {ur.status_code}",
                        "detail": ur.text[:200]}

    # Step 3 — poll status (up to 3 min)
    for _ in range(18):
        time.sleep(10)
        sr = _req.post(_STATUS_URL,
                       json={"publish_id": publish_id},
                       headers=headers, timeout=20)
        if sr.status_code == 200:
            sdata = sr.json().get("data", {})
            state = sdata.get("status", "")
            if state == "PUBLISH_COMPLETE":
                share_url = sdata.get("share_url", "")
                return {"ok": True, "publish_id": publish_id, "share_url": share_url}
            if state in ("FAILED", "CANCELLED"):
                return {"ok": False, "error": f"TikTok publish {state}",
                        "detail": sdata.get("fail_reason", "")}

    return {"ok": True, "publish_id": publish_id, "share_url": "",
            "note": "Upload sent — TikTok is still processing (may take a few minutes)"}


# ── Daily queue ────────────────────────────────────────────────────────────────

def _load_queue() -> list:
    try: return json.loads(QUEUE_FILE.read_text()) if QUEUE_FILE.exists() else []
    except Exception: return []

def _save_queue(q: list):
    QUEUE_FILE.write_text(json.dumps(q, indent=2, ensure_ascii=False))

def queue_video(video_path: str, title: str, description: str = "") -> dict:
    from datetime import datetime
    q = _load_queue()
    today = datetime.now().strftime("%Y-%m-%d")
    if any(item["date"] == today for item in q):
        return {"ok": True, "skipped": True, "reason": "Already queued for today"}
    entry = {
        "date": today, "video_path": video_path,
        "title": title, "description": description,
        "status": "pending", "created_at": datetime.now().isoformat(),
        "publish_id": None, "share_url": None,
    }
    q.append(entry)
    _save_queue(q[-30:])
    return {"ok": True, "queued": entry}

def get_pending() -> list:
    from datetime import datetime
    today = datetime.now().strftime("%Y-%m-%d")
    return [i for i in _load_queue() if i["date"] == today and i["status"] == "pending"]

def mark_sent(date: str, publish_id: str = "", share_url: str = ""):
    q = _load_queue()
    from datetime import datetime
    for item in q:
        if item["date"] == date and item["status"] == "pending":
            item.update({"status": "posted",
                         "posted_at": datetime.now().isoformat(),
                         "publish_id": publish_id,
                         "share_url": share_url})
            break
    _save_queue(q)

def post_and_mark(date: str, video_path: str, title: str, description: str = "") -> dict:
    result = post_video(video_path, title, description)
    if result.get("ok"):
        mark_sent(date, result.get("publish_id", ""), result.get("share_url", ""))
    return result
