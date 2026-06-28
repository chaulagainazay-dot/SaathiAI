"""SafetyHarness — pre/post validation wrapper for sub-agent execution."""
from __future__ import annotations
import re
from contextlib import asynccontextmanager
from typing import Any

from ..models import Perception, ActionResult

# Simple blocked-phrase list (extend as needed)
_BLOCKED_PATTERNS = [
    re.compile(r"\b(hack|cheat|exploit)\b", re.IGNORECASE),
]

# Pedagogical sanity: band estimates must be in IELTS range
_BAND_MIN, _BAND_MAX = 1.0, 9.0


class ContentFilter:
    def check(self, text: str) -> tuple[bool, str]:
        for pat in _BLOCKED_PATTERNS:
            if pat.search(text):
                return False, f"Blocked pattern: {pat.pattern}"
        return True, ""


class PedagogyChecker:
    def check_result(self, result: ActionResult) -> tuple[bool, str]:
        if result.band_estimate is not None:
            if not (_BAND_MIN <= result.band_estimate <= _BAND_MAX):
                return False, f"Band estimate {result.band_estimate} out of range"
        return True, ""


class BiasDetector:
    """Placeholder — future: detect culturally biased or discouraging language."""
    def check(self, text: str) -> tuple[bool, str]:
        return True, ""


class SafetyHarness:
    def __init__(self):
        self._content = ContentFilter()
        self._pedagogy = PedagogyChecker()
        self._bias = BiasDetector()

    async def validate_input(self, perception: Perception) -> None:
        ok, reason = self._content.check(perception.raw_input)
        if not ok:
            raise ValueError(f"Input blocked by SafetyHarness: {reason}")

    async def validate_output(self, result: ActionResult) -> ActionResult:
        ok, reason = self._pedagogy.check_result(result)
        if not ok:
            # Sanitise instead of hard-fail — clamp band to valid range
            if result.band_estimate is not None:
                result.band_estimate = max(_BAND_MIN, min(_BAND_MAX, result.band_estimate))

        ok_bias, _ = self._bias.check(result.response)
        result.safe = ok_bias
        return result

    @asynccontextmanager
    async def monitor(self, perception: Perception):
        await self.validate_input(perception)
        yield
        # post-execution validation happens in validate_output called by master
