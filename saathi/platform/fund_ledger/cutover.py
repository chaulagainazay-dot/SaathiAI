"""T-NEXT-1.1 cutover marker and OMS↔fund binding helpers."""
from __future__ import annotations

import json
import time as _time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

CUTOVER_VERSION = "t-next-1.1/1.0.0"
CUTOVER_POLICY = "RESET_PAPER_FUND_FOR_NEW_CANONICAL_ERA"
# Historical OMS rows are not silently migrated; new accounts open a fresh fund book.


@dataclass
class CutoverMarker:
    ledger_cutover_at: float
    source_branch: str
    source_sha: str
    initial_cash_policy: str
    initial_positions_policy: str
    historical_migration: str
    version: str = CUTOVER_VERSION

    def to_public(self) -> dict:
        return asdict(self)


DEFAULT_MARKER = CutoverMarker(
    ledger_cutover_at=_time.time(),
    source_branch="feature/t-next-1-canonical-paper-ledger",
    source_sha="278600bbaefb6ddaacc4546c8f8c3f61eb3543d3",
    initial_cash_policy="opening_deposit_equals_paper_account_starting_cash",
    initial_positions_policy="empty_at_fund_open_fifo_from_fills_after_cutover",
    historical_migration="HISTORICAL_STATE_NOT_MIGRATED",
)


def fund_id_for_account(account_id: str) -> str:
    """Deterministic fund id bound 1:1 to a paper account after cutover."""
    return f"fund_{account_id}"


def write_cutover_marker(path: Path | str, marker: CutoverMarker | None = None) -> dict:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    m = marker or DEFAULT_MARKER
    data = m.to_public()
    p.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return data
