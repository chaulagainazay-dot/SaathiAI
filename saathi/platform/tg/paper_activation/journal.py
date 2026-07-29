"""Immutable paper trade journal for activation governance."""
from __future__ import annotations

from typing import Any

from saathi.platform.tg.paper_activation.models import JournalEntry


class PaperJournalError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class PaperActivationJournal:
    def __init__(self) -> None:
        self._entries: list[JournalEntry] = []
        self._by_id: dict[str, JournalEntry] = {}

    def append(self, entry: JournalEntry) -> JournalEntry:
        if entry.id in self._by_id:
            raise PaperJournalError("DUPLICATE", "journal entry ids must be unique")
        entry.immutable = True
        self._entries.append(entry)
        self._by_id[entry.id] = entry
        return entry

    def mutate(self, entry_id: str, **_kwargs: Any) -> None:
        raise PaperJournalError("IMMUTABLE", "paper journal entries cannot be mutated")

    def get(self, entry_id: str) -> JournalEntry | None:
        return self._by_id.get(entry_id)

    def list(
        self,
        *,
        portfolio_id: str = "",
        strategy_slug: str = "",
        org_id: str = "",
        limit: int = 200,
    ) -> list[JournalEntry]:
        out = []
        for e in reversed(self._entries):
            if portfolio_id and e.portfolio_id != portfolio_id:
                continue
            if strategy_slug and e.strategy_slug != strategy_slug:
                continue
            if org_id and e.org_id != org_id:
                continue
            out.append(e)
            if len(out) >= limit:
                break
        return out
