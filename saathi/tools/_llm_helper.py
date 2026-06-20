"""Shared LLM caller for studio tools — calls Groq/Gemini directly, no server loopback."""
import json, os, re
from pathlib import Path


def _load_env():
    try:
        for line in (Path.home() / "SaathiAI" / ".env").read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())
    except Exception:
        pass


def ask_llm(prompt: str, system: str = "You are a helpful assistant. Reply ONLY with valid JSON.", timeout: int = 60) -> str:
    """Call LLM directly. Returns the text reply."""
    _load_env()
    groq_key = os.getenv("GROQ_API_KEY", "")
    model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

    if groq_key and not groq_key.startswith("YOUR"):
        import httpx
        r = httpx.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"},
            json={"model": model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}], "temperature": 0.7, "max_tokens": 1500},
            timeout=timeout,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]

    # Fallback: Gemini
    gemini_key = os.getenv("GOOGLE_API_KEY", "")
    if gemini_key and not gemini_key.startswith("YOUR"):
        import httpx
        r = httpx.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={gemini_key}",
            json={"contents": [{"parts": [{"text": f"{system}\n\n{prompt}"}]}]},
            timeout=timeout,
        )
        r.raise_for_status()
        return r.json()["candidates"][0]["content"]["parts"][0]["text"]

    raise RuntimeError("No LLM API key available (GROQ_API_KEY or GOOGLE_API_KEY)")


def extract_json(text: str) -> dict:
    """Extract first JSON object from LLM reply."""
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        return json.loads(match.group(0))
    raise ValueError(f"No JSON found in: {text[:200]}")
