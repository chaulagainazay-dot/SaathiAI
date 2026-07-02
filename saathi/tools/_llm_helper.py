"""Shared LLM caller for studio tools — calls Groq/Gemini directly, no server loopback."""
import json, os, re, time
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
    """Call an LLM via the capability-based Model Router (SES-002).

    Routes the STANDARD label with a QUALITY preference — which orders OpenAI
    (quality_tier 1) ahead of Groq/Gemini, preserving this function's original
    OpenAI-first behavior while going through the router instead of a hardcoded
    chain. Falls back to the legacy inline chain only if the router path errors.
    """
    _load_env()

    # ── Primary path: the Model Router decides + executes (no hardcoded order) ─
    try:
        from ..llm import generate
        from ..model_router import ModelLabel, Prefer
        return generate(
            ModelLabel.STANDARD, prompt, system,
            prefer=Prefer.QUALITY, max_tokens=max_tokens, timeout=timeout,
        ).text
    except Exception:
        pass  # fall through to the legacy inline chain below (belt-and-suspenders)
    from .opik_tracer import trace_llm_call

    # ── 1. OpenAI ChatGPT (primary for creative/script work) ──────────────────
    openai_key = os.getenv("OPENAI_API_KEY", "")
    openai_model = os.getenv("OPENAI_MODEL", "gpt-4o")
    if openai_key and not openai_key.startswith("YOUR"):
        import httpx
        t0 = time.monotonic()
        r = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {openai_key}", "Content-Type": "application/json"},
            json={"model": openai_model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}], "temperature": 0.7, "max_tokens": max_tokens},
            timeout=timeout,
        )
        r.raise_for_status()
        data = r.json()
        output = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        trace_llm_call("openai", openai_model, prompt, system, output,
                       (time.monotonic() - t0) * 1000,
                       {"prompt_tokens": usage.get("prompt_tokens"), "completion_tokens": usage.get("completion_tokens")},
                       tags=["tool-call"])
        return output

    # ── 2. Groq (fast free fallback) ──────────────────────────────────────────
    groq_key = os.getenv("GROQ_API_KEY", "")
    model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

    if groq_key and not groq_key.startswith("YOUR"):
        import httpx
        try:
            t0 = time.monotonic()
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
                data = r.json()
                output = data["choices"][0]["message"]["content"]
                usage = data.get("usage", {})
                trace_llm_call("groq", model, prompt, system, output,
                               (time.monotonic() - t0) * 1000,
                               {"prompt_tokens": usage.get("prompt_tokens"), "completion_tokens": usage.get("completion_tokens")},
                               tags=["tool-call"])
                return output
        except Exception:
            pass  # fall through to Gemini

    # ── 3. Gemini fallback ────────────────────────────────────────────────────
    gemini_key = os.getenv("GOOGLE_API_KEY", "")
    gemini_model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
    if gemini_key and not gemini_key.startswith("YOUR"):
        import httpx
        t0 = time.monotonic()
        r = httpx.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{gemini_model}:generateContent?key={gemini_key}",
            json={"contents": [{"parts": [{"text": f"{system}\n\n{prompt}"}]}]},
            timeout=timeout,
        )
        r.raise_for_status()
        output = r.json()["candidates"][0]["content"]["parts"][0]["text"]
        trace_llm_call("gemini", gemini_model, prompt, system, output,
                       (time.monotonic() - t0) * 1000, tags=["tool-call"])
        return output

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
