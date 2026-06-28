"""Grammar micro-agent — targeted grammar error analysis."""
from __future__ import annotations
import json
from typing import Any

from ....models import Perception, Strategy, Skill
from ..base import BaseSubAgent

_SYSTEM = (
    "You are a grammar specialist for IELTS. "
    "Respond ONLY in valid JSON: {errors: [{error, correction, rule}], severity: 'minor'|'major', summary: str}."
)


class GrammarSubAgent(BaseSubAgent):
    skill = Skill.GRAMMAR

    def build_prompt(self, perception: Perception, strategy: Strategy, context: dict[str, Any]):
        return [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": f"Analyse grammar errors in:\n\"{perception.raw_input}\""},
        ]

    def validate_output(self, raw: str) -> dict[str, Any]:
        clean = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        data = json.loads(clean)
        # Normalise to base schema
        corrections = [
            {"type": "grammar", "error": e.get("error", ""), "suggestion": e.get("correction", "")}
            for e in data.get("errors", [])
        ]
        return {
            "response": data.get("summary", "Grammar analysis complete."),
            "corrections": corrections,
            "metadata": {"severity": data.get("severity", "minor")},
        }
