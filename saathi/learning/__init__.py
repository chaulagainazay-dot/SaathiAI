"""Learning Runtime — SaathiAI becomes better tomorrow because of today (M2 Phase 3).

    Execution → Outcome Evaluation → Failure Analysis → Lesson Extraction
              → Capability Improvement → Learning Policy → explicit outputs

The Learning Engine never writes prompts directly — it proposes. LLM assists
only lesson extraction (AP-17); everything else is deterministic and testable.
"""
from saathi.learning.failures import FailureCategory, classify_failure
from saathi.learning.registry import (
    CapabilityImprovementRegistry, ImprovementProposal, ImprovementStatus,
    Experiment, ExperimentStatus,
)
from saathi.learning.engine import (
    LearningEngine, LearningReport, Lesson, OutcomeScore, LearningOutput,
    route_lesson, deterministic_lesson_extractor,
)

__all__ = [
    "FailureCategory", "classify_failure",
    "CapabilityImprovementRegistry", "ImprovementProposal", "ImprovementStatus",
    "Experiment", "ExperimentStatus",
    "LearningEngine", "LearningReport", "Lesson", "OutcomeScore", "LearningOutput",
    "route_lesson", "deterministic_lesson_extractor",
]
