"""Owner API-key store — paste a key in the UI and it starts working immediately.

Keys are written to ~/.saathi/keys.env and set into the live process environment, so providers
(which read os.getenv at call time) pick them up without a restart. Only an allowlist of
LLM/data keys is accepted. Values are never returned to the client — only a masked status.
"""
from __future__ import annotations

import os
import threading
from pathlib import Path

KEYS_FILE = Path.home() / ".saathi" / "keys.env"
_lock = threading.Lock()

# name -> human label (only these can be set from the UI)
ALLOWED = {
    "GOOGLE_API_KEY": "Google / Gemini API key (chat + screen vision)",
    "GEMINI_MODEL": "Gemini model id (e.g. gemini-2.5-flash)",
    "GEMINI_VISION_MODEL": "Gemini vision model id (optional)",
    "OPENROUTER_API_KEY": "OpenRouter API key (DeepSeek/GLM/Qwen)",
    "GROQ_API_KEY": "Groq API key",
    "ANTHROPIC_API_KEY": "Anthropic (Claude) API key",
    "OLLAMA_MODEL": "Local Ollama model (e.g. qwen3:4b)",
    "OLLAMA_HOST": "Ollama host URL",
}
_SECRET = tuple(k for k in ALLOWED if k.endswith("_API_KEY"))


def _parse(text: str) -> dict[str, str]:
    out = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def load_keys() -> None:
    """Load persisted keys into the live environment (called at startup)."""
    try:
        if KEYS_FILE.exists():
            for k, v in _parse(KEYS_FILE.read_text()).items():
                if k in ALLOWED and v:
                    os.environ[k] = v
    except Exception:
        pass


def set_key(name: str, value: str) -> dict:
    name = (name or "").strip()
    value = (value or "").strip()
    if name not in ALLOWED:
        return {"ok": False, "error": "KEY_NOT_ALLOWED"}
    with _lock:
        try:
            KEYS_FILE.parent.mkdir(parents=True, exist_ok=True)
            existing = _parse(KEYS_FILE.read_text()) if KEYS_FILE.exists() else {}
            if value:
                existing[name] = value
                os.environ[name] = value
            else:
                existing.pop(name, None)
                os.environ.pop(name, None)
            body = "\n".join(f"{k}={v}" for k, v in existing.items()) + "\n"
            KEYS_FILE.write_text(body)
            try:
                KEYS_FILE.chmod(0o600)
            except Exception:
                pass
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)[:120]}
    return {"ok": True, "name": name, "cleared": not value}


def _mask(name: str) -> str:
    v = os.getenv(name, "")
    if not v:
        return ""
    if name in _SECRET:
        return ("•" * 4) + v[-4:] if len(v) >= 4 else "••••"
    return v  # non-secret (model ids, host) shown plainly


def status() -> dict:
    return {
        "keys": [
            {"name": n, "label": ALLOWED[n], "secret": n in _SECRET,
             "set": bool(os.getenv(n)), "masked": _mask(n)}
            for n in ALLOWED
        ],
        "note": "Keys are stored locally (~/.saathi/keys.env, 0600) and never leave this machine except to the provider you configured.",
    }
