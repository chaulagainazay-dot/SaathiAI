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
    # One shared conversation engine (command layer → agent) behind the Telegram
    # adapter — the same brain every other channel uses. One agent instance is
    # reused across messages so in-process state persists.
    from .agent import SaathiAgent
    from saathi.infrastructure.conversation import ConversationEngine, TelegramAdapter
    from saathi.infrastructure.connectors import default_registry
    try:
        from saathi.events import bus as _bus
    except Exception:
        _bus = None
    agent = SaathiAgent()

    def _brain(message, session):
        return agent.respond(message, session_id=session.session_id, speaker_verified=True)

    engine = ConversationEngine(brain=_brain, bus=_bus)
    adapter = TelegramAdapter(engine, registry=default_registry(),
                              trusted_chat=config.TELEGRAM_CHAT_ID)
    offset = None
    while True:
        try:
            r = default_registry().execute(capability="get_updates", connector_id="telegram",
                                           timeout=50, offset=offset,
                                           allowed_updates='["message"]')
            for u in r.get("result", []):
                offset = u["update_id"] + 1
                adapter.handle_update(u)   # parse → engine → deliver via connector
        except Exception:
            time.sleep(5)


def start():
    global _STARTED
    if _STARTED:
        return
    _STARTED = True
    threading.Thread(target=_loop, daemon=True).start()
