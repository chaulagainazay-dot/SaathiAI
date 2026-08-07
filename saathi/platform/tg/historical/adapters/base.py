"""Adapter base contract — read-only, fail-closed."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from saathi.platform.tg.historical.models import AdjustedPriceBar, CorporateAction, DatasetSource


@dataclass
class AdapterResult:
    ok: bool
    bars: list[AdjustedPriceBar] = field(default_factory=list)
    corporate_actions: list[CorporateAction] = field(default_factory=list)
    source: DatasetSource | None = None
    source_file_fingerprint: str = ""
    error: str = ""
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_public(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "bar_count": len(self.bars),
            "corporate_action_count": len(self.corporate_actions),
            "source": self.source.to_public() if self.source else None,
            "source_file_fingerprint": self.source_file_fingerprint,
            "error": self.error,
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
            "read_only": True,
            "credentials_required": False,
            "live_trading": False,
        }


class HistoricalAdapter:
    name: str = "base"
    read_only: bool = True
    credentials_required: bool = False
    allows_live_orders: bool = False

    def load(self, **kwargs: Any) -> AdapterResult:
        raise NotImplementedError
