"""Creative Director — the module that lifts quality without changing renderers.

Turns a Topic + Script into a directed Brief: overall style, voice tone, music
mood, camera language, and a per-scene shot list (label · visual prompt ·
narration · seconds). Rendering reads the brief, so better direction beats a
better renderer. Uses the Model Router when available; deterministic fallback
maps the script's beats to scenes so it always produces a usable brief offline.
"""
from __future__ import annotations

import json


def direct(topic: str, script: dict, *, quality: str = "draft") -> dict:
    brief = _from_model(topic, script)
    if brief and brief.get("scenes"):
        return brief
    return _deterministic(topic, script)


def _from_model(topic: str, script: dict) -> dict | None:
    try:
        from saathi.infrastructure.llm import generate
        from saathi.infrastructure.model_router import ModelLabel
    except Exception:
        return None
    try:
        prompt = (
            f"You are the creative director for a Mr. Yeti IELTS explainer about '{topic}'. "
            f"Script: {json.dumps(script)[:900]}. Reply ONLY as JSON: "
            '{"style","voice_tone","music_mood","camera",'
            '"scenes":[{"label","prompt","narration","seconds"}]}. 4-6 scenes.')
        out = generate(ModelLabel.STANDARD, prompt, "Reply with ONLY JSON.", max_tokens=800).text
        b = json.loads(out.strip().strip("`").replace("json", "", 1))
        return _shape(b, topic, script)
    except Exception:
        return None


def _deterministic(topic: str, script: dict) -> dict:
    scenes = [{"label": "Intro", "prompt": f"warm classroom, Mr Yeti greets, topic {topic}",
               "narration": script.get("hook", f"Let's learn {topic}."), "seconds": 5}]
    for i, t in enumerate(script.get("teaching", []), 1):
        scenes.append({"label": f"Teaching {i}", "prompt": f"whiteboard illustration of {topic}",
                       "narration": t, "seconds": 8})
    scenes.append({"label": "Example", "prompt": "example sentence on screen, Mr Yeti points",
                   "narration": script.get("examples", "Here's an example."), "seconds": 6})
    scenes.append({"label": "Practice", "prompt": "pielts.web.app call to action, friendly Yeti wave",
                   "narration": script.get("cta", "Practice on pielts.web.app."), "seconds": 5})
    return {"style": "Pixar classroom", "voice_tone": "friendly", "music_mood": "curious",
            "camera": "slow zoom", "scenes": [s for s in scenes if s["narration"]]}


def _shape(b: dict, topic: str, script: dict) -> dict:
    scenes = b.get("scenes") or []
    for s in scenes:
        s.setdefault("label", "Scene")
        s.setdefault("prompt", topic)
        s.setdefault("narration", "")
        s["seconds"] = int(s.get("seconds", 6) or 6)
    return {"style": b.get("style", "Pixar classroom"),
            "voice_tone": b.get("voice_tone", "friendly"),
            "music_mood": b.get("music_mood", "curious"),
            "camera": b.get("camera", "slow zoom"),
            "scenes": [s for s in scenes if s["narration"]] or _deterministic(topic, script)["scenes"]}
