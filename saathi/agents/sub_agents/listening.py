"""Listening sub-agent — feedback on IELTS listening answers."""
from __future__ import annotations
import json
from typing import Any

from ...models import Perception, Strategy, Skill
from .base import BaseSubAgent

_SYSTEM = (
    "You are Mr. Yeti, an expert IELTS Listening coach. "
    "Respond ONLY in valid JSON with keys: response, feedback, corrections, band_estimate, praise, tip."
)


class ListeningSubAgent(BaseSubAgent):
    skill = Skill.LISTENING

    def build_prompt(self, perception: Perception, strategy: Strategy, context: dict[str, Any]):
        correct = perception.metadata.get("correct_answer", "")
        question_type = perception.metadata.get("question_type", "general")
        return [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": (
                f"Student answer: \"{perception.raw_input}\"\n"
                f"Correct answer: \"{correct}\"\n"
                f"Question type: {question_type}\n"
                f"Strategy: {strategy.approach}\n"
                "Explain why the answer is correct/incorrect and give a listening tip for this question type."
            )},
        ]

    def validate_output(self, raw: str) -> dict[str, Any]:
        clean = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        return json.loads(clean)
