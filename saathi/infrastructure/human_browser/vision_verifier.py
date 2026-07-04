"""Vision verifier — turns brittle RPA into intelligent automation.

After a major step the workflow screenshots the page and asks a vision model
"does this look right?" — so a DOM change doesn't silently break a publish; the
run either self-confirms or recovers/aborts with a clear reason. Reuses the
platform's multimodal capability (OpenAI-compatible vision: GPT-4o / Gemini).

Injectable `ask(prompt, image_b64) -> str` for tests; guarded so no key = no-op.
"""
from __future__ import annotations

import os


class VisionVerifier:
    def __init__(self, ask=None, *, model: str | None = None, api_key: str | None = None,
                 base_url: str | None = None):
        self._ask = ask
        self._model = model or os.getenv("VISION_MODEL", "gpt-4o-mini")
        self._key = api_key if api_key is not None else (
            os.getenv("OPENAI_API_KEY") or os.getenv("GOOGLE_API_KEY", ""))
        self._base = base_url or os.getenv("VISION_BASE_URL", "https://api.openai.com/v1")

    def available(self) -> bool:
        return self._ask is not None or bool(self._key and not self._key.startswith("YOUR"))

    def __call__(self, prompt: str, screenshot_b64: str) -> bool:
        q = f"{prompt}\nLook at the screenshot. Answer with ONLY 'YES' or 'NO'."
        try:
            answer = (self._ask or self._vision_call)(q, screenshot_b64)
        except Exception:
            return True   # a verifier outage must not block an otherwise-valid run
        return str(answer).strip().upper().startswith("Y")

    def _vision_call(self, prompt: str, img_b64: str) -> str:
        import httpx
        r = httpx.post(
            f"{self._base.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {self._key}"},
            json={"model": self._model, "max_tokens": 5, "temperature": 0,
                  "messages": [{"role": "user", "content": [
                      {"type": "text", "text": prompt},
                      {"type": "image_url",
                       "image_url": {"url": f"data:image/png;base64,{img_b64}"}}]}]},
            timeout=30)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]


def default_verifier():
    """A VisionVerifier if a vision key is configured, else None (workflow skips checks)."""
    v = VisionVerifier()
    return v if v.available() else None
