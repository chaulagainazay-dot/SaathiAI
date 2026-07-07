"""Provider Scheduler + Cost Optimizer + Retry policy.

Saathi decides which provider generates each scene — cheapest-then-best that has
credits today, per scene, so a single episode can span Google Flow + Seedance +
HeyGen + local render and nobody watching knows. If a provider fails, the retry
policy retries once then switches to the next available provider — production never
stops because one API is down.
"""
from __future__ import annotations


def assign_scenes(n_scenes: int, *, manager=None, kind: str = "", reserve: bool = True) -> dict:
    """Cost-optimised per-scene provider assignment. Reserves credits as it goes."""
    from saathi.production_automation.credits import default_manager
    cm = manager or default_manager()
    assignments, cost = [], 0.0
    used = {}
    for i in range(n_scenes):
        avail = cm.available(need=1, kind=kind)
        chosen = None
        for p in avail:
            if not reserve or cm.reserve(p["name"], 1):
                chosen = p
                break
        if not chosen:
            chosen = {"name": "ffmpeg", "cost": 0.0, "quality_tier": 3}   # unlimited safety net
            if reserve:
                cm.reserve("ffmpeg", 1)
        assignments.append({"scene": i + 1, "provider": chosen["name"],
                            "quality_tier": chosen.get("quality_tier", 3), "cost": chosen.get("cost", 0.0)})
        cost += chosen.get("cost", 0.0)
        used[chosen["name"]] = used.get(chosen["name"], 0) + 1
    return {"assignments": assignments, "est_cost": round(cost, 3), "providers_used": used,
            "scene_count": n_scenes}


def fallback_chain(kind: str = "", *, manager=None) -> list[str]:
    """The ordered provider chain the retry engine walks (cheapest-quality-first)."""
    from saathi.production_automation.credits import default_manager
    cm = manager or default_manager()
    return [p["name"] for p in cm.available(kind=kind)] or ["ffmpeg"]


def retry_plan(provider: str, *, kind: str = "", manager=None) -> dict:
    """On failure: retry the same provider once, then switch to the next in the chain."""
    chain = fallback_chain(kind, manager=manager)
    nxt = None
    for i, p in enumerate(chain):
        if p == provider and i + 1 < len(chain):
            nxt = chain[i + 1]
            break
    if nxt is None:
        nxt = next((p for p in chain if p != provider), "ffmpeg")
    return {"provider": provider, "policy": "retry_once_then_switch", "switch_to": nxt}
