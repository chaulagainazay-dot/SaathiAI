"""Reading sub-agent — Socratic guidance on IELTS reading questions."""
from __future__ import annotations
import json
from typing import Any

from ...models import Perception, Strategy, Skill
from .base import BaseSubAgent

_SYSTEM = (
    "You are Mr. Yeti, an expert IELTS Reading coach. "
    "Use Socratic questioning — guide the student to the answer, don't give it directly. "
    "Respond ONLY in valid JSON with keys: response, feedback, corrections, band_estimate, praise, hint."
)


class ReadingSubAgent(BaseSubAgent):
    skill = Skill.READING

    def build_prompt(self, perception: Perception, strategy: Strategy, context: dict[str, Any]):
        passage = perception.metadata.get("passage_text", "")
        correct = perception.metadata.get("correct_answer", "")
        return [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": (
                f"Student answer: \"{perception.raw_input}\"\n"
                f"Correct answer: \"{correct}\"\n"
                f"Passage excerpt: \"{passage[:400]}\"\n"
                f"Strategy: {strategy.approach}\n"
                "Help the student understand why using a guiding question. "
                "If they got it right, reinforce the strategy."
            )},
        ]

    def validate_output(self, raw: str) -> dict[str, Any]:
        clean = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        return json.loads(clean)
