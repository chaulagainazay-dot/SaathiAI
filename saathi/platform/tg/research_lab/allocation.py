"""Adaptive allocation rule versioning (M277 support)."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from saathi.platform.tg.research_lab.models import AUTHORITY_VALUES, ENSEMBLE_ENGINE_VERSION


def allocation_rule_checksum(rule: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(rule, sort_keys=True, default=str).encode()).hexdigest()


def freeze_allocation_rule(
    method: str,
    strategy_ids: list[str],
    weights: dict[str, float],
    *,
    regime_inputs: dict | None = None,
    version: str = "v1",
    fitted_on: str = "training",
) -> dict[str, Any]:
    rule = {
        "allocation_rule_version": version,
        "method": method,
        "strategy_ids": list(strategy_ids),
        "weights": dict(weights),
        "regime_inputs": regime_inputs or {},
        "fitted_on": fitted_on,
        "frozen": True,
        "test_set_tuning_forbidden": True,
        "engine_version": ENSEMBLE_ENGINE_VERSION,
    }
    rule["checksum"] = allocation_rule_checksum(rule)
    rule["authority"] = AUTHORITY_VALUES["max_authority"]
    return rule
