"""Telegram adapter — the Telegram companion, now on the shared engine.

Parses a Telegram update into a session + message, runs the SAME conversation
engine every other channel uses, and delivers the reply through the Connector
Registry (never a raw Bot API call).
"""
from __future__ import annotations


class TelegramAdapter:
    device = "telegram"

    def __init__(self, engine, *, registry=None, trusted_chat: str | None = None):
        self._engine = engine
        self._registry = registry
        self._trusted = str(trusted_chat) if trusted_chat is not None else None

    def _reg(self):
        if self._registry is None:
            from saathi.infrastructure.connectors import default_registry
            self._registry = default_registry()
        return self._registry

    def deliver(self, chat_id: str, text: str) -> None:
        self._reg().execute(capability="send_text", connector_id="telegram",
                            chat_id=chat_id, text=text[:4000])

    def handle_update(self, update: dict, *, deliver: bool = True):
        """Process one getUpdates entry. Returns the Reply, or None if ignored."""
        msg = update.get("message") or {}
        chat = str(msg.get("chat", {}).get("id", ""))
        text = (msg.get("text") or "").strip()
        if not text:
            return None
        if self._trusted is not None and chat != self._trusted:
            return None                    # only the trusted chat is served
        session = self._engine.session(f"telegram:{chat}", device=self.device, user=chat)
        try:
            reply = self._engine.handle(session, message=text)
        except Exception as e:
            reply_text = f"⚠️ {type(e).__name__}: {str(e)[:120]}"
            if deliver:
                self.deliver(chat, reply_text)
            return None
        if deliver:
            self.deliver(chat, reply.text)
        return reply
