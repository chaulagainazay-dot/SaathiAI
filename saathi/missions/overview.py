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

    # mission health — per-function scores
    health = None
    try:
        from saathi.missions.health import mission_health
        health = mission_health(mission)
    except Exception:
        pass

    # workflows + open tasks
    workflows, open_tasks = [], []
    try:
        from saathi.missions.workflow import default_store as wf_store
        ws = wf_store()
        workflows = ws.list(mission.get("id", ""))
        open_tasks = ws.open_tasks(mission.get("id", ""))
    except Exception:
        pass

    # revenue from the knowledge graph
    revenue = None
    try:
        from saathi.missions.knowledge import default_graph
        revs = default_graph().nodes(mission.get("id", ""), node_type="revenue")
        amounts = [r["data"].get("amount") for r in revs if isinstance(r.get("data"), dict)]
        amounts = [a for a in amounts if isinstance(a, (int, float))]
        if amounts:
            revenue = {"total": sum(amounts), "entries": len(amounts)}
    except Exception:
        pass

    # CEO pipeline: research → proposal → execution → evidence
    proposal = None
    try:
        from saathi.missions.proposal import default_store as p_store
        proposal = p_store().latest(mission.get("id", ""))
    except Exception:
        pass
    pipeline = {
        "research": "done" if twin else "pending",
        "proposal": ("accepted" if (proposal or {}).get("status") == "accepted"
                     else "ready" if proposal else "pending"),
        "execution": "active" if mission.get("status") == "active" and workflows else (
            "active" if mission.get("status") == "active" else "pending"),
        "evidence": "flowing" if ev_count > 0 else "pending",
    }

    # top priorities — from weakest health dims + open tasks + pending recs
    priorities = []
    if health:
        for dim, v in sorted((health.get("dimensions") or {}).items(), key=lambda x: x[1])[:2]:
            if v < 0.6:
                priorities.append(f"Raise {dim.replace('_', ' ')} ({int(v*100)}%)")
    for t in open_tasks[:2]:
        priorities.append(f"{t['title']}" + (f" ({t['director']})" if t.get("director") else ""))
    for r in recs:
        if r.get("status") == "pending":
            priorities.append(r.get("recommendation", "")[:60]); break

    # brand identity + active voice (what Directors read)
    brand, active_voice, voice_count = {}, None, 0
    try:
        from saathi.missions.brand import default_store as b_store, default_brand
        bs = b_store()
        brand = bs.get_brand(mission.get("id", "")) or default_brand(mission)
        active_voice = bs.active_voice(mission.get("id", ""))
        voice_count = len(bs.list_voices(mission.get("id", "")))
    except Exception:
        pass

    pending = sum(1 for r in recs if r.get("status") == "pending")
    return {
        "mission": mission,
        "twin": twin,
        "timeline": timeline,
        "knowledge": coverage,
        "health": health,
        "brand": brand,
        "active_voice": active_voice,
        "voice_count": voice_count,
        "workflows": workflows,
        "open_tasks": open_tasks,
        "revenue": revenue,
        "pipeline": pipeline,
        "priorities": priorities[:5],
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
