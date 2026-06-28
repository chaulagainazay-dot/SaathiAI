"""Perception, Decision, and state models for the Master Agent Loop."""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class AgentState(Enum):
    IDLE = "idle"
    PERCEIVING = "perceiving"
    DECIDING = "deciding"
    ACTING = "acting"
    REFLECTING = "reflecting"
    ERROR = "error"


class Skill(Enum):
    WRITING = "writing"
    SPEAKING = "speaking"
    READING = "reading"
    LISTENING = "listening"
    GRAMMAR = "grammar"
    VOCABULARY = "vocabulary"
    PRONUNCIATION = "pronunciation"


@dataclass
class StudentInput:
    student_id: str
    text: str
    skill: Optional[Skill] = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Perception:
    student_id: str
    raw_input: str
    detected_skill: Skill
    intent: str                    # e.g. "practice", "question", "correction_request"
    confidence: float
    context: dict[str, Any] = field(default_factory=dict)


@dataclass
class Strategy:
    primary_skill: Skill
    approach: str                  # e.g. "socratic", "direct_correction", "encouragement"
    sub_agents_to_invoke: list[Skill] = field(default_factory=list)
    parameters: dict[str, Any] = field(default_factory=dict)


@dataclass
class Decision:
    strategy: Strategy
    rationale: str
    cross_skill_patterns: list[str] = field(default_factory=list)
