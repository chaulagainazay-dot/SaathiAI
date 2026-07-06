"""Event → Evidence routing — the adapter layer of the bus.

Maps an event TYPE (glob) to the Evidence-department adapter that should absorb
it. This is the ONLY place that knows both events and evidence; products stay
ignorant of both. Register a route = plug a new event source into the whole
Learning pipeline. Unmatched events are still persisted (raw signal), they just
don't yet produce evidence — nothing is lost, and a route can be added later.
"""
from __future__ import annotations

import fnmatch


# event-type glob → evidence department (whose adapter converts the payload)
ROUTES: list[tuple[str, str]] = [
    ("episode.produced", "ai_studio"),
    ("video.*", "ai_studio"),
    ("essay.*", "pielts"),
    ("lesson.*", "pielts"),
    ("quiz.*", "pielts"),
    ("mistake.*", "pielts"),
    ("trade.*", "hcg"),
    ("signal.*", "hcg"),
    ("meal.*", "cafeteria"),
    ("inventory.*", "cafeteria"),
    ("booking.*", "travel"),
    ("lead.*", "travel"),
]


def department_for(event_type: str) -> str | None:
    for pattern, dept in ROUTES:
        if fnmatch.fnmatch(event_type, pattern):
            return dept
    return None


def to_evidence(ev) -> list:
    """Convert an Event to Evidence rows via the matched department adapter. Returns ids."""
    dept = department_for(ev.type)
    if not dept:
        return []
    from saathi.evidence.adapters import ADAPTERS
    from saathi.evidence.store import default_store
    adapter = ADAPTERS.get(dept)
    if not adapter:
        return []
    # the payload IS the native event the department adapter already understands;
    # carry the event's subject/project so evidence stays traceable to the event.
    native = dict(ev.payload)
    native.setdefault("episode", ev.subject)
    evs = adapter(native)
    for e in evs:
        if ev.project and not e.project:
            e.project = ev.project
    return default_store().record_many(evs)
