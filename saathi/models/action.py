"""ActionResult model returned by sub-agents and the master loop."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ActionResult:
    student_id: str
    skill: str
    response: str                       # primary response text
    feedback: Optional[str] = None      # pedagogical feedback
    corrections: list[dict] = field(default_factory=list)
    band_estimate: Optional[float] = None
    xp_delta: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    safe: bool = True                   # cleared by SafetyHarness
    reflection_notes: list[str] = field(default_factory=list)
