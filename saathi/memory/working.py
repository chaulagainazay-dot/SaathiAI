"""Working memory — in-process ring buffer, per student, per session."""
from __future__ import annotations
from collections import deque
from typing import Any


_MAX_ENTRIES = 20  # keep the last 20 interactions per student


class WorkingMemory:
    def __init__(self):
        self._store: dict[str, deque] = {}

    def add(self, student_id: str, interaction: dict[str, Any]) -> None:
        if student_id not in self._store:
            self._store[student_id] = deque(maxlen=_MAX_ENTRIES)
        self._store[student_id].append(interaction)

    def get(self, student_id: str) -> list[dict[str, Any]]:
        return list(self._store.get(student_id, []))

    def recent(self, student_id: str, n: int = 5) -> list[dict[str, Any]]:
        items = self.get(student_id)
        return items[-n:]

    def clear(self, student_id: str) -> None:
        self._store.pop(student_id, None)
