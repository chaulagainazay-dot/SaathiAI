"""M62.2 — deterministic replay engine.

Replays a stored or in-memory bar series with a stable, reproducible ordering and
NO wall-clock dependency (step-driven). Exposes events through a stable interface
for future backtest/simulation layers. It places NO orders and touches no broker.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Iterable

from saathi.platform.market_data.models import MDBar, Timeframe


class ReplayStatus(str, Enum):
    READY = "READY"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    STOPPED = "STOPPED"
    DONE = "DONE"


@dataclass
class ReplayEvent:
    index: int
    bar: MDBar
    correlation_id: str
    dataset_version: str


class ReplayEngine:
    """Step-mode deterministic replay. `bars` are sorted by start_time once, so the
    same input always yields the same event order regardless of insertion order."""

    def __init__(self, bars: Iterable[MDBar], *, correlation_id: str, dataset_version: str = "unknown"):
        # deterministic ordering (stable): by start_time then instrument
        self._bars = sorted(bars, key=lambda b: (b.start_time.timestamp(), b.instrument))
        self.correlation_id = correlation_id
        self.dataset_version = dataset_version
        self._pos = 0
        self.status = ReplayStatus.READY

    @property
    def position(self) -> int:
        return self._pos

    @property
    def total(self) -> int:
        return len(self._bars)

    def start(self) -> None:
        if self.status in (ReplayStatus.READY, ReplayStatus.PAUSED):
            self.status = ReplayStatus.RUNNING

    def pause(self) -> None:
        if self.status == ReplayStatus.RUNNING:
            self.status = ReplayStatus.PAUSED

    def resume(self) -> None:
        if self.status == ReplayStatus.PAUSED:
            self.status = ReplayStatus.RUNNING

    def stop(self) -> None:
        self.status = ReplayStatus.STOPPED

    def reset(self) -> None:
        self._pos = 0
        self.status = ReplayStatus.READY

    def checkpoint(self) -> dict[str, Any]:
        return {"position": self._pos, "status": self.status.value,
                "correlation_id": self.correlation_id, "dataset_version": self.dataset_version,
                "total": self.total}

    def restore(self, checkpoint: dict[str, Any]) -> None:
        pos = int(checkpoint.get("position", 0))
        if pos < 0 or pos > self.total or checkpoint.get("dataset_version") != self.dataset_version:
            raise ValueError("corrupted or mismatched replay checkpoint")
        self._pos = pos
        self.status = ReplayStatus.PAUSED if 0 < pos < self.total else ReplayStatus.READY

    def step(self, count: int = 1) -> list[ReplayEvent]:
        """Emit up to `count` events. No-op if not running/ready. Terminates at DONE."""
        if self.status in (ReplayStatus.STOPPED, ReplayStatus.DONE, ReplayStatus.PAUSED):
            return []
        if self.status == ReplayStatus.READY:
            self.start()
        out: list[ReplayEvent] = []
        for _ in range(max(0, count)):
            if self._pos >= self.total:
                self.status = ReplayStatus.DONE
                break
            b = self._bars[self._pos]
            out.append(ReplayEvent(index=self._pos, bar=b,
                                   correlation_id=self.correlation_id, dataset_version=self.dataset_version))
            self._pos += 1
        if self._pos >= self.total:
            self.status = ReplayStatus.DONE
        return out

    def run_to_end(self) -> list[ReplayEvent]:
        events: list[ReplayEvent] = []
        self.start()
        while self.status == ReplayStatus.RUNNING:
            batch = self.step(1)
            if not batch:
                break
            events.extend(batch)
        return events
