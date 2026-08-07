"""Research calendar — planned offline research slots (not live market calendar)."""
from __future__ import annotations

from typing import Any

from saathi.platform.tg.research_orchestrator.models import AUTHORITY_VALUES


class ResearchCalendar:
    """Static research schedule templates for orchestration planning."""

    SLOTS = [
        {"slot_id": "daily_compare", "cadence": "daily", "template_id": "tpl_strategy_compare_v1", "priority": "NORMAL"},
        {"slot_id": "weekly_bootstrap", "cadence": "weekly", "template_id": "tpl_lab_bootstrap_v1", "priority": "HIGH"},
        {"slot_id": "heartbeat", "cadence": "hourly", "template_id": "tpl_noop_v1", "priority": "BACKGROUND"},
    ]

    def list_slots(self) -> dict[str, Any]:
        return {
            "ok": True,
            "slots": list(self.SLOTS),
            "note": "Research planning calendar only — not live market session times",
            "live_market_calendar": False,
            **AUTHORITY_VALUES,
        }
