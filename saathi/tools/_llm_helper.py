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


def ask_llm(prompt: str, system: str = "You are a helpful assistant. Reply ONLY with valid JSON.",
            timeout: int = 60, max_tokens: int = 4000) -> str:
    """Call LLM directly. Priority: OpenAI GPT-4o → Groq → Gemini."""
    _load_env()

    # ── 1. OpenAI ChatGPT (primary for creative/script work) ──────────────────
    openai_key = os.getenv("OPENAI_API_KEY", "")
    openai_model = os.getenv("OPENAI_MODEL", "gpt-4o")
    if openai_key and not openai_key.startswith("YOUR"):
        import httpx
        r = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {openai_key}", "Content-Type": "application/json"},
            json={"model": openai_model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}], "temperature": 0.7, "max_tokens": max_tokens},
            timeout=timeout,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]

    # ── 2. Groq (fast free fallback) ──────────────────────────────────────────
    groq_key = os.getenv("GROQ_API_KEY", "")
    model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

    if groq_key and not groq_key.startswith("YOUR"):
        import httpx
        try:
            r = httpx.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"},
                json={"model": model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}], "temperature": 0.7, "max_tokens": max_tokens},
                timeout=timeout,
            )
            if r.status_code == 429:
                pass  # fall through to Gemini
            else:
                r.raise_for_status()
                return r.json()["choices"][0]["message"]["content"]
        except Exception:
            pass  # fall through to Gemini

    # Fallback: Gemini
    gemini_key = os.getenv("GOOGLE_API_KEY", "")
    gemini_model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
    if gemini_key and not gemini_key.startswith("YOUR"):
        import httpx
        r = httpx.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{gemini_model}:generateContent?key={gemini_key}",
            json={"contents": [{"parts": [{"text": f"{system}\n\n{prompt}"}]}]},
            timeout=timeout,
        )
        r.raise_for_status()
        return r.json()["candidates"][0]["content"]["parts"][0]["text"]

    raise RuntimeError("No LLM API key available (GROQ_API_KEY or GOOGLE_API_KEY)")


def extract_json(text: str) -> dict:
    """Extract first JSON object from LLM reply, with multi-pass cleaning."""
    # Strip markdown fences
    text = re.sub(r'```(?:json)?', '', text).strip()

    # Find outermost { ... }
    start = text.find('{')
    if start == -1:
        raise ValueError(f"No JSON found in: {text[:200]}")

    # Walk to find matching closing brace
    depth, end = 0, -1
    for i, ch in enumerate(text[start:], start):
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                end = i + 1
                break

    raw = text[start:end] if end != -1 else text[start:]

    # First attempt — direct parse
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Second attempt — strip control characters (tabs, newlines inside strings)
    cleaned = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', raw)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Third attempt — remove trailing comma before } or ]
    fixed = re.sub(r',\s*([\}\]])', r'\1', cleaned)
    try:
        return json.loads(fixed)
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON parse failed after 3 attempts: {e} | text[:300]={raw[:300]}")
