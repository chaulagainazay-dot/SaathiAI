"""AgentMessageBus — cross-agent communication and pattern detection."""
from __future__ import annotations
from collections import defaultdict
from typing import Any, Callable, Awaitable

from ..models import ActionResult, Skill

# Error type → set of skills that have reported it for a student
_CrossPattern = dict[str, dict[str, set[str]]]  # student_id → error_type → {skill, ...}

_ESCALATION_THRESHOLD = 2  # same error in N+ skills triggers master escalation


class AgentMessageBus:
    def __init__(self):
        self._patterns: _CrossPattern = defaultdict(lambda: defaultdict(set))
        self._listeners: list[Callable[[str, str, list[str]], Awaitable[None]]] = []

    def subscribe(self, handler: Callable[[str, str, list[str]], Awaitable[None]]) -> None:
        """Subscribe to cross-skill escalation events."""
        self._listeners.append(handler)

    async def publish(self, result: ActionResult) -> None:
        """Record corrections from a result; escalate if cross-skill pattern found."""
        student_id = result.student_id
        skill = result.skill
        for corr in result.corrections:
            error_type = corr.get("type", "unknown")
            self._patterns[student_id][error_type].add(skill)
            skills_affected = self._patterns[student_id][error_type]
            if len(skills_affected) >= _ESCALATION_THRESHOLD:
                await self._escalate(student_id, error_type, list(skills_affected))

    async def _escalate(self, student_id: str, error_type: str, skills: list[str]) -> None:
        for handler in self._listeners:
            await handler(student_id, error_type, skills)

    def get_cross_patterns(self, student_id: str) -> list[dict[str, Any]]:
        """Return error types that appear across multiple skills."""
        return [
            {"error_type": et, "skills": list(skills)}
            for et, skills in self._patterns.get(student_id, {}).items()
            if len(skills) >= _ESCALATION_THRESHOLD
        ]

    def reset(self, student_id: str) -> None:
        self._patterns.pop(student_id, None)
