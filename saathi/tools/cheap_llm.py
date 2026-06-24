"""cheap_llm — calls Groq (free) via anthropic-proxy for routine/non-critical tasks."""
from __future__ import annotations
import httpx
from .. import config


def cheap_ask(prompt: str, system: str = "You are a helpful assistant.", max_tokens: int = 1024) -> dict:
    """Send a prompt to Groq (free) via anthropic-proxy. Use for captions, summaries, rewrites."""
    try:
        r = httpx.post(
            f"{config.CHEAP_PROXY_URL}/v1/messages",
            headers={"x-api-key": "baadar", "anthropic-version": "2023-06-01"},
            json={
                "model": "claude-haiku-4-5",
                "max_tokens": max_tokens,
                "system": system,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=60,
        )
        r.raise_for_status()
        data = r.json()
        text = data.get("content", [{}])[0].get("text", "")
        return {"reply": text, "model": "groq/llama-3.3-70b", "cost": "free"}
    except Exception as e:
        return {"error": str(e)}


def cheap_proxy_status() -> dict:
    """Check if the cheap proxy (anthropic-proxy → Groq) is running."""
    try:
        r = httpx.get(f"{config.CHEAP_PROXY_URL}/healthz", timeout=3)
        return {"status": "running", "url": config.CHEAP_PROXY_URL} if r.text == "ok" else {"status": "error"}
    except Exception as e:
        return {"status": "offline", "error": str(e), "fix": "Run: cd ~/SaathiAI && ./anthropic-proxy .proxy.env"}
