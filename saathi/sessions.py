"""Stateful session store — v1.2 adapter over Security Store.

The public API is unchanged from v1.1 for backward compatibility.
The backend now uses SQLite via Security Store instead of JSON files.
"""
from __future__ import annotations

import hashlib
import re
import secrets
import time

from saathi.security.store import get_store


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _store():
    return get_store()


def _owner_id() -> str:
    return _store().get_or_create_owner()


def _now() -> float:
    return time.time()


# ── device parsing (no external dep) ──────────────────────────────────────────
def describe(ua: str) -> tuple[str, str]:
    """(browser, os) from a User-Agent string — best-effort, dependency-free."""
    ua = ua or ""
    os_name = ("iOS" if re.search(r"iPhone|iPad|iPod", ua) else
               "Android" if "Android" in ua else
               "Windows" if "Windows" in ua else
               "macOS" if re.search(r"Mac OS X|Macintosh", ua) else
               "Linux" if "Linux" in ua else "Unknown")
    browser = ("Edge" if re.search(r"Edg/|EdgA/", ua) else
               "Chrome" if re.search(r"Chrome|CriOS", ua) else
               "Firefox" if re.search(r"Firefox|FxiOS", ua) else
               "Safari" if "Safari" in ua else "Unknown")
    return browser, os_name


def _platform_from_ua(ua: str) -> str:
    ua = ua or ""
    if re.search(r"iPhone|Android.*Mobile", ua):
        return "mobile"
    if re.search(r"iPad|Android(?!.*Mobile)", ua):
        return "tablet"
    return "desktop"


# ── public API (unchanged from v1.1) ──────────────────────────────────────────
def create(ua: str = "", ip: str = "", kind: str = "password", remember_me: bool = True) -> str:
    """Mint a new session; return the RAW token."""
    token = secrets.token_urlsafe(32)
    browser, os_name = describe(ua)
    platform = _platform_from_ua(ua)
    # Extract device name
    device_name = ("iPhone" if "iPhone" in ua else
                   "iPad" if "iPad" in ua else
                   "Mac" if "Mac OS X" in ua or "Macintosh" in ua else
                   "Android" if "Android" in ua else
                   "Windows" if "Windows" in ua else
                   "Linux" if "Linux" in ua else "Unknown")
    _store().session_create(
        user_id=_owner_id(),
        token_hash=_hash(token),
        browser=browser,
        os=os_name,
        platform=platform,
        device_name=device_name,
        user_agent=(ua or "")[:200],
        ip_address=ip or "",
        login_method=kind,
        remember_me=1 if remember_me else 0,
        expires_at=_now() + (30 * 24 * 3600 if remember_me else 24 * 3600),
    )
    return token


def validate(token: str, *, touch: bool = True) -> bool:
    """True if the token maps to a live session; refresh last_seen when touching."""
    if not token:
        return False
    th = _hash(token)
    rec = _store().session_by_hash(th)
    if not rec:
        return False
    if rec.get("revoked"):
        return False
    if rec.get("expires_at", 0) < _now():
        # Expired — the store's session_by_hash already filters revoked,
        # but we also check expiry here for safety
        return False
    if touch:
        _store().session_touch(th)
    return True


def session_id(token: str) -> str:
    return _hash(token)[:12] if token else ""


def listing(current_token: str = "") -> list[dict]:
    """Devices/sessions for the Security page — never leaks token material."""
    cur = _hash(current_token) if current_token else ""
    out = []
    for r in _store().session_list(_owner_id()):
        out.append({
            "id": r.get("id", ""),
            "browser": r.get("browser", "Unknown"),
            "os": r.get("os", "Unknown"),
            "platform": r.get("platform", "Unknown"),
            "device_name": r.get("device_name", "Unknown"),
            "ip": r.get("ip_address", ""),
            "kind": r.get("login_method", "password"),
            "label": r.get("label", ""),
            "created": r.get("first_seen", 0),
            "last_seen": r.get("last_seen", 0),
            "current": bool(cur) and r.get("token_hash") == cur,
            "expires": r.get("expires_at", 0),
            "remember_me": bool(r.get("remember_me", 1)),
            "risk_score": r.get("risk_score", 0),
        })
    out.sort(key=lambda x: x["last_seen"], reverse=True)
    return out


def revoke(session_id: str) -> bool:
    return _store().session_revoke(session_id)


def revoke_all(except_token: str = "") -> int:
    """Logout everywhere. Keep only the caller's own session when given."""
    keep_th = _hash(except_token) if except_token else ""
    return _store().session_revoke_all(_owner_id(), except_hash=keep_th)


def rename(session_id: str, label: str) -> bool:
    return _store().session_rename(session_id, label)


def rotate(old_token: str, ua: str = "", ip: str = "") -> str:
    """Invalidate old_token's session and mint a fresh one (same device)."""
    revoke(session_id(old_token))
    return create(ua=ua, ip=ip, kind="rotate")
