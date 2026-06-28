"""BaseSubAgent — abstract base for all skill sub-agents."""
from __future__ import annotations
import json
import os
from abc import ABC, abstractmethod
from typing import Any

from groq import AsyncGroq

from ...models import Perception, Strategy, ActionResult, Skill

_GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

_groq_client: AsyncGroq | None = None


def _get_groq() -> AsyncGroq:
    global _groq_client
    if _groq_client is None:
        _groq_client = AsyncGroq(api_key=os.getenv("GROQ_API_KEY"))
    return _groq_client


class BaseSubAgent(ABC):
    skill: Skill

    @abstractmethod
    def build_prompt(
        self, perception: Perception, strategy: Strategy, context: dict[str, Any]
    ) -> list[dict[str, str]]:
        """Return a list of Groq chat messages."""

    @abstractmethod
    def validate_output(self, raw: str) -> dict[str, Any]:
        """Parse and validate the LLM response."""

    async def call_llm(self, messages: list[dict[str, str]], max_tokens: int = 400) -> str:
        resp = await _get_groq().chat.completions.create(
            model=_GROQ_MODEL,
            messages=messages,
            temperature=0.5,
            max_tokens=max_tokens,
        )
        return resp.choices[0].message.content or ""

    async def apply_pedagogy(
        self, structured: dict[str, Any], perception: Perception
    ) -> dict[str, Any]:
        """Apply pedagogical guardrails: encourage first, correct gently."""
        structured.setdefault("feedback", "")
        if structured.get("corrections"):
            praise = structured.get("praise", "Good effort!")
            structured["response"] = f"{praise} {structured.get('response', '')}"
        return structured

    async def format_for_frontend(self, output: dict[str, Any]) -> ActionResult:
        return ActionResult(
            student_id=output.get("student_id", ""),
            skill=self.skill.value,
            response=output.get("response", ""),
            feedback=output.get("feedback"),
            corrections=output.get("corrections", []),
            band_estimate=output.get("band_estimate"),
            xp_delta=output.get("xp_delta", 10),
            metadata=output.get("metadata", {}),
        )

    async def execute(
        self, perception: Perception, strategy: Strategy, context: dict[str, Any]
    ) -> ActionResult:
        messages = self.build_prompt(perception, strategy, context)
        raw = await self.call_llm(messages)
        try:
            structured = self.validate_output(raw)
        except Exception:
            structured = {"response": raw, "corrections": []}
        structured["student_id"] = perception.student_id
        pedagogical = await self.apply_pedagogy(structured, perception)
        return await self.format_for_frontend(pedagogical)
