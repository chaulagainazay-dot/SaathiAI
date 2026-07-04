"""ConversationSession — one live session per user/device across all channels.

The session is what lets "Continue." mean something: it carries history, the
active department, and the last command so any adapter (Telegram, mobile,
desktop, voice) resumes the same conversation brain.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

_MAX_HISTORY = 40


@dataclass
class ConversationSession:
    session_id: str
    user: str = ""
    device: str = ""                       # telegram | mobile | desktop | api | voice
    locale: str = "en"
    history: list[dict] = field(default_factory=list)   # {role, content, ts}
    active_department: str | None = None
    context: dict = field(default_factory=dict)
    last_command: str | None = None
    permissions: frozenset[str] = frozenset()

    def add(self, role: str, content: str) -> None:
        self.history.append({"role": role, "content": content, "ts": time.time()})
        if len(self.history) > _MAX_HISTORY:
            self.history = self.history[-_MAX_HISTORY:]

    def last_n(self, n: int) -> list[dict]:
        return self.history[-n:]


class SessionStore:
    """In-memory session registry (injectable; a durable backend can replace it)."""

    def __init__(self):
        self._sessions: dict[str, ConversationSession] = {}

    def get_or_create(self, session_id: str, **defaults) -> ConversationSession:
        s = self._sessions.get(session_id)
        if s is None:
            s = ConversationSession(session_id=session_id, **defaults)
            self._sessions[session_id] = s
        return s

    def get(self, session_id: str) -> ConversationSession | None:
        return self._sessions.get(session_id)

    def all(self) -> list[ConversationSession]:
        return list(self._sessions.values())

    def count(self) -> int:
        return len(self._sessions)

    def delete(self, session_id: str) -> bool:
        return self._sessions.pop(session_id, None) is not None
