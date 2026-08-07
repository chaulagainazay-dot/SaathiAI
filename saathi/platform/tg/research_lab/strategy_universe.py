"""Strategy universe adapter — composes with M248 Strategy Registry."""
from __future__ import annotations

from typing import Any

from saathi.platform.tg.research_lab.models import AUTHORITY_VALUES


class StrategyUniverse:
    """Read-only view over the institutional strategy registry (no parallel catalog)."""

    def __init__(self):
        from saathi.platform.tg.intelligence.strategy_registry import StrategyRegistryEngine
        self._registry = StrategyRegistryEngine()

    def list_strategies(self, category: str | None = None) -> dict[str, Any]:
        return self._registry.list_strategies(category)

    def get(self, strategy_id: str) -> dict[str, Any] | None:
        return self._registry.get(strategy_id)

    def categories_present(self) -> list[str]:
        listed = self._registry.list_strategies()
        cats = sorted({s.get("category") for s in listed.get("strategies") or [] if s.get("category")})
        return cats

    def resolve_many(self, strategy_ids: list[str]) -> dict[str, Any]:
        found = []
        missing = []
        for sid in strategy_ids:
            s = self.get(sid)
            if s:
                found.append(s)
            else:
                missing.append(sid)
        return {
            "ok": len(missing) == 0,
            "strategies": found,
            "missing": missing,
            "categories_present": sorted({s.get("category") for s in found if s.get("category")}),
            **AUTHORITY_VALUES,
        }
