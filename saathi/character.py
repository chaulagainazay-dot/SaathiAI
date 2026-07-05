"""Mr. Yeti Bible — the single character reference every renderer consumes.

Consistency is what turns a mascot into a brand. Flux, HyperFrames, Runway,
HeyGen, or the current PIL scene-card renderer all receive the SAME reference via
`visual_prefix()`, and the Creative Director draws voice/teaching style from
`BIBLE`. Change the character here, once, and every output follows.

Human-readable companion: docs/MR_YETI_BIBLE.md
"""
from __future__ import annotations

BIBLE = {
    "name": "Mr. Yeti",
    "biography": "A warm, patient Himalayan yeti who left the mountains to become the "
                 "world's friendliest IELTS teacher. He believes anyone can reach Band 9.",
    "personality": ["warm", "encouraging", "patient", "gently funny", "never condescending"],
    "teaching_philosophy": "One clear idea per lesson, a real example, then a tiny action. "
                           "Celebrate small wins; normalise mistakes as part of learning.",
    "catchphrases": ["Let's make this simple.", "You've got this, my friend.",
                     "One small step today.", "See? Not so scary."],
    "voice": {"provider_tone": "friendly", "pace": "calm and clear", "kokoro_voice": "af_heart"},
    "appearance": ("a friendly Himalayan yeti with soft white-and-cream fur, large kind dark "
                   "eyes, round glasses, a neat teal scarf, holding a wooden pointer"),
    "wardrobe": "round glasses and a teal scarf, sometimes a cardigan",
    "props": ["wooden pointer", "chalk", "a warm mug labelled 'Band 9'", "a small globe"],
    "classroom": ("a cosy wooden classroom with a green chalkboard, warm lamps, a small "
                  "bookshelf, and a window showing snowy peaks"),
    "palette": {"primary": "#6C3FCF", "accent": "#00BFA5", "dark": "#1a1a2e",
                "fur": "#F4F1EA"},
    "camera": ["slow zoom", "gentle pan", "steady medium shot on Mr. Yeti at the board"],
    "animation_rules": ["no jump cuts", "soft easing", "expressions match the lesson's emotion"],
    "style": "Pixar-quality 3D, warm soft lighting, shallow depth of field",
}


def visual_prefix() -> str:
    """Prepend to every image/video scene prompt so the character stays identical."""
    b = BIBLE
    return (f"{b['style']}. {b['name']}: {b['appearance']}. Classroom: {b['classroom']}. "
            f"Brand colors purple {b['palette']['primary']} and teal {b['palette']['accent']}. "
            "Consistent character across every scene.")


def scene_prompt(beat: str) -> str:
    return f"{visual_prefix()} Scene: {beat}. No on-screen text."


def voice_tone() -> str:
    return BIBLE["voice"]["provider_tone"]


def kokoro_voice() -> str:
    return BIBLE["voice"]["kokoro_voice"]
