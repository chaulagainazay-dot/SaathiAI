"""Test selector — maps a subsystem/category to focused test targets.

Focused tests run first (fast signal), then the full suite runs as the
regression gate. Paths are best-effort; unknown ones are dropped so pytest
never errors on a missing node.
"""
from __future__ import annotations

from pathlib import Path

from saathi.repair.incident import RepairIncident, FailureCategory

ROOT = Path(__file__).resolve().parent.parent.parent

# category/subsystem -> candidate test files
_MAP: dict[str, list[str]] = {
    "execution_gateway": [
        "tests/test_execution_gateway.py", "tests/test_execution.py",
        "tests/test_trade_journal.py",
    ],
    "event_bus": [
        "tests/test_infra_events.py", "tests/test_eventstream.py",
        "tests/test_events_bus_api.py",
    ],
    "bff": ["tests/test_bff.py"],
    "connectors": ["tests/test_connectors.py", "tests/test_connector_layer.py",
                   "tests/test_connector_drivers.py"],
    "intent_router": ["tests/test_conversation.py"],
    "capability_registry": ["tests/test_capabilities.py"],
    "cowork": ["tests/test_control_room.py"],
}

_CATEGORY_MAP: dict[FailureCategory, list[str]] = {
    FailureCategory.EVENT_BUS_ERROR: ["tests/test_infra_events.py",
                                      "tests/test_eventstream.py",
                                      "tests/test_events_bus_api.py"],
    FailureCategory.IMPORT_ERROR: ["tests/test_execution_gateway.py"],
    FailureCategory.COLLECTION_ERROR: [],
    FailureCategory.ASYNC_ERROR: ["tests/test_execution_gateway.py"],
    FailureCategory.API_CONTRACT_MISMATCH: ["tests/test_bff.py"],
    FailureCategory.CONNECTOR_AUTH_ERROR: ["tests/test_connectors.py"],
    FailureCategory.CONNECTOR_RUNTIME_ERROR: ["tests/test_connectors.py"],
}


def _existing(paths: list[str]) -> list[str]:
    return [p for p in paths if (ROOT / p).exists()]


def focused_targets(inc: RepairIncident) -> list[str]:
    """Ordered, de-duplicated, existing focused test files."""
    picks: list[str] = []
    # 1) explicit failing tests always come first
    for t in inc.failed_tests:
        node = t.split("::")[0]
        if node.endswith(".py") and (ROOT / node).exists():
            picks.append(node)
    # 2) by subsystem
    picks += _MAP.get(inc.subsystem, [])
    # 3) by category
    picks += _CATEGORY_MAP.get(inc.category, [])
    # de-dup preserving order, keep only existing
    seen: list[str] = []
    for p in picks:
        if p not in seen:
            seen.append(p)
    return _existing(seen)
