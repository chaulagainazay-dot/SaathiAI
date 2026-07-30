"""M272–M279 Multi-Strategy Research Lab, Portfolio Optimisation and Adaptive Regime Intelligence.

RESEARCH ONLY. OFFLINE-FIRST. PAPER/SANDBOX ONLY.
NO BROKER CONNECTIVITY. NO API KEYS. NO ORDER EXECUTION. NO LIVE TRADING.
"""
from saathi.platform.tg.research_lab.models import (
    AUTHORITY_VALUES,
    MAX_STATE,
    TERMINAL_VERDICT,
)
from saathi.platform.tg.research_lab.service import (
    ResearchLabService,
    default_research_lab,
    reset_research_lab_for_tests,
)

__all__ = [
    "ResearchLabService",
    "default_research_lab",
    "reset_research_lab_for_tests",
    "AUTHORITY_VALUES",
    "MAX_STATE",
    "TERMINAL_VERDICT",
]
