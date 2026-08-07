"""Compute budget manager — fail closed when exhausted."""
from __future__ import annotations

import time
from typing import Any

from saathi.platform.tg.research_orchestrator.errors import OrchestratorError
from saathi.platform.tg.research_orchestrator.models import (
    AUTHORITY_VALUES,
    DEFAULT_COMPUTE_BUDGET_UNITS,
    BudgetState,
)
from saathi.platform.tg.research_orchestrator.storage import OrchestratorStore


class ComputeBudgetManager:
    BUDGET_ID = "default"

    def __init__(self, store: OrchestratorStore, total_units: float = DEFAULT_COMPUTE_BUDGET_UNITS):
        self.store = store
        row = self.store.fetchone("SELECT * FROM orch_budget WHERE id=?", (self.BUDGET_ID,))
        if not row:
            self.store.execute(
                "INSERT INTO orch_budget(id, total_units, reserved_units, spent_units, state, updated_at) "
                "VALUES(?,?,?,?,?,?)",
                (self.BUDGET_ID, float(total_units), 0.0, 0.0, BudgetState.AVAILABLE.value, time.time()),
            )

    def status(self) -> dict[str, Any]:
        row = self.store.fetchone("SELECT * FROM orch_budget WHERE id=?", (self.BUDGET_ID,))
        assert row
        remaining = float(row["total_units"]) - float(row["reserved_units"]) - float(row["spent_units"])
        return {
            "ok": True,
            "total_units": row["total_units"],
            "reserved_units": row["reserved_units"],
            "spent_units": row["spent_units"],
            "remaining_units": remaining,
            "state": row["state"],
            **AUTHORITY_VALUES,
        }

    def reserve(self, units: float) -> dict[str, Any]:
        units = float(units)
        st = self.status()
        if st["remaining_units"] < units - 1e-9:
            self.store.execute(
                "UPDATE orch_budget SET state=?, updated_at=? WHERE id=?",
                (BudgetState.EXHAUSTED.value, time.time(), self.BUDGET_ID),
            )
            raise OrchestratorError(
                "BUDGET_EXHAUSTED",
                f"Need {units} units, remaining {st['remaining_units']}",
                detail=st,
            )
        self.store.execute(
            "UPDATE orch_budget SET reserved_units=reserved_units+?, state=?, updated_at=? WHERE id=?",
            (units, BudgetState.RESERVED.value, time.time(), self.BUDGET_ID),
        )
        return self.status()

    def commit(self, units: float) -> dict[str, Any]:
        units = float(units)
        self.store.execute(
            "UPDATE orch_budget SET reserved_units=MAX(0, reserved_units-?), "
            "spent_units=spent_units+?, updated_at=? WHERE id=?",
            (units, units, time.time(), self.BUDGET_ID),
        )
        st = self.status()
        if st["remaining_units"] <= 0:
            self.store.execute(
                "UPDATE orch_budget SET state=?, updated_at=? WHERE id=?",
                (BudgetState.EXHAUSTED.value, time.time(), self.BUDGET_ID),
            )
        else:
            self.store.execute(
                "UPDATE orch_budget SET state=?, updated_at=? WHERE id=?",
                (BudgetState.AVAILABLE.value, time.time(), self.BUDGET_ID),
            )
        return self.status()

    def release_reservation(self, units: float) -> dict[str, Any]:
        units = float(units)
        self.store.execute(
            "UPDATE orch_budget SET reserved_units=MAX(0, reserved_units-?), updated_at=? WHERE id=?",
            (units, time.time(), self.BUDGET_ID),
        )
        return self.status()
