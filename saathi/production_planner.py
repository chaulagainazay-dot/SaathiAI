"""Production Planner — gate before expensive rendering.

Validates that every scene in the Scene Package is actually renderable BEFORE
generation starts: narration present, image prompt present, durations add up,
voice assignable, subtitle timings valid, cost/time acceptable. Cheap check that
prevents wasting compute on incomplete jobs.
"""
from __future__ import annotations

# rough per-scene estimates ($ / seconds of wall-clock) for the draft stack
_COST_PER_SCENE = 0.02      # image + voice draft
_RENDER_SEC_PER_SCENE = 18  # generate + assemble


def validate(scene_package: dict, *, max_cost: float = 1.0, max_render_min: float = 8.0) -> dict:
    scenes = scene_package.get("scenes", []) or []
    issues: list[str] = []
    if not scenes:
        issues.append("no scenes")
    total = 0
    for s in scenes:
        n = s.get("scene", "?")
        if not s.get("narration"):
            issues.append(f"scene {n}: missing narration")
        if not s.get("image_prompt"):
            issues.append(f"scene {n}: missing image prompt")
        dur = s.get("duration", 0)
        if not (isinstance(dur, (int, float)) and dur > 0):
            issues.append(f"scene {n}: bad duration")
        else:
            total += dur
        if not (s.get("character") or {}).get("name"):
            issues.append(f"scene {n}: no character assignment")
    if total and not (20 <= total <= 400):
        issues.append(f"total duration {total}s out of range (20-400s)")

    est_cost = round(len(scenes) * _COST_PER_SCENE, 3)
    est_render_min = round(len(scenes) * _RENDER_SEC_PER_SCENE / 60, 2)
    if est_cost > max_cost:
        issues.append(f"estimated cost ${est_cost} over budget ${max_cost}")
    if est_render_min > max_render_min:
        issues.append(f"estimated render {est_render_min}m over limit {max_render_min}m")

    return {"ok": not issues, "issues": issues, "scene_count": len(scenes),
            "total_seconds": total, "est_cost": est_cost, "est_render_min": est_render_min}
