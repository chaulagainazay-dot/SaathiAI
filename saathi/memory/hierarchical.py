"""HierarchicalMemory — three-tier store: working → episodic → semantic."""
from __future__ import annotations
from typing import Any

from .working import WorkingMemory
from .episodic import EpisodicMemory
from .semantic import SemanticMemory


class HierarchicalMemory:
    def __init__(self):
        self.working = WorkingMemory()
        self.episodic = EpisodicMemory()
        self.semantic = SemanticMemory()

    async def store_interaction(self, student_id: str, interaction: dict[str, Any]) -> None:
        interaction["student_id"] = student_id
        # Tier 1: immediate ring buffer
        self.working.add(student_id, interaction)
        # Tier 2: persistent session log
        await self.episodic.store(interaction)
        # Tier 3: long-term pattern extraction
        await self.semantic.update(student_id, interaction)

    def get_context(self, student_id: str) -> dict[str, Any]:
        """Assemble a context dict for prompt building."""
        recent = self.working.recent(student_id, n=5)
        weaknesses = self.semantic.get_top_weaknesses(student_id, n=3)
        return {
            "recent_interactions": recent,
            "top_weaknesses": weaknesses,
        }
