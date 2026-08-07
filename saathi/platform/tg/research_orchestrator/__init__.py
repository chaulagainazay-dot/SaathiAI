"""M280–M287 Autonomous Research Orchestrator.

RESEARCH ONLY. OFFLINE-FIRST. PAPER/SANDBOX ONLY.
NO BROKER. NO API KEYS. NO ORDER EXECUTION. NO LIVE TRADING.
"""
from saathi.platform.tg.research_orchestrator.models import (
    AUTHORITY_VALUES,
    MAX_STATE,
    TERMINAL_VERDICT,
)
from saathi.platform.tg.research_orchestrator.service import (
    ResearchOrchestratorService,
    default_research_orchestrator,
    reset_research_orchestrator_for_tests,
)

__all__ = [
    "ResearchOrchestratorService",
    "default_research_orchestrator",
    "reset_research_orchestrator_for_tests",
    "AUTHORITY_VALUES",
    "MAX_STATE",
    "TERMINAL_VERDICT",
]
