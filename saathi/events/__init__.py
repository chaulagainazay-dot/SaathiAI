"""Saathi Event Bus — the single spine every product emits to. Products emit
Events; the bus routes them into the Evidence Store via business handlers.
"""
# Re-export the lightweight fabric types from saathi.events module (events.py file)
# Load it directly without going through this package to avoid circular import
import importlib.util
import os
import sys

# The events.py file is at saathi/events.py (sibling of the saathi/events/ directory)
_events_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "events.py")
spec = importlib.util.spec_from_file_location("saathi._events_fabric", _events_path)
_events_py = importlib.util.module_from_spec(spec)
sys.modules["saathi._events_fabric"] = _events_py  # register in sys.modules for dataclass resolution
spec.loader.exec_module(_events_py)

Event = _events_py.Event
EventBus = _events_py.EventBus
bus = _events_py.bus
PublishReport = _events_py.PublishReport
WILDCARD = _events_py.WILDCARD
STORAGE_WARNING = _events_py.STORAGE_WARNING
STORAGE_CRITICAL = _events_py.STORAGE_CRITICAL

# Re-export the SQLite-backed bus and routes.
# NOTE: importing the submodule `saathi.events.bus` binds the name `bus` on this
# package to that MODULE, shadowing the fabric singleton instance set above
# (`bus = _events_py.bus`). Producers and tests do `from saathi.events import bus`
# expecting the fabric INSTANCE (with .subscribe/.publish/.publish_sync), so we
# re-bind `bus` to the fabric instance AFTER these submodule imports.
from saathi.events.bus import EventBus as BusEventBus, default_bus
from saathi.events.routes import ROUTES, business_for, department_for, to_evidence

# Restore the fabric singleton as the canonical `saathi.events.bus` attribute.
bus = _events_py.bus

# Storage Intelligence event vocabulary (dotted namespace) — feeds Mission Control
STORAGE_EVENTS = {
    "warning": "storage.warning",
    "cleanup_started": "storage.cleanup.started",
    "cleanup_finished": "storage.cleanup.finished",
    "cleanup_failed": "storage.cleanup.failed",
    "render_blocked": "storage.render.blocked",
    "render_allowed": "storage.render.allowed",
    "disk_full": "storage.disk.full",
    "archive_completed": "storage.archive.completed",
    "lifecycle_deleted": "storage.lifecycle.deleted",
    "lifecycle_protected": "storage.lifecycle.protected",
}

__all__ = ["Event", "EventBus", "bus", "PublishReport", "default_bus", "ROUTES", "business_for", "department_for", "to_evidence", "STORAGE_EVENTS", "WILDCARD", "STORAGE_WARNING", "STORAGE_CRITICAL"]
