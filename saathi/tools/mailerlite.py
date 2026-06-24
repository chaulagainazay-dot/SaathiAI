"""MailerLite v3 — subscriber management and automation for pielts.web.app leads."""
from __future__ import annotations
import os
import httpx

API_KEY = os.getenv("MAILERLITE_API_KEY", "")
BASE = "https://connect.mailerlite.com/api"


def _h():
    return {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}


def _configured() -> bool:
    return bool(API_KEY)


# ── Subscribers ────────────────────────────────────────────────────────────────

def add_subscriber(email: str, group_id: str = "", fields: dict | None = None) -> dict:
    """Add or update a subscriber. Optionally add to a group."""
    if not _configured():
        return {"error": "MAILERLITE_API_KEY not set"}
    payload: dict = {"email": email}
    if fields:
        payload["fields"] = fields
    if group_id:
        payload["groups"] = [group_id]
    try:
        r = httpx.post(f"{BASE}/subscribers", headers=_h(), json=payload, timeout=15)
        r.raise_for_status()
        return {"ok": True, "subscriber": r.json().get("data", {})}
    except Exception as e:
        return {"error": str(e)[:300]}


def get_subscriber(email: str) -> dict:
    """Look up a subscriber by email."""
    if not _configured():
        return {"error": "MAILERLITE_API_KEY not set"}
    try:
        r = httpx.get(f"{BASE}/subscribers/{email}", headers=_h(), timeout=15)
        if r.status_code == 404:
            return {"found": False}
        r.raise_for_status()
        return {"found": True, "subscriber": r.json().get("data", {})}
    except Exception as e:
        return {"error": str(e)[:300]}


def list_subscribers(group_id: str = "", limit: int = 25) -> dict:
    """List subscribers, optionally filtered by group."""
    if not _configured():
        return {"error": "MAILERLITE_API_KEY not set"}
    try:
        params: dict = {"limit": limit}
        url = f"{BASE}/groups/{group_id}/subscribers" if group_id else f"{BASE}/subscribers"
        r = httpx.get(url, headers=_h(), params=params, timeout=15)
        r.raise_for_status()
        data = r.json()
        subs = data.get("data", [])
        return {"count": len(subs), "subscribers": [
            {"email": s.get("email"), "status": s.get("status"), "created_at": s.get("created_at")}
            for s in subs
        ]}
    except Exception as e:
        return {"error": str(e)[:300]}


# ── Groups ─────────────────────────────────────────────────────────────────────

def list_groups() -> dict:
    """List all subscriber groups."""
    if not _configured():
        return {"error": "MAILERLITE_API_KEY not set"}
    try:
        r = httpx.get(f"{BASE}/groups", headers=_h(), timeout=15)
        r.raise_for_status()
        groups = r.json().get("data", [])
        return {"groups": [{"id": g["id"], "name": g["name"], "count": g.get("active_count", 0)} for g in groups]}
    except Exception as e:
        return {"error": str(e)[:300]}


def create_group(name: str) -> dict:
    """Create a new subscriber group."""
    if not _configured():
        return {"error": "MAILERLITE_API_KEY not set"}
    try:
        r = httpx.post(f"{BASE}/groups", headers=_h(), json={"name": name}, timeout=15)
        r.raise_for_status()
        g = r.json().get("data", {})
        return {"ok": True, "id": g.get("id"), "name": g.get("name")}
    except Exception as e:
        return {"error": str(e)[:300]}


# ── Automations ────────────────────────────────────────────────────────────────

def list_automations() -> dict:
    """List all automations."""
    if not _configured():
        return {"error": "MAILERLITE_API_KEY not set"}
    try:
        r = httpx.get(f"{BASE}/automations", headers=_h(), timeout=15)
        r.raise_for_status()
        items = r.json().get("data", [])
        return {"automations": [
            {"id": a["id"], "name": a["name"], "enabled": a.get("enabled"), "emails": a.get("emails_count", 0)}
            for a in items
        ]}
    except Exception as e:
        return {"error": str(e)[:300]}


def get_automation(automation_id: str) -> dict:
    """Get details of a specific automation."""
    if not _configured():
        return {"error": "MAILERLITE_API_KEY not set"}
    try:
        r = httpx.get(f"{BASE}/automations/{automation_id}", headers=_h(), timeout=15)
        r.raise_for_status()
        return r.json().get("data", {})
    except Exception as e:
        return {"error": str(e)[:300]}


# ── Campaigns (one-off broadcast emails) ──────────────────────────────────────

def create_campaign(name: str, subject: str, from_name: str, from_email: str,
                    html_content: str, group_ids: list[str]) -> dict:
    """Create a broadcast campaign (not automation — one-off send to a group)."""
    if not _configured():
        return {"error": "MAILERLITE_API_KEY not set"}
    try:
        payload = {
            "name": name,
            "type": "regular",
            "emails": [{
                "subject": subject,
                "from_name": from_name,
                "from": from_email,
                "content": html_content,
            }],
            "groups": group_ids,
        }
        r = httpx.post(f"{BASE}/campaigns", headers=_h(), json=payload, timeout=15)
        r.raise_for_status()
        data = r.json().get("data", {})
        return {"ok": True, "id": data.get("id"), "name": data.get("name"), "status": data.get("status")}
    except Exception as e:
        return {"error": str(e)[:300]}


def list_campaigns(limit: int = 20) -> dict:
    """List recent campaigns with stats."""
    if not _configured():
        return {"error": "MAILERLITE_API_KEY not set"}
    try:
        r = httpx.get(f"{BASE}/campaigns", headers=_h(), params={"limit": limit}, timeout=15)
        r.raise_for_status()
        campaigns = r.json().get("data", [])
        return {"campaigns": [
            {"id": c["id"], "name": c["name"], "status": c.get("status"),
             "sent_at": c.get("sent_at"), "open_rate": c.get("stats", {}).get("open_rate")}
            for c in campaigns
        ]}
    except Exception as e:
        return {"error": str(e)[:300]}


def get_stats() -> dict:
    """Get account-level stats: total subscribers, open rates, groups."""
    groups = list_groups()
    subs = list_subscribers(limit=1)
    automations = list_automations()
    return {
        "groups": groups.get("groups", []),
        "automations": automations.get("automations", []),
        "note": "Use list_subscribers(group_id=...) for group-specific counts",
    }
