"""M17.14 mission-scheduler interval runner — opt-in, overlap-safe, restart-safe.

Mirrors the M17.11 monitor scheduler adapter (a single named daemon-thread job with
idempotent registration + overlap protection). It does NOT execute anything itself:
one tick = one deterministic `MissionScheduler.sweep()` (reconcile stale leases →
generate due occurrences → dispatch through the MissionEngine).

Default DISABLED. Enable locally with `SAATHI_MISSION_SCHEDULER_ENABLED=1`. There is
no repository evidence for safe automatic production enablement, so it is opt-in; no
OS launch agent / cron / cloud scheduler is created here.
"""
from __future__ import annotations

import os
import threading

from saathi.application_harness import run_ledger as L
from saathi.application_harness.scheduler import MissionScheduler

JOB_ID = "mission.scheduler.sweep"
DEFAULT_INTERVAL_SEC = 60


def is_enabled() -> bool:
    return os.environ.get("SAATHI_MISSION_SCHEDULER_ENABLED") == "1"


class SchedulerRunner:
    def __init__(self, scheduler: MissionScheduler | None = None,
                 ledger: L.RunLedger | None = None):
        self.ledger = ledger or L.default_ledger()
        self.scheduler = scheduler or MissionScheduler(ledger=self.ledger)
        self._tick_lock = threading.Lock()
        self._registered = False
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def tick(self, *, now=None, worker="scheduler") -> dict:
        """One deterministic sweep. Overlapping ticks are skipped (not queued); a
        sweep exception is isolated and never fakes success."""
        if not self._tick_lock.acquire(blocking=False):
            return {"skipped": "overlap"}
        try:
            self.ledger._event("harness.scheduler.tick_started", {"job": JOB_ID})
            try:
                out = self.scheduler.sweep(now=now, worker=worker)
            except Exception as e:
                self.ledger._event("harness.scheduler.tick_failed",
                                   {"job": JOB_ID, "error": str(e)[:120]})
                return {"sweep_failed": str(e)[:120]}
            self.ledger._event("harness.scheduler.tick_finished",
                               {"job": JOB_ID,
                                "generated": len(out.get("generated", [])),
                                "dispatched": len(out.get("dispatched", []))})
            return out
        finally:
            self._tick_lock.release()

    def register_once(self) -> bool:
        if self._registered:
            return False
        self._registered = True
        return True

    def start(self, *, interval_sec: int = DEFAULT_INTERVAL_SEC) -> dict:
        if not is_enabled():
            return {"started": False, "reason": "disabled"}
        if self._thread is not None and self._thread.is_alive():
            return {"started": False, "reason": "already_running"}
        self.register_once()

        def _loop():
            while not self._stop.wait(interval_sec):
                try:
                    self.tick()
                except Exception:
                    pass                     # a tick must never kill the loop
        self._thread = threading.Thread(target=_loop, name=JOB_ID, daemon=True)
        self._thread.start()
        return {"started": True, "job": JOB_ID, "interval_sec": interval_sec}

    def stop(self) -> None:
        self._stop.set()

    def schedule_status(self) -> dict:
        return {"job": JOB_ID, "enabled": is_enabled(),
                "running": bool(self._thread and self._thread.is_alive()),
                "interval_sec": DEFAULT_INTERVAL_SEC,
                "health": self.scheduler.health()}


_default: SchedulerRunner | None = None


def default_runner() -> SchedulerRunner:
    global _default
    if _default is None:
        _default = SchedulerRunner()
    return _default
