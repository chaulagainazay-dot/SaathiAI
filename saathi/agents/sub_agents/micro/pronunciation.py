"""Pronunciation micro-agent — phoneme and fluency coaching."""
from __future__ import annotations
import json
from typing import Any

from ....models import Perception, Strategy, Skill
from ..base import BaseSubAgent

_SYSTEM = (
    "You are a pronunciation specialist for IELTS Speaking. "
    "Respond ONLY in valid JSON: "
    "{issues: [{word, ipa_correct, tip}], fluency_note: str, overall_band: float}."
)


class PronunciationSubAgent(BaseSubAgent):
    skill = Skill.PRONUNCIATION

    def build_prompt(self, perception: Perception, strategy: Strategy, context: dict[str, Any]):
        accent = perception.metadata.get("accent", "general")
        return [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": (
                f"Transcript: \"{perception.raw_input}\"\n"
                f"Accent target: {accent}\n"
                "Identify likely pronunciation difficulties for a Nepali/South-Asian speaker. "
                "Give IPA and practical tips."
            )},
        ]

    def validate_output(self, raw: str) -> dict[str, Any]:
        clean = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        data = json.loads(clean)
        corrections = [
            {"type": "pronunciation", "error": i["word"], "suggestion": i.get("tip", "")}
            for i in data.get("issues", [])
        ]
        return {
            "response": data.get("fluency_note", "Pronunciation analysis complete."),
            "corrections": corrections,
            "band_estimate": data.get("overall_band"),
        }
