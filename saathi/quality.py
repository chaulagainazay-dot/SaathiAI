"""Quality levels — the pipeline is constant; only providers change.

Draft   ≈ $0    Kokoro/say · Flux/card · FFmpeg
Standard≈ $0.20 OpenAI TTS · Flux Pro · FFmpeg
Premium ≈ $3-10 ElevenLabs · Runway/Kling · HeyGen/Hyperframes

v0.4.1 ships DRAFT fully wired and local-first. Standard/Premium are declared
here so AI Studio can select by policy the moment those providers are added —
no pipeline change required.
"""
from __future__ import annotations

DRAFT, STANDARD, PREMIUM = "draft", "standard", "premium"

POLICY = {
    DRAFT: {"voice": ("kokoro", "say"), "images": ("flux", "card"),
            "render": "ffmpeg", "est_cost": 0.0},
    STANDARD: {"voice": ("openai", "kokoro", "say"), "images": ("flux", "card"),
               "render": "ffmpeg", "est_cost": 0.20},
    PREMIUM: {"voice": ("elevenlabs", "openai"), "images": ("flux",),
              "render": "ffmpeg", "est_cost": 6.0},
}


def policy(level: str) -> dict:
    return POLICY.get((level or DRAFT).lower(), POLICY[DRAFT])
