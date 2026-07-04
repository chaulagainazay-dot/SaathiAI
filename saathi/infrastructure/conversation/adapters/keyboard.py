"""Keyboard adapter — plain text in, Reply out. The simplest channel."""
from __future__ import annotations


class KeyboardAdapter:
    device = "desktop"

    def __init__(self, engine):
        self._engine = engine

    def send(self, session_id: str, text: str, *, user: str = "", speak: bool = False):
        session = self._engine.session(session_id, device=self.device, user=user)
        return self._engine.handle(session, message=text, speak=speak)
