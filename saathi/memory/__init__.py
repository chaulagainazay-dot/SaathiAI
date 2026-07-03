from .working import WorkingMemory
from .episodic import EpisodicMemory
from .semantic import SemanticMemory
from .hierarchical import HierarchicalMemory
from ._legacy import Memory  # backward-compat: existing code imports Memory from saathi.memory
# M2 Phase 1a — generic platform memory (product-agnostic Episode/Knowledge,
# Promotion State Machine, retention, scope, source trace, verification count)
from .platform import (
    PlatformMemory, Episode, Knowledge,
    PromotionState, MemoryScope, RetentionPolicy,
)

__all__ = [
    "WorkingMemory", "EpisodicMemory", "SemanticMemory", "HierarchicalMemory", "Memory",
    "PlatformMemory", "Episode", "Knowledge",
    "PromotionState", "MemoryScope", "RetentionPolicy",
]
