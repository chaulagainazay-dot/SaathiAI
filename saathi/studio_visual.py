"""Visual Department — Storyboard/Character/Camera/Motion/Image Directors.

Consumes the Episode Script, produces a SCENE PACKAGE: the missing artifact of
the Studio. Each scene is fully specified (purpose, character block, camera,
motion, image prompt, animation prompt, transition, subtitle style, music,
assets) so the Renderer needs NO intelligence — it just reads the package.

- Character Director owns the Mr. Yeti Bible → injects consistency into every scene.
- Camera / Motion Directors own fixed vocabularies (no AI re-inventing per scene).
- Image Director owns the provider list (Flux → SDXL → PIL) like the Model Router.
Storyboard prompt `mr-yeti.storyboard` in the AI Lab; Gemini 3.5; deterministic fallback.
"""
from __future__ import annotations

import json

# Camera Director vocabulary (fixed — not AI-invented each time)
_SHOTS = ["medium", "close-up", "wide", "medium", "close-up"]
_MOVES = ["slow zoom in", "gentle pan left", "static", "push in", "slow zoom out"]
# Motion Director vocabulary
_MOTIONS = ["ken burns", "subtle parallax", "slide-in cards", "background drift", "particle sparkle"]
_TRANSITIONS = ["soft crossfade", "whip pan", "match cut", "fade through white", "quick cut"]
# Image Director provider chain (first available wins, like Model Router)
IMAGE_PROVIDERS = ["flux", "sdxl", "pil-card"]


def character_block() -> dict:
    """Character Director — the ONLY owner of Mr. Yeti's look, injected everywhere."""
    try:
        from saathi.character import BIBLE
        return {"name": BIBLE["name"], "fur": BIBLE["palette"].get("fur", "#F4F1EA"),
                "wardrobe": BIBLE.get("wardrobe", ""), "props": BIBLE.get("props", []),
                "classroom": BIBLE.get("classroom", ""), "palette": BIBLE.get("palette", {}),
                "style": BIBLE.get("style", "Pixar-quality 3D, warm soft lighting")}
    except Exception:
        return {"name": "Mr. Yeti", "style": "Pixar-quality 3D, warm soft lighting"}


def _image_prompt(visual: str) -> str:
    try:
        from saathi.character import scene_prompt
        return scene_prompt(visual)
    except Exception:
        return f"Pixar-style Mr. Yeti IELTS teacher. Scene: {visual}. Warm classroom. No on-screen text."


def _purpose(i: int, total: int) -> str:
    if i == 1:
        return "Hook"
    if i >= total:
        return "CTA"
    return "Teaching"


def scene_package(script: dict) -> dict:
    scenes_in = script.get("scenes", []) or []
    ch = character_block()

    # Storyboard Director (AI enrich, optional)
    emap = {}
    try:
        from saathi.studio_directors import _gen_json
        enriched = _gen_json(
            "mr-yeti.storyboard",
            json.dumps({"scenes": [{"n": s.get("n"), "narration": s.get("narration", ""),
                                    "visual": s.get("visual", "")} for s in scenes_in]})[:1300],
            "You are the Storyboard Director for a Mr. Yeti IELTS episode. For each scene give a vivid "
            "image prompt, camera, motion, transition, effects. Reply ONLY as JSON: "
            '{"scenes":[{"n","image_prompt","camera","motion","transition","effects"}]}.')
        if enriched and isinstance(enriched.get("scenes"), list):
            emap = {s.get("n"): s for s in enriched["scenes"] if isinstance(s, dict)}
    except Exception:
        pass

    total = len(scenes_in)
    pkg = []
    for i, s in enumerate(scenes_in, 1):
        n = s.get("n", i)
        e = emap.get(n, {})
        pkg.append({
            "scene": n, "purpose": _purpose(i, total), "duration": int(s.get("seconds", 12) or 12),
            "narration": s.get("narration", ""),
            "character": ch,                                        # Character Director
            "camera": {"shot": _SHOTS[(i - 1) % len(_SHOTS)],       # Camera Director
                       "movement": e.get("camera") or s.get("camera") or _MOVES[(i - 1) % len(_MOVES)]},
            "background": s.get("visual", "warm classroom"),
            "motion": e.get("motion") or _MOTIONS[(i - 1) % len(_MOTIONS)],   # Motion Director
            "image_prompt": e.get("image_prompt") or _image_prompt(s.get("visual", "")),   # Image Director
            "animation_prompt": e.get("effects") or s.get("animation") or "gentle highlight on key word",
            "transition": e.get("transition") or _TRANSITIONS[(i - 1) % len(_TRANSITIONS)],
            "subtitle_style": "lower-third, high-contrast, key word accented",
            "music": "curious underscore, low volume",
            "image_providers": IMAGE_PROVIDERS,                     # Image Director chain
            "assets": [],
        })
    return {"scenes": pkg, "scene_count": len(pkg),
            "est_seconds": sum(s["duration"] for s in pkg), "character": ch}
