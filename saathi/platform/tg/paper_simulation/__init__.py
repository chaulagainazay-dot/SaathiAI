"""M288–M295 Institutional Paper Trading Simulation.

VIRTUAL EXCHANGE ONLY. NO BROKER. NO API KEYS. NO LIVE TRADING.
"""
from saathi.platform.tg.paper_simulation.models import (
    AUTHORITY_VALUES,
    MAX_STATE,
    TERMINAL_VERDICT,
)
from saathi.platform.tg.paper_simulation.service import (
    PaperSimulationService,
    default_paper_simulation,
    reset_paper_simulation_for_tests,
)

__all__ = [
    "PaperSimulationService",
    "default_paper_simulation",
    "reset_paper_simulation_for_tests",
    "AUTHORITY_VALUES",
    "MAX_STATE",
    "TERMINAL_VERDICT",
]
