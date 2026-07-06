"""Event → Evidence routing — the adapter layer of the bus.

Maps an event TYPE (glob) to the BUSINESS that owns it. The business handler is
the only code that understands both the event's semantics and Evidence; products
stay ignorant of both. Register a route = plug a new event source into the whole
Learning pipeline. Unmatched events are still persisted (raw signal), they just
don't yet produce evidence — nothing is lost, and a route can be added later.
"""
from __future__ import annotations

import fnmatch


# event-type glob → business key (whose handler converts the event)
ROUTES: list[tuple[str, str]] = [
    ("episode.produced", "ai_studio"),
    ("render.completed", "ai_studio"),
    ("publish.completed", "ai_studio"),
    ("video.*", "ai_studio"),
    ("*.analytics", "ai_studio"),
    ("essay.*", "pielts"),
    ("lesson.*", "pielts"),
    ("quiz.*", "pielts"),
    ("mistake.*", "pielts"),
    ("revision.*", "pielts"),
    ("word.*", "pielts"),
    ("streak.*", "pielts"),
    ("user.feedback", "pielts"),
    ("trade.*", "hcg"),
    ("signal.*", "hcg"),
    ("daily.pnl", "hcg"),
    ("monthly.pnl", "hcg"),
    ("meal.*", "cafeteria"),
    ("inventory.*", "cafeteria"),
    ("waste.*", "cafeteria"),
    ("customer.feedback", "cafeteria"),
    ("booking.*", "travel"),
    ("lead.*", "travel"),
    ("quotation.*", "travel"),
    ("visa.*", "travel"),
    ("client.feedback", "travel"),
    ("*.lead", "travel"),
]


def business_for(event_type: str) -> str | None:
    for pattern, biz in ROUTES:
        if fnmatch.fnmatch(event_type, pattern):
            return biz
    return None


# backward-compat alias (business == evidence department here)
department_for = business_for


# subscription.started is shared — resolve by source, not type
_AMBIGUOUS = {"subscription.started", "subscription.cancelled"}


def to_evidence(ev) -> list:
    """Convert an Event to Evidence rows via the owning business handler. Returns ids."""
    from saathi.businesses import HANDLERS
    biz = ev.source if ev.type in _AMBIGUOUS and ev.source in HANDLERS else business_for(ev.type)
    handler = HANDLERS.get(biz) if biz else None
    if not handler:
        return []
    evs = handler(ev.type, ev.payload or {}, subject=ev.subject)
    for e in evs:
        if ev.project and not e.project:
            e.project = ev.project
    if not evs:
        return []
    from saathi.evidence.store import default_store
    return default_store().record_many(evs)
