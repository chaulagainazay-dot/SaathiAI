"""M17.11 harness monitor scheduler adapter — deterministic interval sweeps +
notification dispatch, wired the SAME way the storage watchdog runs
(`svc.start(interval_seconds=60)`). NOT a new scheduler framework: a single named
daemon-thread job with idempotent registration, overlap protection, restart-safe
delivery recovery, and event-bus evidence.

Default DISABLED. Enable locally with `SAATHI_HARNESS_MONITOR_ENABLED=1` (there is
no repository evidence for safe automatic enablement, so it is opt-in). One tick =
monitor sweep → enqueue deliveries → dispatch. A failed dispatch never corrupts the
sweep; a failed sweep never fabricates delivery success.
"""
from __future__ import annotations

import os
import threading

from saathi.application_harness import run_ledger as L
from saathi.application_harness.run_monitor import HarnessRunMonitor
from saathi.application_harness.notify import NotificationDispatcher

JOB_ID = "harness.monitor.sweep"          # stable identity — never duplicated
DEFAULT_INTERVAL_SEC = 60


def is_enabled() -> bool:
    return os.environ.get("SAATHI_HARNESS_MONITOR_ENABLED") == "1"


class MonitorScheduler:
    """One monitor+dispatch job. `register_once`/`start` are idempotent — a second
    call is a no-op, so duplicate registration is impossible."""

    def __init__(self, ledger: L.RunLedger | None = None, *,
                 monitor: HarnessRunMonitor | None = None,
                 dispatcher: NotificationDispatcher | None = None):
        self.ledger = ledger or L.default_ledger()
        self.monitor = monitor or HarnessRunMonitor(self.ledger)
        self.dispatcher = dispatcher or NotificationDispatcher(self.ledger)
        self._tick_lock = threading.Lock()   # overlap protection
        self._registered = False
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def tick(self, *, now=None, worker="scheduler") -> dict:
        """One deterministic pass. Overlapping ticks are skipped (not queued). A
        sweep failure is isolated from dispatch and never fakes delivery success."""
        if not self._tick_lock.acquire(blocking=False):
            return {"skipped": "overlap"}
        try:
            self.ledger._event("harness.monitor.sweep_started", {"job": JOB_ID})
            sweep = None
            try:
                sweep = self.monitor.sweep(now=now)
            except Exception as e:
                self.ledger._event("harness.monitor.sweep_failed",
                                   {"job": JOB_ID, "error": str(e)[:120]})
                return {"sweep_failed": str(e)[:120]}
            dispatch = self.dispatcher.run_once(now=now, worker=worker)
            self.ledger._event("harness.monitor.sweep_finished",
                               {"job": JOB_ID, "recovered": len(sweep.get("recovered", [])),
                                "delivered": len(dispatch.get("delivered", []))})
            return {"sweep": sweep, "dispatch": dispatch}
        finally:
            self._tick_lock.release()

    def register_once(self) -> bool:
        """Idempotent registration. Returns True the first time only."""
        if self._registered:
            return False
        self._registered = True
        return True

    def start(self, *, interval_sec: int = DEFAULT_INTERVAL_SEC) -> dict:
        """Launch the interval loop ONLY if enabled and not already running.
        Idempotent — a second call is a no-op. Restart-safe: stale delivery leases
        are reclaimed and retry_wait deliveries resume from persisted timing."""
        if not is_enabled():
            return {"started": False, "reason": "disabled"}
        if self._thread is not None and self._thread.is_alive():
            return {"started": False, "reason": "already_running"}
        self.register_once()
        # restart recovery: return crash-after-claim leases to retry_wait
        self.ledger.reclaim_stale_deliveries()

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
                "delivery_health": self.ledger.delivery_health()}


_default: MonitorScheduler | None = None


def default_scheduler() -> MonitorScheduler:
    global _default
    if _default is None:
        _default = MonitorScheduler()
    return _default
