"""Capability Improvement Registry + Experiment Registry (M2 Phase 3).

Memory stores knowledge; the **Capability Improvement Registry** stores
*improvements* — so years later you can answer "how has AI Studio improved?"
and "which improvements made Mission Control faster?". Organizational learning.

The **Experiment Registry** prevents regressions: rather than replacing behavior
immediately, run current vs new as an A/B test, measure, then promote the winner.

Both SQLite-backed, testable in isolation (AP-12): injected clock, no network.
"""
from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable


class ImprovementStatus(str, Enum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    IMPLEMENTED = "implemented"
    REJECTED = "rejected"


@dataclass
class ImprovementProposal:
    improvement_id: int
    capability: str
    improvement: str
    evidence: str
    expected_benefit: str
    confidence: float
    status: ImprovementStatus
    created_at: float
    resolved_at: float | None


class ExperimentStatus(str, Enum):
    RUNNING = "running"
    COMPLETE = "complete"


@dataclass
class Experiment:
    experiment_id: int
    capability: str
    control: str
    variant: str
    control_metric: float
    variant_metric: float
    status: ExperimentStatus
    winner: str | None      # "control" | "variant" | None


_SCHEMA = """
CREATE TABLE IF NOT EXISTS capability_improvements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    capability TEXT NOT NULL,
    improvement TEXT NOT NULL,
    evidence TEXT DEFAULT '',
    expected_benefit TEXT DEFAULT '',
    confidence REAL DEFAULT 0.0,
    status TEXT NOT NULL DEFAULT 'proposed',
    created_at REAL NOT NULL,
    resolved_at REAL
);
CREATE INDEX IF NOT EXISTS idx_imp_capability ON capability_improvements(capability);
CREATE INDEX IF NOT EXISTS idx_imp_status ON capability_improvements(status);

CREATE TABLE IF NOT EXISTS experiments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    capability TEXT NOT NULL,
    control TEXT NOT NULL,
    variant TEXT NOT NULL,
    control_metric REAL DEFAULT 0.0,
    variant_metric REAL DEFAULT 0.0,
    status TEXT NOT NULL DEFAULT 'running',
    winner TEXT,
    created_at REAL NOT NULL,
    higher_is_better INTEGER DEFAULT 1
);
"""


class CapabilityImprovementRegistry:
    def __init__(self, db_path: "str | Path", now: Callable[[], float] = time.time):
        Path(str(db_path)).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(db_path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(_SCHEMA)
        self.db.commit()
        self._now = now

    # ── improvements ──────────────────────────────────────────────────────
    def propose(self, *, capability: str, improvement: str, evidence: str = "",
                expected_benefit: str = "", confidence: float = 0.0) -> int:
        cur = self.db.execute(
            "INSERT INTO capability_improvements (capability, improvement, evidence,"
            " expected_benefit, confidence, created_at) VALUES (?,?,?,?,?,?)",
            (capability, improvement, evidence, expected_benefit, confidence, self._now()),
        )
        self.db.commit()
        return cur.lastrowid

    def set_status(self, improvement_id: int, status: ImprovementStatus) -> ImprovementProposal:
        self.db.execute(
            "UPDATE capability_improvements SET status=?, resolved_at=? WHERE id=?",
            (status.value, self._now(), improvement_id),
        )
        self.db.commit()
        return self.get(improvement_id)

    def approve(self, improvement_id: int) -> ImprovementProposal:
        return self.set_status(improvement_id, ImprovementStatus.APPROVED)

    def implement(self, improvement_id: int) -> ImprovementProposal:
        return self.set_status(improvement_id, ImprovementStatus.IMPLEMENTED)

    def reject(self, improvement_id: int) -> ImprovementProposal:
        return self.set_status(improvement_id, ImprovementStatus.REJECTED)

    def get(self, improvement_id: int) -> ImprovementProposal | None:
        r = self.db.execute("SELECT * FROM capability_improvements WHERE id=?",
                            (improvement_id,)).fetchone()
        return self._imp(r) if r else None

    def by_capability(self, capability: str) -> list[ImprovementProposal]:
        rows = self.db.execute(
            "SELECT * FROM capability_improvements WHERE capability=? ORDER BY created_at",
            (capability,)).fetchall()
        return [self._imp(r) for r in rows]

    def implemented_for(self, capability: str) -> list[ImprovementProposal]:
        return [i for i in self.by_capability(capability)
                if i.status is ImprovementStatus.IMPLEMENTED]

    # ── experiments (A/B) ─────────────────────────────────────────────────
    def start_experiment(self, *, capability: str, control: str, variant: str,
                         higher_is_better: bool = True) -> int:
        cur = self.db.execute(
            "INSERT INTO experiments (capability, control, variant, created_at,"
            " higher_is_better) VALUES (?,?,?,?,?)",
            (capability, control, variant, self._now(), int(higher_is_better)),
        )
        self.db.commit()
        return cur.lastrowid

    def conclude_experiment(self, experiment_id: int, control_metric: float,
                            variant_metric: float) -> Experiment:
        row = self.db.execute("SELECT higher_is_better FROM experiments WHERE id=?",
                              (experiment_id,)).fetchone()
        hib = bool(row["higher_is_better"])
        variant_wins = variant_metric > control_metric if hib else variant_metric < control_metric
        winner = "variant" if variant_wins else "control"
        self.db.execute(
            "UPDATE experiments SET control_metric=?, variant_metric=?, status=?,"
            " winner=? WHERE id=?",
            (control_metric, variant_metric, ExperimentStatus.COMPLETE.value, winner, experiment_id),
        )
        self.db.commit()
        return self.get_experiment(experiment_id)

    def get_experiment(self, experiment_id: int) -> Experiment | None:
        r = self.db.execute("SELECT * FROM experiments WHERE id=?", (experiment_id,)).fetchone()
        if r is None:
            return None
        return Experiment(
            experiment_id=r["id"], capability=r["capability"], control=r["control"],
            variant=r["variant"], control_metric=r["control_metric"],
            variant_metric=r["variant_metric"], status=ExperimentStatus(r["status"]),
            winner=r["winner"],
        )

    @staticmethod
    def _imp(r) -> ImprovementProposal:
        return ImprovementProposal(
            improvement_id=r["id"], capability=r["capability"],
            improvement=r["improvement"], evidence=r["evidence"],
            expected_benefit=r["expected_benefit"], confidence=r["confidence"],
            status=ImprovementStatus(r["status"]), created_at=r["created_at"],
            resolved_at=r["resolved_at"],
        )
