"""Two-way Telegram — Ajay texts Baadar from anywhere (abroad), Baadar replies/acts.
Long-polls getUpdates; only responds to Ajay's own chat id."""
import threading
import time

import httpx

from . import config

_STARTED = False


def _send(text: str):
    try:
        from saathi.infrastructure.connectors import default_registry
        default_registry().execute(capability="send_text", connector_id="telegram",
                                   chat_id=config.TELEGRAM_CHAT_ID, text=text[:4000])
    except Exception:
        pass


def _loop():
    if not (config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID):
        return
    from .agent import SaathiAgent
    agent = SaathiAgent()
    offset = None
    while True:
        try:
            from saathi.infrastructure.connectors import default_registry
            r = default_registry().execute(capability="get_updates", connector_id="telegram",
                                           timeout=50, offset=offset,
                                           allowed_updates='["message"]')
            for u in r.get("result", []):
                offset = u["update_id"] + 1
                msg = u.get("message", {})
                chat = str(msg.get("chat", {}).get("id", ""))
                text = (msg.get("text") or "").strip()
                if not text or chat != str(config.TELEGRAM_CHAT_ID):
                    continue  # only Ajay's chat is trusted
                try:
                    # fast CEO command layer first; falls through to the agent
                    from .telegram_ceo import handle_command
                    reply = handle_command(text)
                    if reply is None:
                        reply = agent.respond(text, session_id="telegram", speaker_verified=True)
                except Exception as e:
                    reply = f"⚠️ {type(e).__name__}: {str(e)[:120]}"
                _send(reply)
        except Exception:
            time.sleep(5)


def start():
    global _STARTED
    if _STARTED:
        return
    _STARTED = True
    threading.Thread(target=_loop, daemon=True).start()
