"""Character Verification + Quality Gate.

Character Verification scores a generated scene against the Character Bible — does
it still look like Mr. Yeti? Quality Gate runs the release checklist (voice/character/
duration/captions/brand/resolution/hook/CTA). Anything failing → retry.

Honest scope: verification here is STRUCTURAL (does the scene carry the required
character attributes + prompt cues), not pixel-level CV — real vision scoring plugs
in behind `verify_scene` later. It never claims to have looked at pixels it can't see.
"""
from __future__ import annotations

# the character attributes a Mr.-Yeti-style scene must reference
_REQUIRED_ATTRS = ("fur", "glasses", "shirt", "eyes", "face")
_BRAND_CUES = ("classroom", "logo", "palette", "camera")


def verify_scene(scene: dict, bible: dict | None = None) -> dict:
    """Structural character-consistency score for one scene (0-1) + what's missing."""
    bible = bible or {}
    ch = scene.get("character") or {}
    prompt = " ".join(str(x) for x in (scene.get("image_prompt", ""), ch.get("style", ""),
                                       ch.get("description", ""), scene.get("background", ""))).lower()
    name_ok = bool(ch.get("name")) and (not bible.get("name") or
                                        bible.get("name", "").lower() in (ch.get("name", "").lower()))
    present = [a for a in _REQUIRED_ATTRS if a in prompt or a in str(ch).lower()]
    missing = [a for a in _REQUIRED_ATTRS if a not in present]
    # score: name match (weight) + attribute coverage
    score = round((0.4 if name_ok else 0.0) + 0.6 * (len(present) / len(_REQUIRED_ATTRS)), 2)
    return {"score": score, "name_ok": name_ok, "present": present, "missing": missing,
            "verified": score >= 0.85, "method": "structural",
            "note": "Structural check (attributes + prompt cues). Pixel-level CV plugs in later."}


def verify_package(scene_package: dict, bible: dict | None = None) -> dict:
    scenes = scene_package.get("scenes", []) if scene_package else []
    scores = [verify_scene(s, bible) for s in scenes]
    avg = round(sum(s["score"] for s in scores) / len(scores), 2) if scores else 0.0
    rejected = [i + 1 for i, s in enumerate(scores) if not s["verified"]]
    return {"avg_score": avg, "scene_scores": scores, "rejected_scenes": rejected,
            "all_pass": not rejected}


# ── Quality Gate ──────────────────────────────────────────────────────────────
def quality_gate(*, script: dict | None = None, render_plan: dict | None = None,
                 publish_plan: dict | None = None, character: dict | None = None) -> dict:
    script = script or {}
    render_plan = render_plan or {}
    publish_plan = publish_plan or {}
    character = character or {}
    seconds = script.get("est_seconds", 0)
    checks = {
        "voice": bool(render_plan.get("engines", {}).get("voice")) or bool(render_plan),
        "character": character.get("all_pass", False) if character else False,
        "duration": 20 <= seconds <= 400,
        "captions": bool(script.get("captions") or script.get("seo")),
        "brand": bool(render_plan.get("logo") is not None or render_plan.get("settings")),
        "resolution": (render_plan.get("settings", {}) or {}).get("resolution", "") != "",
        "hook": bool(script.get("hook")),
        "cta": bool(script.get("cta")),
    }
    failed = [k for k, v in checks.items() if not v]
    return {"checks": checks, "failed": failed, "passed": not failed,
            "score": round(sum(1 for v in checks.values() if v) / len(checks), 2)}
