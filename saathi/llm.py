"""LLM execution via the Model Router (SES-002) — the capability-based path.

`generate(label, prompt)` routes to an ordered provider chain and executes with
fallback. Agents ask for a capability label; they never name a model. This is
the execution path the Model Router was built for — no agent selects models
directly.

    request → label → ModelRouter → ordered chain → try each → result

Provider identity lives only in the router registry + the caller table here.
Testable in isolation (AP-12): availability + callers are injected; no network.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Callable

from saathi.model_router import ModelRouter, ModelLabel, Privacy, Prefer, ProviderSpec

# caller signature: (prompt, system, max_tokens, timeout) -> (text, model_name, usage)
Caller = Callable[[str, str, int, int], "tuple[str, str, dict]"]


@dataclass
class LLMResult:
    text: str
    provider: str
    model: str


# ── provider availability from environment ──────────────────────────────
def _has(key: str) -> bool:
    v = os.getenv(key, "")
    return bool(v) and not v.startswith("YOUR")


def env_availability(name: str) -> bool:
    if name.startswith("openai/"):
        return _has("OPENAI_API_KEY")
    if name.startswith("groq/"):
        return _has("GROQ_API_KEY")
    if name.startswith("gemini/"):
        return _has("GOOGLE_API_KEY")
    if name.startswith("ollama/"):
        return bool(os.getenv("OLLAMA_HOST"))   # only if explicitly configured
    return False


# ── real provider callers (compact; mirror tools/_llm_helper) ────────────
def _call_openai(prompt, system, max_tokens, timeout):
    import httpx
    model = os.getenv("OPENAI_MODEL", "gpt-4o")
    r = httpx.post("https://api.openai.com/v1/chat/completions",
                   headers={"Authorization": f"Bearer {os.getenv('OPENAI_API_KEY')}"},
                   json={"model": model, "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": prompt}], "max_tokens": max_tokens},
                   timeout=timeout)
    r.raise_for_status()
    d = r.json()
    return d["choices"][0]["message"]["content"], model, d.get("usage", {})


def _call_groq(prompt, system, max_tokens, timeout):
    import httpx
    model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    r = httpx.post("https://api.groq.com/openai/v1/chat/completions",
                   headers={"Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}"},
                   json={"model": model, "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": prompt}], "max_tokens": max_tokens},
                   timeout=timeout)
    if r.status_code == 429:
        raise RuntimeError("groq rate-limited")
    r.raise_for_status()
    d = r.json()
    return d["choices"][0]["message"]["content"], model, d.get("usage", {})


def _call_gemini(prompt, system, max_tokens, timeout):
    import httpx
    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
    r = httpx.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        f"?key={os.getenv('GOOGLE_API_KEY')}",
        json={"contents": [{"parts": [{"text": f"{system}\n\n{prompt}"}]}]}, timeout=timeout)
    r.raise_for_status()
    return r.json()["candidates"][0]["content"]["parts"][0]["text"], model, {}


def _call_ollama(prompt, system, max_tokens, timeout):
    import httpx
    model = os.getenv("OLLAMA_MODEL", "llama3.1")
    host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    r = httpx.post(f"{host}/api/generate",
                   json={"model": model, "prompt": f"{system}\n\n{prompt}", "stream": False},
                   timeout=timeout)
    r.raise_for_status()
    return r.json().get("response", ""), model, {}


DEFAULT_CALLERS: dict[str, Caller] = {
    "openai": _call_openai,
    "groq": _call_groq,
    "gemini": _call_gemini,
    "ollama": _call_ollama,
}


def _family(provider_name: str) -> str:
    return provider_name.split("/", 1)[0]


def generate(
    label: ModelLabel,
    prompt: str,
    system: str = "You are a helpful assistant.",
    privacy: Privacy = Privacy.CLOUD_OK,
    prefer: Prefer = Prefer.QUALITY,
    max_tokens: int = 2048,
    timeout: int = 60,
    router: ModelRouter | None = None,
    callers: dict[str, Caller] | None = None,
    trace: bool = True,
) -> LLMResult:
    """Route to a provider by capability and execute, falling back down the chain."""
    router = router or ModelRouter(is_available=env_availability)
    callers = callers or DEFAULT_CALLERS
    chain = router.route(label, privacy=privacy, prefer=prefer)
    if not chain:
        raise RuntimeError(f"No available provider serves label '{label.value}' (privacy={privacy.value})")

    last_err: Exception | None = None
    for spec in chain:
        caller = callers.get(_family(spec.name))
        if caller is None:
            continue
        try:
            t0 = time.monotonic()
            text, model, usage = caller(prompt, system, max_tokens, timeout)
            if trace:
                _trace(spec, model, prompt, system, text, (time.monotonic() - t0) * 1000, usage)
            return LLMResult(text=text, provider=spec.name, model=model)
        except Exception as e:  # fall through to the next provider in the chain
            last_err = e
            continue
    raise RuntimeError(f"All providers failed for '{label.value}': {last_err}")


def _trace(spec: ProviderSpec, model, prompt, system, output, ms, usage):
    try:
        from saathi.tools.opik_tracer import trace_llm_call
        trace_llm_call(_family(spec.name), model, prompt, system, output, ms,
                       {"prompt_tokens": usage.get("prompt_tokens"),
                        "completion_tokens": usage.get("completion_tokens")},
                       tags=["router", label_tag(spec)])
    except Exception:
        pass


def label_tag(spec: ProviderSpec) -> str:
    return "routed"
