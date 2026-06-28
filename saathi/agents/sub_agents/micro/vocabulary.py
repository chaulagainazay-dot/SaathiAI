"""Vocabulary micro-agent — lexical resource analysis."""
from __future__ import annotations
import json
from typing import Any

from ....models import Perception, Strategy, Skill
from ..base import BaseSubAgent

_SYSTEM = (
    "You are a vocabulary specialist for IELTS. "
    "Respond ONLY in valid JSON: "
    "{upgrades: [{original, upgrade, reason}], lexical_band: float, feedback: str}."
)


class VocabularySubAgent(BaseSubAgent):
    skill = Skill.VOCABULARY

    def build_prompt(self, perception: Perception, strategy: Strategy, context: dict[str, Any]):
        return [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": (
                f"Suggest Band 7+ vocabulary upgrades for:\n\"{perception.raw_input}\"\n"
                "Focus on collocations, academic phrases, and precise word choice."
            )},
        ]

    def validate_output(self, raw: str) -> dict[str, Any]:
        clean = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        data = json.loads(clean)
        corrections = [
            {"type": "vocabulary", "error": u["original"], "suggestion": u["upgrade"]}
            for u in data.get("upgrades", [])
        ]
        return {
            "response": data.get("feedback", "Vocabulary analysis complete."),
            "corrections": corrections,
            "band_estimate": data.get("lexical_band"),
        }
