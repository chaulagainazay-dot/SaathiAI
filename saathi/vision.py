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
    if window_app:
        subprocess.run(["open", "-a", window_app], capture_output=True)
        time.sleep(1.5)  # let it come to the front
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        path = f.name
    r = subprocess.run(["screencapture", "-x", path], capture_output=True, text=True)
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

    from .agent import SaathiAgent
    agent = SaathiAgent()
    if agent.provider not in ("gemini",):
        return {"error": "vision needs the Gemini brain (set GOOGLE_API_KEY); "
                         "local Ollama text model can't see images."}
    # use full flash for vision — sharper at reading text in screenshots
    resp = agent.client.chat.completions.create(
        model="gemini-2.5-flash", max_tokens=400,
        messages=[{"role": "user", "content": [
            {"type": "text", "text":
                f"Look at this Mac screenshot and answer briefly for Ajay. {question}"},
            {"type": "image_url",
             "image_url": {"url": f"data:image/png;base64,{b64}"}},
        ]}])
    return {"answer": (resp.choices[0].message.content or "").strip()}
