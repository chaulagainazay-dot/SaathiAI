"""Student profile and band-score models."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class BandScores:
    writing: Optional[float] = None
    speaking: Optional[float] = None
    reading: Optional[float] = None
    listening: Optional[float] = None
    overall: Optional[float] = None


@dataclass
class StudentProfile:
    student_id: str
    target_band: float = 7.0
    current_band: float = 5.0
    band_scores: BandScores = field(default_factory=BandScores)
    weaknesses: list[str] = field(default_factory=list)
    session_count: int = 0
    total_interactions: int = 0
