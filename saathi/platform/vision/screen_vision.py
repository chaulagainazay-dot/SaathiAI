"""Screen vision — analyse a screenshot with Gemini Vision so Saathi can "look at the screen".

Owner captures the current SaathiOS screen in the browser; the frame + a question are sent
here and answered by Gemini's multimodal model (same GOOGLE_API_KEY as chat, a vision-capable
model). Honest failure when no valid key. The image is used only for this one answer — not
stored, not logged, not sent anywhere but Google's endpoint.
"""
from __future__ import annotations

import base64
import re
from typing import Any

_MAX_B64 = 12_000_000   # ~9 MB image cap


def _strip_data_uri(b64: str) -> tuple[str, str]:
    m = re.match(r"^data:(image/[a-zA-Z0-9.+-]+);base64,(.*)$", b64 or "", re.S)
    if m:
        return m.group(1), m.group(2)
    return "image/jpeg", (b64 or "")


def analyze_image(image_b64: str, question: str = "") -> dict[str, Any]:
    import os
    from saathi import config
    key = os.getenv("GOOGLE_API_KEY", "")
    if not key or key.startswith("YOUR"):
        return {"available": False, "error": "NO_GOOGLE_API_KEY",
                "note": "Set a valid GOOGLE_API_KEY in .env to enable screen vision."}
    mime, data = _strip_data_uri(image_b64)
    if not data:
        return {"available": False, "error": "NO_IMAGE"}
    if len(data) > _MAX_B64:
        return {"available": False, "error": "IMAGE_TOO_LARGE"}
    try:
        base64.b64decode(data[:64] + "===")  # cheap validity probe
    except Exception:
        return {"available": False, "error": "BAD_IMAGE_B64"}

    model = os.getenv("GEMINI_VISION_MODEL") or os.getenv("GEMINI_MODEL") or getattr(config, "GEMINI_MODEL", "gemini-2.5-flash")
    prompt = (question or "").strip() or (
        "You are looking at a screenshot of the owner's SaathiOS finance screen. Describe what is "
        "shown and answer any implicit question about it. Be concise and factual; if it shows "
        "market/portfolio data, read the key numbers. Research/observation only — no financial advice.")
    try:
        import httpx
        r = httpx.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}",
            json={"contents": [{"parts": [
                {"text": prompt},
                {"inline_data": {"mime_type": mime, "data": data}},
            ]}]},
            timeout=60,
        )
        if r.status_code == 401:
            return {"available": False, "error": "GOOGLE_API_KEY_INVALID (401)"}
        r.raise_for_status()
        j = r.json()
        text = j["candidates"][0]["content"]["parts"][0]["text"]
        return {"available": True, "answer": text, "provider": f"gemini:{model}",
                "note": "Screen read by Gemini Vision · research/observation only, not advice."}
    except Exception as e:  # noqa: BLE001
        return {"available": False, "error": f"VISION_FAILED:{str(e)[:120]}"}
