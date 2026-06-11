"""Gmail — read, summarize, and send email by voice.

Uses Gmail API with OAuth credentials in .env (GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET,
GMAIL_REFRESH_TOKEN). Until those are set it returns a clear setup message, so the
tool exists and Baadar knows about it. Get a refresh token once via Google OAuth
(the same flow Ajay's email-agent project uses).
"""
import base64
import os
from email.mime.text import MIMEText

import httpx

CLIENT_ID = os.getenv("GMAIL_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("GMAIL_CLIENT_SECRET", "")
REFRESH_TOKEN = os.getenv("GMAIL_REFRESH_TOKEN", "")


def _configured() -> bool:
    return all([CLIENT_ID, CLIENT_SECRET, REFRESH_TOKEN])


def _access_token() -> str:
    r = httpx.post("https://oauth2.googleapis.com/token", data={
        "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET,
        "refresh_token": REFRESH_TOKEN, "grant_type": "refresh_token"}, timeout=20)
    r.raise_for_status()
    return r.json()["access_token"]


def _headers():
    return {"Authorization": f"Bearer {_access_token()}"}


def check_email(query: str = "is:unread", limit: int = 8) -> dict:
    """Read recent emails (default: unread). Returns sender + subject + snippet.
    Uses the Gmail API if configured, else reads the logged-in Gmail in the browser
    via screen vision."""
    if not _configured():
        return _check_email_browser(query)
    try:
        base = "https://gmail.googleapis.com/gmail/v1/users/me"
        lst = httpx.get(f"{base}/messages", headers=_headers(),
                        params={"q": query, "maxResults": limit}, timeout=20).json()
        out = []
        for m in lst.get("messages", []):
            msg = httpx.get(f"{base}/messages/{m['id']}", headers=_headers(),
                            params={"format": "metadata",
                                    "metadataHeaders": ["From", "Subject"]},
                            timeout=20).json()
            h = {x["name"]: x["value"] for x in msg.get("payload", {}).get("headers", [])}
            out.append({"from": h.get("From", "?"), "subject": h.get("Subject", "(no subject)"),
                        "snippet": msg.get("snippet", "")[:140]})
        return {"emails": out, "count": len(out)}
    except Exception as e:
        return {"error": str(e)[:200]}


def _check_email_browser(query: str) -> dict:
    """Read Gmail via the logged-in browser + screen vision (no API needed)."""
    import subprocess
    import time
    # bring Gmail to the front in Brave, then look at the screen
    url = "https://mail.google.com/mail/u/0/#search/" + query.replace(" ", "+") \
          if query and query != "is:unread" else "https://mail.google.com/mail/u/0/#inbox"
    subprocess.run(["open", "-a", "Brave Browser", url], capture_output=True)
    time.sleep(3)
    from .. import vision
    return vision.ask_screen(
        "This is Ajay's Gmail inbox. List the most recent/unread emails: for each give "
        "the sender, the subject, and a few words of preview. If nothing notable, say so.")


def _compose_url(to: str, subject: str, body: str) -> str:
    from urllib.parse import quote
    return ("https://mail.google.com/mail/?view=cm&fs=1"
            f"&to={quote(to)}&su={quote(subject)}&body={quote(body)}")


def send_email(to: str, subject: str, body: str) -> dict:
    """Send an email. Baadar reads it back and confirms before calling this."""
    if not _configured():
        # browser path: open a pre-filled Gmail compose window, then send it
        import subprocess
        import time
        subprocess.run(["open", "-a", "Brave Browser", _compose_url(to, subject, body)],
                       capture_output=True)
        time.sleep(4)
        # Gmail sends with Cmd+Return when the compose window is focused
        script = ('tell application "Brave Browser" to activate\n'
                  'delay 1\n'
                  'tell application "System Events" to keystroke return using command down')
        p = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
        if p.returncode != 0:
            return {"opened_compose": True, "sent": False,
                    "note": "Pre-filled compose is open in Gmail — Ajay can press "
                            "Cmd+Return or click Send. (Keystroke failed: "
                            f"{p.stderr.strip()[:80]})"}
        return {"sent": True, "to": to, "subject": subject, "via": "browser"}
    try:
        mime = MIMEText(body)
        mime["to"] = to
        mime["subject"] = subject
        raw = base64.urlsafe_b64encode(mime.as_bytes()).decode()
        r = httpx.post(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
            headers=_headers(), json={"raw": raw}, timeout=20)
        r.raise_for_status()
        return {"sent": True, "to": to, "subject": subject}
    except Exception as e:
        return {"error": str(e)[:200]}
