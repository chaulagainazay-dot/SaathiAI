"""Email adapter — SMTP-pluggable, inert until configured.

Set SMTP_HOST/SMTP_PORT/SMTP_USER/SMTP_PASS/SMTP_FROM in .env to enable real
sending. Until then send() logs the message to ~/.saathi/outbox.log and returns
delivered=False, so the whole recovery flow is testable without a mail server
and can be switched to live SMTP with zero code changes.
"""
from __future__ import annotations

import json
import os
import ssl
import time
from pathlib import Path

_OUTBOX = Path.home() / ".saathi" / "outbox.log"


def configured() -> bool:
    return bool(os.getenv("SMTP_HOST") and os.getenv("SMTP_FROM"))


def _log(to: str, subject: str, body: str, delivered: bool) -> None:
    try:
        _OUTBOX.parent.mkdir(parents=True, exist_ok=True)
        with _OUTBOX.open("a") as f:
            f.write(json.dumps({"ts": time.time(), "to": to, "subject": subject,
                                "delivered": delivered, "body": body[:500]}) + "\n")
    except Exception:
        pass


def send(to: str, subject: str, body: str) -> dict:
    """Return {ok, delivered, reason}. Never raises — recovery must not 500."""
    if not configured():
        _log(to, subject, body, False)
        return {"ok": True, "delivered": False, "reason": "smtp_not_configured"}
    try:
        import smtplib
        from email.message import EmailMessage
        msg = EmailMessage()
        msg["From"] = os.getenv("SMTP_FROM")
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body)
        host, port = os.getenv("SMTP_HOST"), int(os.getenv("SMTP_PORT", "587"))
        ctx = ssl.create_default_context()
        if port == 465:
            with smtplib.SMTP_SSL(host, port, context=ctx, timeout=15) as s:
                s.login(os.getenv("SMTP_USER", ""), os.getenv("SMTP_PASS", ""))
                s.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=15) as s:
                s.starttls(context=ctx)
                if os.getenv("SMTP_USER"):
                    s.login(os.getenv("SMTP_USER"), os.getenv("SMTP_PASS", ""))
                s.send_message(msg)
        _log(to, subject, body, True)
        return {"ok": True, "delivered": True, "reason": "sent"}
    except Exception as e:
        _log(to, subject, body, False)
        return {"ok": False, "delivered": False, "reason": str(e)[:120]}
