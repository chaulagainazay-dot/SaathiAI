"""Writing sub-agent — evaluates and coaches IELTS writing."""
from __future__ import annotations
import json
from typing import Any

from ...models import Perception, Strategy, Skill
from .base import BaseSubAgent

_SYSTEM = (
    "You are Mr. Yeti, an expert IELTS Writing coach. "
    "Respond ONLY in valid JSON with keys: response, feedback, corrections (list of "
    "{type, error, suggestion}), band_estimate (float), praise."
)


class WritingSubAgent(BaseSubAgent):
    skill = Skill.WRITING

    def build_prompt(self, perception: Perception, strategy: Strategy, context: dict[str, Any]):
        recent = context.get("recent_interactions", [])
        weaknesses = context.get("top_weaknesses", [])
        return [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": (
                f"Student writing:\n\"{perception.raw_input}\"\n\n"
                f"Strategy: {strategy.approach}\n"
                f"Known weaknesses: {weaknesses}\n"
                f"Recent interactions: {recent[-2:]}\n"
                "Evaluate for Task Achievement, Coherence, Lexical Resource, Grammar. "
                "Give a band estimate and 1-3 corrections with examples."
            )},
        ]

    def validate_output(self, raw: str) -> dict[str, Any]:
        # Strip markdown fences if present
        clean = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        return json.loads(clean)
