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
