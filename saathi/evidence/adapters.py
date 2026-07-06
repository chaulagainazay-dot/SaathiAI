"""Evidence adapters — each department converts its NATIVE events into the
universal Evidence schema. This is what keeps departments independent while the
CEO still gets one queryable body of truth. Add a business = add an adapter; the
schema and the store never change.

Registry: `ADAPTERS[name](native_event) -> list[Evidence]`. AI Studio is fully
wired (it produces the data today); PIELTS / HCG / Cafeteria are real, minimal
converters ready for their native events.
"""
from __future__ import annotations

from saathi.evidence.schema import Evidence


# ── AI Studio ─────────────────────────────────────────────────────────────────
def from_studio_production(prod: dict) -> list[Evidence]:
    """A Studio Executive Production (as_dict) → one episode Evidence + per-stage rows.

    The episode row is the CEO-level summary; per-stage rows let the Learning
    layer see WHICH department moved a metric.
    """
    episode = prod.get("episode", "")
    project = (prod.get("plan") or {}).get("brand") or "mr_yeti"
    status = prod.get("status", "")
    render = prod.get("render_plan") or {}
    engines = render.get("engines") or {}
    provider_model = None
    try:
        from saathi import config
        provider_model = config.GEMINI_MODEL
    except Exception:
        provider_model = "gemini-3.5-flash"

    # per-stage confidence/cost mirrors the Control Room report
    stage_conf = {
        "research": _completeness(prod.get("research"), ("summary", "key_facts", "common_mistakes", "examples")),
        "creative": _completeness(prod.get("creative"), ("story_arc", "hook_style", "cta", "visual_direction")),
        "script": _completeness(prod.get("script"), ("hook", "scenes", "cta", "seo")),
        "storyboard": _completeness(prod.get("scene_package"), ("scenes",)),
        "render": _completeness(render, ("scenes", "adapter", "engines")),
        "publish": _completeness(prod.get("publish_plan"), ("platforms", "master")),
    }
    stage_cost = {"research": 0.01, "creative": 0.0, "script": 0.02, "storyboard": 0.0,
                  "render": 0.0, "publish": 0.0}
    overall = round(sum(stage_conf.values()) / len(stage_conf), 3) if stage_conf else 0.0
    total_cost = round(sum(stage_cost.values()), 3)
    targets = [p.get("platform") for p in (prod.get("publish_plan") or {}).get("platforms", [])]

    artifacts = {k: bool(prod.get(v)) for k, v in
                 {"research": "research", "creative": "creative", "script": "script",
                  "scene_package": "scene_package", "render_plan": "render_plan",
                  "publish_plan": "publish_plan"}.items()}

    episode_ev = Evidence(
        department="ai_studio", project=project, episode=episode, director="studio_executive",
        provider="gemini", model=provider_model, cost=total_cost, confidence=overall, status=status,
        metrics={"est_seconds": prod.get("est_seconds", 0), "publish_targets": targets,
                 "stage_confidence": stage_conf}, artifacts=artifacts)

    evs = [episode_ev]
    prov = {"research": "gemini", "creative": "gemini", "script": "gemini", "storyboard": "gemini",
            "render": f"{engines.get('image','pil-card')}+{engines.get('voice','say')}/{render.get('adapter','ffmpeg')}",
            "publish": "connectors"}
    for stage, conf in stage_conf.items():
        evs.append(Evidence(
            department="ai_studio", project=project, episode=episode, director=stage,
            provider=prov.get(stage, "gemini"),
            model=provider_model if stage in ("research", "creative", "script", "storyboard") else prov.get(stage, ""),
            cost=stage_cost.get(stage, 0.0), confidence=conf, status=status))
    return evs


# ── PIELTS ────────────────────────────────────────────────────────────────────
def from_pielts_essay(ev: dict) -> list[Evidence]:
    """A graded essay → Evidence (band as metric, prompt version, student improvement)."""
    return [Evidence(
        department="pielts", project="pielts", episode=ev.get("essay_id", ""),
        director="writing_evaluator", prompt_version=ev.get("prompt_version", ""),
        provider="gemini", model=ev.get("model", ""), confidence=float(ev.get("confidence", 0) or 0),
        status=ev.get("status", "graded"),
        metrics={"band": ev.get("band"), "improvement": ev.get("improvement"),
                 "corrections": ev.get("corrections", 0)},
        feedback={"student_rating": ev.get("student_rating")})]


# ── HCG Live Signal ───────────────────────────────────────────────────────────
def from_hcg_trade(ev: dict) -> list[Evidence]:
    """A trade signal outcome → Evidence (win/loss, return, risk)."""
    return [Evidence(
        department="hcg", project="hcg_signal", episode=ev.get("trade_id", ""),
        director="signal_engine", prompt_version=ev.get("prompt_version", ""),
        provider=ev.get("provider", ""), model=ev.get("model", ""),
        confidence=float(ev.get("confidence", 0) or 0), status=ev.get("result", ""),
        metrics={"return": ev.get("return"), "risk": ev.get("risk"), "reason": ev.get("reason")})]


# ── Cafeteria ─────────────────────────────────────────────────────────────────
def from_cafeteria_day(ev: dict) -> list[Evidence]:
    """A menu-day → Evidence (sales, waste, profit)."""
    return [Evidence(
        department="cafeteria", project="hcg_canteen", episode=ev.get("date", ""),
        director="menu_planner", status="closed",
        metrics={"sales": ev.get("sales"), "waste": ev.get("waste"),
                 "profit": ev.get("profit"), "visitors": ev.get("visitors")},
        feedback={"rating": ev.get("feedback")})]


def _completeness(artifact, fields) -> float:
    if not artifact:
        return 0.0
    filled = sum(1 for f in fields if artifact.get(f))
    return round(filled / len(fields), 3)


ADAPTERS = {
    "ai_studio": from_studio_production,
    "pielts": from_pielts_essay,
    "hcg": from_hcg_trade,
    "cafeteria": from_cafeteria_day,
}


def ingest(department: str, native_event: dict, *, store=None) -> list[str]:
    """Convert a native event via its adapter and persist. Returns evidence ids."""
    adapter = ADAPTERS.get(department)
    if not adapter:
        raise ValueError(f"no evidence adapter for department '{department}'")
    from saathi.evidence.store import default_store
    st = store or default_store()
    evs = adapter(native_event)
    return st.record_many(evs)
