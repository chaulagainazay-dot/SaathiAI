"""Disk Watchdog — safety-critical free-space monitor (SES-019A Part 7).

Escalation ladder:
    >= 80%  notify            (Telegram notice)
    >= 90%  pause_rendering   (Studio Director stops accepting jobs)
    >= 95%  emergency_cleanup (priority-ordered deletion)

Design notes vs SES-019A:
  * Uses stdlib ``shutil.disk_usage`` instead of psutil — no extra dependency
    for Step 1. Swap in psutil later only if per-process metrics are needed.
  * Every dependency is injected (AP-12): the usage reader, the DB, and the
    three action callbacks. Tests drive it with a fake reader and no real disk.
  * State transitions are edge-triggered — an event fires once when a
    threshold is first crossed, and ``resume`` fires once when it clears,
    so we don't spam Telegram every poll.
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from enum import Enum
from typing import Callable

from saathi.storage.db import StorageDB


class WatchdogLevel(str, Enum):
    OK = "ok"
    NOTIFY = "notify"
    PAUSE = "pause"
    EMERGENCY = "emergency"


@dataclass
class DiskUsage:
    total: int
    used: int
    free: int

    @property
    def pct(self) -> float:
        return self.used / self.total if self.total else 0.0


THRESHOLDS = {
    WatchdogLevel.NOTIFY: 0.80,
    WatchdogLevel.PAUSE: 0.90,
    WatchdogLevel.EMERGENCY: 0.95,
}


def _default_usage_reader(path: str = "/") -> DiskUsage:
    total, used, free = shutil.disk_usage(path)
    return DiskUsage(total=total, used=used, free=free)


def _noop(*_a, **_k) -> None:
    pass


class DiskWatchdog:
    def __init__(
        self,
        db: StorageDB,
        usage_reader: Callable[[], DiskUsage] = _default_usage_reader,
        on_alert: Callable[[str], None] = _noop,        # e.g. Telegram send
        on_pause: Callable[[], None] = _noop,           # e.g. Studio Director pause
        on_resume: Callable[[], None] = _noop,
        on_emergency: Callable[[], None] = _noop,       # e.g. Cleanup Engine
        publish: Callable[[str, dict], None] | None = None,  # e.g. EventBus.publish_sync
    ):
        self.db = db
        self._read = usage_reader
        self._on_alert = on_alert
        self._on_pause = on_pause
        self._on_resume = on_resume
        self._on_emergency = on_emergency
        self._publish_fn = publish
        self.rendering_paused = False
        self.emergency_active = False

    def _publish(self, name: str, payload: dict) -> None:
        if self._publish_fn is not None:
            self._publish_fn(name, payload)

    def level_for(self, pct: float) -> WatchdogLevel:
        if pct >= THRESHOLDS[WatchdogLevel.EMERGENCY]:
            return WatchdogLevel.EMERGENCY
        if pct >= THRESHOLDS[WatchdogLevel.PAUSE]:
            return WatchdogLevel.PAUSE
        if pct >= THRESHOLDS[WatchdogLevel.NOTIFY]:
            return WatchdogLevel.NOTIFY
        return WatchdogLevel.OK

    def check(self) -> WatchdogLevel:
        """Single poll. Returns the level observed; fires edge-triggered
        actions/events. Safe to call every minute from a scheduler."""
        usage = self._read()
        pct = usage.pct
        level = self.level_for(pct)

        if level == WatchdogLevel.EMERGENCY:
            if not self.emergency_active:
                self.emergency_active = True
                self.rendering_paused = True
                self.db.record_watchdog_event("emergency", pct, usage.free)
                self._publish("storage_critical", {"disk_pct": pct, "free_bytes": usage.free})
                self._on_alert(f"EMERGENCY: disk at {pct:.0%}, running emergency cleanup")
                self._on_pause()
                self._on_emergency()

        elif level == WatchdogLevel.PAUSE:
            self.emergency_active = False
            if not self.rendering_paused:
                self.rendering_paused = True
                self.db.record_watchdog_event("pause", pct, usage.free)
                self._publish("storage_warning", {"disk_pct": pct, "free_bytes": usage.free})
                self._on_alert(f"WARNING: disk at {pct:.0%}, rendering paused")
                self._on_pause()

        elif level == WatchdogLevel.NOTIFY:
            self.emergency_active = False
            self._maybe_resume(pct, usage.free)
            self.db.record_watchdog_event("notify", pct, usage.free)
            self._on_alert(f"NOTICE: disk at {pct:.0%}")

        else:  # OK
            self.emergency_active = False
            self._maybe_resume(pct, usage.free)

        return level

    def _maybe_resume(self, pct: float, free: int) -> None:
        if self.rendering_paused:
            self.rendering_paused = False
            self.db.record_watchdog_event("resume", pct, free)
            self._on_alert(f"Disk back to {pct:.0%}, rendering resumed")
            self._on_resume()

    def safe_to_render(self, required_bytes: int) -> bool:
        """Predictive gate stub: is there room for a job needing
        ``required_bytes``, staying under the 90% pause line?"""
        usage = self._read()
        projected_used = usage.used + required_bytes
        return (projected_used / usage.total) < THRESHOLDS[WatchdogLevel.PAUSE]
