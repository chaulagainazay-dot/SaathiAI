"""Mission overview — the Executive Dashboard data for one Mission.

Because a Mission's `key` IS the evidence/event `project` and its `department` is
the evidence department, the whole loop aggregates per Mission with no extra
tagging: evidence rollup, recent activity, Mission-specific learning
recommendations, and event volume — all filtered to this Mission.
"""
from __future__ import annotations


def overview(mission: dict) -> dict:
    key = mission.get("key", "")
    dept = mission.get("department", "")

    # evidence for this Mission (by project == key)
    evidence_rows, ev_count, ev_cost, ev_conf = [], 0, 0.0, 0.0
    try:
        from saathi.evidence.store import default_store as ev_store
        st = ev_store()
        evidence_rows = st.query(project=key, limit=12) if key else []
        all_rows = st.query(project=key, limit=500) if key else []
        ev_count = len(all_rows)
        if all_rows:
            ev_cost = round(sum(r.get("cost", 0) or 0 for r in all_rows), 3)
            ev_conf = round(sum(r.get("confidence", 0) or 0 for r in all_rows) / len(all_rows), 3)
    except Exception:
        pass

    # learning recommendations aimed at this Mission's department
    recs = []
    try:
        from saathi.learning.recommendation import default_store as rec_store
        allrecs = rec_store().list(limit=100)
        recs = [r for r in allrecs if not dept or r.get("department") == dept][:10]
    except Exception:
        pass

    # events emitted by this Mission (source == department/business)
    events, evt_count = [], 0
    try:
        from saathi.events.bus import default_bus
        bus = default_bus()
        src = dept
        events = bus.query(source=src, limit=10) if src else []
        evt_count = len(bus.query(source=src, limit=500)) if src else 0
    except Exception:
        pass

    # digital-twin artifacts (departments / briefing / roadmap) + timeline history
    twin = None
    try:
        from saathi.missions.twin import default_store as twin_store
        twin = twin_store().get(mission.get("id", ""))
    except Exception:
        pass
    timeline = []
    try:
        from saathi.missions.timeline import default_store as tl_store
        timeline = tl_store().list(mission.get("id", ""), limit=30)
    except Exception:
        pass

    # knowledge coverage — how much of the business we hold in memory
    coverage = None
    try:
        from saathi.missions.knowledge import default_graph
        coverage = default_graph().coverage(mission.get("id", ""))
    except Exception:
        pass

    pending = sum(1 for r in recs if r.get("status") == "pending")
    return {
        "mission": mission,
        "twin": twin,
        "timeline": timeline,
        "knowledge": coverage,
        "kpis": {
            "evidence": ev_count,
            "events": evt_count,
            "avg_confidence": ev_conf,
            "cost": ev_cost,
            "pending_recommendations": pending,
        },
        "recent_evidence": evidence_rows,
        "recommendations": recs,
        "recent_events": events,
    }
