"""Narrow read-only adapter protocol."""
from __future__ import annotations

from typing import Any, Protocol

from saathi.knowledge.registry import KnowledgeSource
from saathi.knowledge.types import KnowledgeQuery, KnowledgeResult


class SourceAdapter(Protocol):
    name: str

    def supports(self, query: KnowledgeQuery, source: KnowledgeSource) -> bool: ...

    def retrieve(
        self,
        query: KnowledgeQuery,
        source: KnowledgeSource,
        *,
        limit: int = 8,
    ) -> list[KnowledgeResult]: ...

    def health(self, source: KnowledgeSource) -> dict: ...

    def describe_capabilities(self) -> dict: ...
