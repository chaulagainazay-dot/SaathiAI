"""Speaking sub-agent — evaluates IELTS speaking transcripts."""
from __future__ import annotations
import json
from typing import Any

from ...models import Perception, Strategy, Skill
from .base import BaseSubAgent

_SYSTEM = (
    "You are Mr. Yeti, an expert IELTS Speaking examiner. "
    "Respond ONLY in valid JSON with keys: response, feedback, corrections (list of "
    "{type, error, suggestion}), band_estimate (float), praise, next_question."
)


class SpeakingSubAgent(BaseSubAgent):
    skill = Skill.SPEAKING

    def build_prompt(self, perception: Perception, strategy: Strategy, context: dict[str, Any]):
        weaknesses = context.get("top_weaknesses", [])
        part = perception.metadata.get("part", 1)
        return [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": (
                f"Student said (Part {part}):\n\"{perception.raw_input}\"\n\n"
                f"Strategy: {strategy.approach}\n"
                f"Known weaknesses: {weaknesses}\n"
                "Evaluate for Fluency, Lexical Resource, Grammar, Pronunciation. "
                "Give a band estimate, one praise, up to 2 corrections, and the next question."
            )},
        ]

    def validate_output(self, raw: str) -> dict[str, Any]:
        clean = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        return json.loads(clean)
