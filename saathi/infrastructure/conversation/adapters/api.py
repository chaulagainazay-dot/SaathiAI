"""API adapter — for web / mobile / watch clients. Returns a JSON-able dict.

The same engine powers every future surface (mobile app, WhatsApp, Apple Watch)
by speaking HTTP instead of a keyboard or microphone.
"""
from __future__ import annotations


class ApiAdapter:
    def __init__(self, engine):
        self._engine = engine

    def handle(self, session_id: str, message: str, *, device: str = "api",
               user: str = "", locale: str = "en", speak: bool = False) -> dict:
        session = self._engine.session(session_id, device=device, user=user, locale=locale)
        reply = self._engine.handle(session, message=message, speak=speak)
        out = {"session_id": reply.session_id, "text": reply.text,
               "intent": reply.intent, "command": reply.command,
               "ui_events": reply.ui_events}
        if reply.speech is not None:
            out["has_speech"] = True
        return out
