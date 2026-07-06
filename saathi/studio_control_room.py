"""AI Studio OS — the CEO Control Room report.

ONE structured read that the dashboard renders as the whole content factory:
the production pipeline (stage by stage), Director health, per-stage cost &
confidence, provider monitor, queue, content memory, and studio health. It runs
the Studio Executive once, then derives everything from the artifacts each
Director already emitted — no new model calls, no fabricated numbers. Confidence
is an honest artifact-completeness score (which fields the Director actually
filled), not a guess. Every business (Mr. Yeti / PIELTS / HCG / cafeteria)
plugs the same pipeline in; only the Directors, prompts and curriculum differ.
"""
from __future__ import annotations

# the pipeline, in order — the spine the dashboard draws
STAGES = ["curriculum", "research", "creative", "script", "storyboard",
          "render", "publish", "memory", "learning"]

# per-stage cost estimate (USD) — LLM stages cost a Gemini call, local stages are free
_STAGE_COST = {"curriculum": 0.0, "research": 0.01, "creative": 0.0, "script": 0.02,
               "storyboard": 0.0, "render": 0.0, "publish": 0.0, "memory": 0.0, "learning": 0.0}

# which artifact fields must be present for a stage to score 100% confidence
_COMPLETENESS = {
    "curriculum": ("topic", "skill", "objective"),
    "research": ("summary", "key_facts", "common_mistakes", "examples"),
    "creative": ("story_arc", "hook_style", "cta", "visual_direction"),
    "script": ("hook", "scenes", "cta", "seo"),
    "storyboard": ("scenes",),
    "render": ("scenes", "adapter", "engines"),
    "publish": ("platforms", "master"),
}

_DIRECTORS = ["research", "creative", "script", "storyboard", "render", "publishing", "learning"]


def _confidence(stage: str, artifact: dict) -> float:
    """Honest completeness: fraction of the stage's required fields that are filled."""
    fields = _COMPLETENESS.get(stage)
    if not fields:
        return 1.0 if artifact else 0.0
    if not artifact:
        return 0.0
    filled = sum(1 for f in fields if artifact.get(f))
    return round(filled / len(fields), 2)


def _provider_for(stage: str, render_plan: dict) -> str:
    """Which engine actually served the stage (for the Provider Monitor)."""
    if stage in ("research", "creative", "script", "storyboard"):
        try:
            from saathi import config
            return config.GEMINI_MODEL
        except Exception:
            return "gemini-3.5-flash"
    if stage == "render":
        eng = render_plan.get("engines", {}) if render_plan else {}
        return f"{eng.get('image', 'pil-card')}+{eng.get('voice', 'say')}/{render_plan.get('adapter', 'ffmpeg')}"
    if stage == "publish":
        return "connectors"
    return "local"


def _director_health() -> dict:
    """11/11-style roster: each Director is healthy if the Registry can route to it."""
    roster = []
    try:
        from saathi.production.director_registry import default_registry
        reg = default_registry()
        caps = {"research": "research", "creative": "creative_brief", "script": "script_generation",
                "storyboard": "storyboard_generation", "render": "render_planning",
                "publishing": "publishing", "learning": "learning"}
        for name in _DIRECTORS:
            cap = caps.get(name, name)
            best = reg.best(cap)
            roster.append({"name": name, "healthy": best is not None,
                           "provider": _provider_for("research" if name != "render" else "render", {}),
                           "source": best.source if best else "missing"})
    except Exception:
        roster = [{"name": n, "healthy": False, "provider": "?", "source": "missing"} for n in _DIRECTORS]
    healthy = sum(1 for d in roster if d["healthy"])
    return {"roster": roster, "healthy": healthy, "total": len(roster)}


def report() -> dict:
    """Run the Studio Executive once → the full Control Room report."""
    from saathi.studio_directors import default_executive
    prod = default_executive().produce().as_dict()
    render_plan = prod.get("render_plan") or {}

    artifacts = {
        "curriculum": prod.get("plan") or {},
        "research": prod.get("research") or {},
        "creative": prod.get("creative") or {},
        "script": prod.get("script") or {},
        "storyboard": prod.get("scene_package") or {},
        "render": render_plan,
        "publish": prod.get("publish_plan") or {},
    }

    # reached = how far the pipeline actually got (status maps to a stage index)
    status = prod.get("status", "planned")
    reached_idx = {"planned": 1, "researched": 2, "briefed": 3, "scripted": 4,
                   "storyboarded": 5, "ready": 7, "revision": 5}.get(status, 1)

    stages, total_cost, conf_sum, conf_n = [], 0.0, 0.0, 0
    for i, name in enumerate(STAGES):
        art = artifacts.get(name)
        done = art is not None and (name not in _COMPLETENESS or bool(art)) and i < reached_idx
        if name in ("memory", "learning"):
            done = False  # emitted after produce()/later
        conf = _confidence(name, art) if art is not None else 0.0
        cost = _STAGE_COST.get(name, 0.0) if done else 0.0
        total_cost += cost
        if done and name in _COMPLETENESS:
            conf_sum += conf; conf_n += 1
        stages.append({
            "stage": name,
            "status": "done" if done else ("blocked" if name == "render" and not render_plan and status != "planned" else "pending"),
            "confidence": conf,
            "cost": round(cost, 3),
            "provider": _provider_for(name, render_plan),
            "has_artifact": bool(art),
        })

    directors = _director_health()

    # content memory snapshot
    try:
        from saathi.content_memory import default_memory
        mem = default_memory()
        memory = {"count": mem.count(), "recent": mem.recent_topics(8),
                  "skills_week": mem.skills_this_week()}
    except Exception:
        memory = {"count": 0, "recent": [], "skills_week": {}}

    # queue snapshot
    try:
        from saathi.studio_store import default_store
        st = default_store()
        queue = {"counts": st.queue_counts(), "recent": st.recent(6)}
    except Exception:
        queue = {"counts": {}, "recent": []}

    overall_conf = round(conf_sum / conf_n, 2) if conf_n else 0.0
    health = {
        "studio": round((directors["healthy"] / directors["total"]) if directors["total"] else 0, 2),
        "directors": f"{directors['healthy']}/{directors['total']}",
        "episodes": memory["count"],
        "queue_waiting": queue["counts"].get("in_progress", 0) + queue["counts"].get("awaiting_approval", 0),
        "status": status,
    }

    return {
        "episode": prod.get("episode", ""),
        "day": prod.get("day", 0),
        "topic": prod.get("topic", ""),
        "status": status,
        "est_seconds": prod.get("est_seconds", 0),
        "stages": stages,
        "directors": directors,
        "cost_total": round(total_cost, 3),
        "confidence_overall": overall_conf,
        "artifacts": {k: bool(v) for k, v in artifacts.items()},
        "publish_targets": [p.get("platform") for p in artifacts["publish"].get("platforms", [])],
        "memory": memory,
        "queue": queue,
        "health": health,
    }
