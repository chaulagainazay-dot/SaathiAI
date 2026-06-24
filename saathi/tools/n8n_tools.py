from __future__ import annotations
"""n8n workflow triggers + Telegram delivery."""
import httpx

from .. import config


def trigger(workflow: str, params: dict | None = None) -> dict:
    r = httpx.post(f"{config.N8N_WEBHOOK_BASE}/{workflow}",
                   json=params or {}, timeout=60)
    r.raise_for_status()
    body = (r.json() if r.headers.get("content-type", "").startswith("application/json")
            else r.text)
    return {"status": "triggered", "workflow": workflow, "response": body}


def _discover_chat_id() -> str:
    """Find Ajay's chat id from recent messages to the bot (after he messages it)."""
    if config.TELEGRAM_CHAT_ID:
        return config.TELEGRAM_CHAT_ID
    r = httpx.get(f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/getUpdates",
                  timeout=15).json()
    for u in reversed(r.get("result", [])):
        chat = (u.get("message") or u.get("channel_post") or {}).get("chat", {})
        if chat.get("id"):
            return str(chat["id"])
    return ""


def send_video(path: str, caption: str = "") -> dict:
    """Send a video file to Ajay's Telegram (works on Android — replaces AirDrop)."""
    from pathlib import Path
    chat_id = _discover_chat_id()
    if not chat_id:
        return {"error": "no_chat_id",
                "message": "Message @AjayGmailbot once from your phone, then retry."}
    p = Path(path).expanduser()
    if not p.exists():
        return {"error": "video not found", "path": str(p)}
    try:
        with open(p, "rb") as f:
            r = httpx.post(
                f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendVideo",
                data={"chat_id": chat_id, "caption": caption[:1000]},
                files={"video": (p.name, f, "video/mp4")}, timeout=120)
        r.raise_for_status()
        return {"sent": True, "to_chat": chat_id, "file": p.name}
    except Exception as e:
        return {"error": str(e), "file": p.name}


# Blueprint slug → n8n workflow ID mapping (imported from LeadGenSpot)
BLUEPRINT_SLUGS: dict[str, str] = {
    "email-reply-agent":   "2BD6DEFD",
    "chatgpt-content":     "293CAFF8",
    "branded-social":      "860C4981",
    "instagram-carousel":  "9B181FD0",
    "social-cross-post":   "454BEA15",
    "tiktok-repost":       "6AA18B05",
    "content-generator":   "D9671041",
    "content-publisher":   "58B4E606",
    "fb-lead-notify":      "7FD76925",
    "coach-reel-carousel": "C04298D8",
    "fb-comment-reply":    "9D63E96E",
}


def trigger_blueprint(slug: str, params: dict | None = None) -> dict:
    """Trigger a LeadGenSpot blueprint by slug.
    Slugs: email-reply-agent, chatgpt-content, branded-social,
    instagram-carousel, social-cross-post, tiktok-repost,
    content-generator, content-publisher, fb-lead-notify,
    coach-reel-carousel, fb-comment-reply
    """
    if slug not in BLUEPRINT_SLUGS:
        return {"error": f"unknown slug '{slug}'", "available": list(BLUEPRINT_SLUGS.keys())}
    return trigger(BLUEPRINT_SLUGS[slug], params)


def list_blueprints() -> dict:
    """List all available LeadGenSpot blueprint slugs."""
    return {"blueprints": list(BLUEPRINT_SLUGS.keys())}


def send_telegram(text: str) -> dict:
    if not config.TELEGRAM_BOT_TOKEN:
        return {"error": "no_token"}
    try:
        r = httpx.post(
            f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": config.TELEGRAM_CHAT_ID, "text": text},
            timeout=8,
        )
        r.raise_for_status()
        return {"status": "sent"}
    except Exception as e:
        return {"error": str(e)}
