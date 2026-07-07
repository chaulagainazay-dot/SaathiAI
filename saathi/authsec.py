"""Auth security primitives — audit log, rate limiting, password hashing.

Dependency-free (stdlib only) so it installs cleanly on the VM. PBKDF2-HMAC-SHA256
replaces the old bare sha256 (salted, 600k iterations); legacy bare-sha256 hashes
are still verified and transparently upgraded on next successful use.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import time
from collections import deque
from pathlib import Path

_DIR = Path.home() / ".saathi"
_AUDIT = _DIR / "auth_audit.log"
_PBKDF2_ITERS = 600_000


# ── password hashing (salted PBKDF2, backward compatible) ─────────────────────
def hash_password(pw: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), _PBKDF2_ITERS)
    return f"pbkdf2$sha256${_PBKDF2_ITERS}${salt}${dk.hex()}"


def verify_password(pw: str, stored: str) -> bool:
    if not stored:
        return False
    if stored.startswith("pbkdf2$"):
        try:
            _, algo, iters, salt, want = stored.split("$")
            dk = hashlib.pbkdf2_hmac(algo, pw.encode(), bytes.fromhex(salt), int(iters))
            return hmac.compare_digest(dk.hex(), want)
        except Exception:
            return False
    # legacy bare sha256 (upgraded on next change)
    return hmac.compare_digest(hashlib.sha256(pw.encode()).hexdigest(), stored)


def needs_upgrade(stored: str) -> bool:
    return bool(stored) and not stored.startswith("pbkdf2$")


def password_strength(pw: str) -> dict:
    """0–4 score + human requirements — mirrors the client meter server-side."""
    checks = {
        "length": len(pw) >= 8,
        "lower": any(c.islower() for c in pw),
        "upper": any(c.isupper() for c in pw),
        "digit": any(c.isdigit() for c in pw),
        "symbol": any(not c.isalnum() for c in pw),
    }
    score = sum([checks["length"], checks["lower"] or checks["upper"],
                 checks["digit"], checks["symbol"]])
    label = ["Very weak", "Weak", "Fair", "Good", "Strong"][max(0, min(4, score))]
    return {"score": score, "label": label, "checks": checks}


# ── audit log (append-only, best-effort) ──────────────────────────────────────
def audit(event: str, *, ok: bool = True, ip: str = "", ua: str = "", detail: str = "") -> None:
    try:
        _DIR.mkdir(parents=True, exist_ok=True)
        rec = {"ts": time.time(), "event": event, "ok": ok, "ip": ip,
               "ua": (ua or "")[:160], "detail": (detail or "")[:200]}
        with _AUDIT.open("a") as f:
            f.write(json.dumps(rec) + "\n")
    except Exception:
        pass


def recent_audit(limit: int = 40) -> list[dict]:
    try:
        lines = _AUDIT.read_text().splitlines()[-limit:]
        return [json.loads(x) for x in reversed(lines)]
    except Exception:
        return []


# ── rate limiting / brute-force lockout (in-memory sliding window) ────────────
_WINDOWS: dict[str, deque] = {}


def rate_check(key: str, *, limit: int = 5, window: float = 300.0) -> tuple[bool, int]:
    """Returns (allowed, retry_after_seconds). Sliding window per key (e.g. ip:login)."""
    now = time.time()
    dq = _WINDOWS.setdefault(key, deque())
    while dq and dq[0] < now - window:
        dq.popleft()
    if len(dq) >= limit:
        return False, int(window - (now - dq[0])) + 1
    return True, 0


def rate_hit(key: str) -> None:
    _WINDOWS.setdefault(key, deque()).append(time.time())


def rate_clear(key: str) -> None:
    _WINDOWS.pop(key, None)
