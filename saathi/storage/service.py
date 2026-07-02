"""Storage Service — assembles Storage Intelligence into one live service (SES-019A).

This is the wiring layer that turns the tested components into a running
capability. It composes everything on ONE shared Event Fabric (AP-13):

    DiskWatchdog ─┐
    CleanupEngine ┼─▶ Event Fabric ─▶ MissionControlState (dashboard snapshot)
    Predictive  ─┘                 └▶ StorageAlerts ─▶ Telegram

Closes the safety loop: at 95% the watchdog's emergency hook triggers a real
cleanup pass. ``tick()`` is the unit the 1-minute poll calls — testable
directly, no threads. ``start()`` runs that poll on a daemon thread.

Independently testable (AP-12): storage root, bus, and telegram toggle injected.
"""
from __future__ import annotations

import shutil
import threading
import time
from pathlib import Path

from saathi.events import EventBus, bus as global_bus
from saathi.storage.db import StorageDB
from saathi.storage.lifecycle import LifecycleEngine
from saathi.storage.watchdog import DiskWatchdog, WatchdogLevel
from saathi.storage.cleanup import CleanupEngine
from saathi.storage.predictive import PredictiveStorageEngine
from saathi.storage.alerts import StorageAlerts
from saathi.mission_control import MissionControlState


class StorageService:
    def __init__(
        self,
        storage_root: "str | Path",
        db_path: "str | Path | None" = None,
        bus: EventBus | None = None,
        enable_telegram: bool = False,
        telegram_send=None,
    ):
        self.root = Path(storage_root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.bus = bus or global_bus
        self.db = StorageDB(str(db_path or (self.root / "storage.db")))
        self.lifecycle = LifecycleEngine()
        self.cleanup = CleanupEngine(
            self.root, self.lifecycle, self.db, publish=self.bus.publish_sync
        )
        self.watchdog = DiskWatchdog(
            self.db,
            usage_reader=lambda: _disk_usage(self.root),
            on_emergency=self._emergency_cleanup,
            publish=self.bus.publish_sync,
        )
        self.predictive = PredictiveStorageEngine(
            free_reader=lambda: shutil.disk_usage(self.root).free,
            publish=self.bus.publish_sync,
        )
        self.mission_control = MissionControlState()
        self.mission_control.register(self.bus)

        # Alerts: real Telegram in production, injected sender in tests.
        if telegram_send is not None:
            StorageAlerts(send=telegram_send).register(self.bus)
        elif enable_telegram:
            from saathi.storage.alerts import wire_to_telegram
            wire_to_telegram(self.bus)

        self._stop = threading.Event()

    def _emergency_cleanup(self) -> None:
        # At 95% the watchdog calls this — a real cleanup pass, not just an alert.
        self.cleanup.nightly()

    def tick(self) -> WatchdogLevel:
        """One monitoring cycle — call every 60s."""
        return self.watchdog.check()

    def snapshot(self) -> dict:
        return self.mission_control.snapshot()

    def start(self, interval_seconds: int = 60) -> None:
        """Run the watchdog poll on a daemon thread."""
        def _loop():
            while not self._stop.is_set():
                try:
                    self.tick()
                except Exception:
                    pass  # a monitoring hiccup must never crash the service
                self._stop.wait(interval_seconds)

        threading.Thread(target=_loop, daemon=True).start()

    def stop(self) -> None:
        self._stop.set()


def _disk_usage(path):
    from saathi.storage.watchdog import DiskUsage
    total, used, free = shutil.disk_usage(path)
    return DiskUsage(total=total, used=used, free=free)


# Process-wide singleton, created on first use by the running server.
_service: StorageService | None = None


def get_storage_service(storage_root: "str | Path | None" = None, **kw) -> StorageService:
    global _service
    if _service is None:
        from saathi import config
        root = storage_root or (config.ROOT / "storage")
        _service = StorageService(root, **kw)
    return _service
