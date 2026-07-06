"""Mission Health — where the business is weak, not just how much we know.

Knowledge Coverage says how complete our memory is. Mission Health goes further:
per business function (knowledge, marketing, finance, operations, automation,
learning, evidence, revenue tracking) it scores how developed that function is,
from real signals in the Knowledge Graph + Evidence Store + Learning + Events.
Honest — an empty function reads low, so the CEO sees the gaps immediately.
"""
from __future__ import annotations


def _has(counts: dict, *types) -> int:
    return sum(counts.get(t, 0) for t in types)


def mission_health(mission: dict) -> dict:
    mid = mission.get("id", "")
    dept = mission.get("department", "")

    # knowledge graph
    counts, coverage = {}, 0.0
    try:
        from saathi.missions.knowledge import default_graph
        g = default_graph()
        counts = g.counts(mid)
        coverage = g.coverage(mid)["overall"]
    except Exception:
        pass

    # evidence + learning + events for this mission's namespace
    ev_count, rec_count = 0, 0
    try:
        from saathi.evidence.store import default_store as es
        ev_count = len(es().query(project=mission.get("key", ""), limit=500)) if mission.get("key") else 0
    except Exception:
        pass
    try:
        from saathi.learning.recommendation import default_store as rs
        rec_count = len([r for r in rs().list(limit=200) if not dept or r.get("department") == dept])
    except Exception:
        pass

    def cap(x, target):
        return round(min(1.0, x / target), 2) if target else 0.0

    dims = {
        "knowledge": coverage,
        "marketing": cap(_has(counts, "social_channel") + _has(counts, "account"), 3),
        "finance": cap(_has(counts, "revenue"), 1) * 0.6 + (0.4 if _has(counts, "kpi") else 0),
        "revenue_tracking": 1.0 if _has(counts, "revenue") else 0.0,
        "operations": cap(_has(counts, "task", "workflow", "service", "product"), 4),
        "automation": cap(_has(counts, "automation", "workflow"), 3),
        "evidence": cap(ev_count, 30),
        "learning": cap(rec_count, 5),
    }
    dims = {k: round(v, 2) for k, v in dims.items()}
    overall = round(sum(dims.values()) / len(dims), 2)
    weakest = min(dims, key=dims.get)
    return {"overall": overall, "dimensions": dims, "weakest": weakest,
            "evidence_count": ev_count, "recommendation_count": rec_count}
