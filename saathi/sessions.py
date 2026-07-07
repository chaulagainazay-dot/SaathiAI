"""Stateful session store — the keystone for real session management.

The legacy session token was *deterministic* (a hash of the password), so every
device shared one token that never rotated: "logout everywhere", per-device
revocation, device lists and token rotation were all impossible. This module
issues opaque *random* tokens, each persisted with device metadata, so all of
that becomes possible.

Single-owner, file-backed (~/.saathi/sessions.json). Tokens are stored HASHED
(sha256) — the raw token lives only in the owner's cookie/localStorage, so a
leak of the store cannot mint a session. Backward-compatible: the server still
also accepts the legacy deterministic token for already-signed-in devices.
"""
from __future__ import annotations

import hashlib
import json
import re
import secrets
import time
from pathlib import Path

_STORE = Path.home() / ".saathi" / "sessions.json"
_MAX_AGE = 30 * 24 * 3600          # 30 days idle → expired
_HARD_CAP = 100                    # keep the file bounded


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _load() -> list[dict]:
    try:
        return json.loads(_STORE.read_text())
    except Exception:
        return []


def _save(rows: list[dict]) -> None:
    _STORE.parent.mkdir(parents=True, exist_ok=True)
    _STORE.write_text(json.dumps(rows[-_HARD_CAP:]))


# ── device parsing (no external dep) ──────────────────────────────────────────
def describe(ua: str) -> tuple[str, str]:
    """(browser, os) from a User-Agent string — best-effort, dependency-free."""
    ua = ua or ""
    os_name = ("iOS" if re.search(r"iPhone|iPad|iPod", ua) else
               "Android" if "Android" in ua else
               "Windows" if "Windows" in ua else
               "macOS" if re.search(r"Mac OS X|Macintosh", ua) else
               "Linux" if "Linux" in ua else "Unknown")
    # order matters: Edge/Chrome both contain "Chrome"; Chrome/Safari overlap
    browser = ("Edge" if re.search(r"Edg/|EdgA/", ua) else
               "Chrome" if re.search(r"Chrome|CriOS", ua) else
               "Firefox" if re.search(r"Firefox|FxiOS", ua) else
               "Safari" if "Safari" in ua else "Unknown")
    return browser, os_name


def _now() -> float:
    return time.time()


def _prune(rows: list[dict]) -> list[dict]:
    now = _now()
    cut = now - _MAX_AGE
    return [r for r in rows if r.get("last_seen", 0) >= cut and r.get("expires", float("inf")) > now]


# ── public API ────────────────────────────────────────────────────────────────
def create(ua: str = "", ip: str = "", kind: str = "password", remember_me: bool = True) -> str:
    """Mint a new session; return the RAW token (store keeps only its hash)."""
    token = secrets.token_urlsafe(32)
    browser, os_name = describe(ua)
    rows = _prune(_load())
    rows.append({
        "id": _hash(token)[:12],           # stable public handle for revoke/list
        "th": _hash(token),                # token hash (secret compare)
        "created": _now(), "last_seen": _now(),
        "browser": browser, "os": os_name, "ua": (ua or "")[:200],
        "ip": ip or "", "kind": kind, "label": "",
        "remember_me": remember_me,
        "expires": _now() + (30*24*3600 if remember_me else 24*3600),
        "revoked": False,
    })
    _save(rows)
    return token


def validate(token: str, *, touch: bool = True) -> bool:
    """True if the token maps to a live session; refresh last_seen when touching."""
    if not token:
        return False
    th = _hash(token)
    rows = _prune(_load())
    hit = next((r for r in rows if r.get("th") == th), None)
    if not hit:
        return False
    if hit.get("revoked"):
        return False
    if hit.get("expires", 0) < _now():
        # Remove expired session
        _save([r for r in rows if r.get("th") != th])
        return False
    if touch:
        hit["last_seen"] = _now()
        _save(rows)
    return True


def session_id(token: str) -> str:
    return _hash(token)[:12] if token else ""


def listing(current_token: str = "") -> list[dict]:
    """Devices/sessions for the Security page — never leaks token material."""
    cur = _hash(current_token) if current_token else ""
    out = []
    for r in _prune(_load()):
        out.append({
            "id": r.get("id", ""), "browser": r.get("browser", "Unknown"),
            "os": r.get("os", "Unknown"), "ip": r.get("ip", ""),
            "kind": r.get("kind", "password"), "label": r.get("label", ""),
            "created": r.get("created", 0), "last_seen": r.get("last_seen", 0),
            "current": bool(cur) and r.get("th") == cur,
            "expires": r.get("expires", 0),
            "remember_me": r.get("remember_me", True),
        })
    out.sort(key=lambda x: x["last_seen"], reverse=True)
    return out


def revoke(session_id: str) -> bool:
    rows = _load()
    hit = next((r for r in rows if r.get("id") == session_id), None)
    if not hit:
        return False
    hit["revoked"] = True
    _save(rows)
    return True


def revoke_all(except_token: str = "") -> int:
    """Logout everywhere. Keep only the caller's own session when given."""
    keep_th = _hash(except_token) if except_token else ""
    rows = _load()
    revoked = 0
    for r in rows:
        if not (keep_th and r.get("th") == keep_th):
            r["revoked"] = True
            revoked += 1
    _save(rows)
    return revoked


def rename(session_id: str, label: str) -> bool:
    rows = _load()
    hit = next((r for r in rows if r.get("id") == session_id), None)
    if not hit:
        return False
    hit["label"] = (label or "")[:60]
    _save(rows)
    return True


def rotate(old_token: str, ua: str = "", ip: str = "") -> str:
    """Invalidate old_token's session and mint a fresh one (same device)."""
    revoke(session_id(old_token))
    return create(ua=ua, ip=ip, kind="rotate")
