"""Saathi Event Bus — the single spine every product emits to. Products emit
Events; the bus routes them into the Evidence Store via business handlers.
"""
from saathi.events.bus import Event, EventBus, default_bus
from saathi.events.routes import ROUTES, business_for, department_for, to_evidence

__all__ = ["Event", "EventBus", "default_bus", "ROUTES", "business_for", "department_for", "to_evidence"]
