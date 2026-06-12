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
    with open(p, "rb") as f:
        r = httpx.post(
            f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendVideo",
            data={"chat_id": chat_id, "caption": caption[:1000]},
            files={"video": (p.name, f, "video/mp4")}, timeout=180)
    r.raise_for_status()
    return {"sent": True, "to_chat": chat_id, "file": p.name}


def send_telegram(text: str) -> dict:
    if not config.TELEGRAM_BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN not configured")
    r = httpx.post(
        f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage",
        json={"chat_id": config.TELEGRAM_CHAT_ID, "text": text},
        timeout=15,
    )
    r.raise_for_status()
    return {"status": "sent"}
