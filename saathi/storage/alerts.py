"""Storage Telegram Alerts — makes the system feel alive (SES-019A Part 7).

Subscribes to the ``storage.*`` Event Fabric events and formats human, glanceable
Telegram messages so you know what's happening without opening Mission Control.

Testable in isolation (AP-12): the sender is injected. In production it is
wired to ``saathi.telegram_bot._send``; in tests it's a list append.
"""
from __future__ import annotations

from typing import Callable

from saathi.events import Event, EventBus, STORAGE_EVENTS


def _gb(n_bytes: float) -> str:
    return f"{n_bytes / 1e9:.1f} GB"


def format_warning(payload: dict) -> str:
    pct = payload.get("disk_pct", 0.0)
    lines = [
        "⚠️ Storage Warning",
        "",
        f"Disk Usage: {pct:.1%}",
        "Rendering Paused",
    ]
    if "recoverable_bytes" in payload:
        lines.append(f"Estimated Recoverable: {_gb(payload['recoverable_bytes'])}")
    if payload.get("cleanup_scheduled"):
        lines.append(f"Cleanup Scheduled: {payload['cleanup_scheduled']}")
    if "active_jobs" in payload:
        lines.append(f"Current Jobs: {payload['active_jobs']}")
    lines += ["", "Reply:", "/cleanup", "/status", "/override"]
    return "\n".join(lines)


def format_critical(payload: dict) -> str:
    pct = payload.get("disk_pct", 0.0)
    return (
        "🚨 Storage CRITICAL\n\n"
        f"Disk Usage: {pct:.1%}\n"
        "Emergency cleanup running.\n"
        "Rendering halted.\n\n"
        "Reply: /status /override"
    )


def format_cleanup_finished(payload: dict) -> str:
    return (
        "✅ Cleanup finished\n\n"
        f"Run: {payload.get('kind', '?')}\n"
        f"Files deleted: {payload.get('deleted', 0)}\n"
        f"Protected: {payload.get('protected', 0)}\n"
        f"Freed: {_gb(payload.get('bytes_freed', 0))}"
    )


def format_render_blocked(payload: dict) -> str:
    return (
        "⛔ Render postponed — not enough disk\n\n"
        f"Need: {_gb(payload.get('required_bytes', 0))}\n"
        f"Have: {_gb(payload.get('free_bytes', 0))}\n"
        f"Cleanup required: {_gb(payload.get('shortfall_bytes', 0))}"
    )


# event name → formatter
_FORMATTERS: dict[str, Callable[[dict], str]] = {
    STORAGE_EVENTS["warning"]: format_warning,
    STORAGE_EVENTS["cleanup_finished"]: format_cleanup_finished,
    STORAGE_EVENTS["render_blocked"]: format_render_blocked,
    "storage_warning": format_warning,     # underscore alias from the Disk Watchdog
    "storage_critical": format_critical,
}


class StorageAlerts:
    """Subscribes to the bus and pushes formatted alerts through ``send``."""

    def __init__(self, send: Callable[[str], None]):
        self._send = send

    def handle(self, event: Event) -> None:
        fmt = _FORMATTERS.get(event.name)
        if fmt is not None:
            self._send(fmt(event.payload))

    def register(self, bus: EventBus) -> None:
        for name in _FORMATTERS:
            bus.subscribe(name, self.handle)


def wire_to_telegram(bus: EventBus) -> StorageAlerts:
    """Production wiring: connect storage alerts to the live Telegram bot."""
    from saathi import telegram_bot
    alerts = StorageAlerts(send=telegram_bot._send)
    alerts.register(bus)
    return alerts
