from __future__ import annotations
"""Screen vision — Saathi looks at the screen and answers questions about it.

Uses screencapture (built-in) + Gemini's free vision. Lets Saathi read WhatsApp
messages, tell you who messaged, summarize what's on screen, read any window —
all by voice. Needs macOS Screen Recording permission once (see README).
"""
import base64
import subprocess
import tempfile
import time
from pathlib import Path

from . import config


def grab_screen(window_app: str | None = None) -> bytes:
    """Capture the screen (or bring an app to front first) as PNG bytes."""
    # absolute paths — under launchd the PATH doesn't include /usr/sbin
    if window_app:
        subprocess.run(["/usr/bin/open", "-a", window_app], capture_output=True)
        time.sleep(1.5)  # let it come to the front
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        path = f.name
    r = subprocess.run(["/usr/sbin/screencapture", "-x", path], capture_output=True, text=True)
    if r.returncode != 0 or not Path(path).exists() or Path(path).stat().st_size == 0:
        raise RuntimeError(
            "Screen Recording permission needed. Grant it once: System Settings → "
            "Privacy & Security → Screen Recording → add the SaathiAI python "
            f"({config.ROOT}/.venv/bin/python), then restart Saathi.")
    data = Path(path).read_bytes()
    Path(path).unlink(missing_ok=True)
    return data


def ask_screen(question: str, window_app: str | None = None) -> dict:
    """Look at the screen and answer a question about it (Gemini vision)."""
    png = grab_screen(window_app)
    b64 = base64.b64encode(png).decode()

    # Vision always uses Gemini directly (Groq/Ollama can't see images), regardless
    # of which brain is primary for conversation.
    if not config.GOOGLE_API_KEY:
        return {"error": "vision needs a Google API key (GOOGLE_API_KEY) for Gemini."}
    from openai import OpenAI
    from openai import APIStatusError
    client = OpenAI(api_key=config.GOOGLE_API_KEY,
                    base_url="https://generativelanguage.googleapis.com/v1beta/openai/")
    msgs = [{"role": "user", "content": [
        {"type": "text", "text":
            f"Look at this Mac screenshot and answer briefly for Ajay. {question}"},
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
    ]}]
    # flash-lite first (higher free quota), fall back to full flash
    last = None
    for model in ("gemini-2.5-flash-lite", "gemini-2.5-flash"):
        try:
            resp = client.chat.completions.create(model=model, max_tokens=400, messages=msgs)
            return {"answer": (resp.choices[0].message.content or "").strip()}
        except APIStatusError as e:
            last = e
            if e.status_code != 429:
                break
    return {"error": "Vision is rate-limited right now (Gemini free quota). "
                     "Try again in a minute or tomorrow.", "detail": str(last)[:120]}
