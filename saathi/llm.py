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
    if name.startswith("anthropic/"):
        return _has("ANTHROPIC_API_KEY")
    if name.startswith("openai/"):
        return _has("OPENAI_API_KEY")
    if name.startswith("groq/"):
        return _has("GROQ_API_KEY")
    if name.startswith("gemini/"):
        return _has("GOOGLE_API_KEY")
    # GLM / DeepSeek / Qwen are served through OpenRouter (one key, many models).
    if name.startswith(("deepseek/", "glm/", "qwen/")):
        return _has("OPENROUTER_API_KEY")
    if name.startswith("ollama/"):
        return bool(os.getenv("OLLAMA_HOST"))   # only if explicitly configured
    return False


# ── real provider callers (compact; mirror tools/_llm_helper) ────────────
def _call_anthropic(prompt, system, max_tokens, timeout):
    import httpx
    model = os.getenv("CLAUDE_MODEL", "claude-sonnet-5")
    r = httpx.post("https://api.anthropic.com/v1/messages",
                   headers={"x-api-key": os.getenv("ANTHROPIC_API_KEY", ""),
                            "anthropic-version": "2023-06-01"},
                   json={"model": model, "max_tokens": max_tokens, "system": system,
                         "messages": [{"role": "user", "content": prompt}]},
                   timeout=timeout)
    r.raise_for_status()
    d = r.json()
    text = "".join(b.get("text", "") for b in d.get("content", []))
    return text, model, d.get("usage", {})


def _openrouter(prompt, system, max_tokens, timeout, model):
    """Shared OpenAI-compatible caller for OpenRouter-served models."""
    import httpx
    r = httpx.post("https://openrouter.ai/api/v1/chat/completions",
                   headers={"Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY')}"},
                   json={"model": model, "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": prompt}], "max_tokens": max_tokens},
                   timeout=timeout)
    if r.status_code == 429:
        raise RuntimeError("openrouter rate-limited")
    r.raise_for_status()
    d = r.json()
    return d["choices"][0]["message"]["content"], model, d.get("usage", {})


def _call_deepseek(prompt, system, max_tokens, timeout):
    return _openrouter(prompt, system, max_tokens, timeout,
                       os.getenv("DEEPSEEK_MODEL", "deepseek/deepseek-chat"))


def _call_glm(prompt, system, max_tokens, timeout):
    return _openrouter(prompt, system, max_tokens, timeout,
                       os.getenv("GLM_MODEL", "z-ai/glm-4.6"))


def _call_qwen(prompt, system, max_tokens, timeout):
    return _openrouter(prompt, system, max_tokens, timeout,
                       os.getenv("QWEN_MODEL", "qwen/qwen-2.5-72b-instruct"))


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
    "anthropic": _call_anthropic,
    "openai": _call_openai,
    "deepseek": _call_deepseek,
    "glm": _call_glm,
    "qwen": _call_qwen,
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
            _event("model.selected", {"label": label.value, "provider": spec.name, "model": model})
            return LLMResult(text=text, provider=spec.name, model=model)
        except Exception as e:  # fall through to the next provider in the chain
            last_err = e
            _event("model.fallback", {"label": label.value, "provider": spec.name, "error": str(e)})
            continue
    _event("model.failed", {"label": label.value, "error": str(last_err)})
    raise RuntimeError(f"All providers failed for '{label.value}': {last_err}")


def _event(name: str, payload: dict) -> None:
    """Publish a Model Router event to the platform Event Fabric (best-effort)."""
    try:
        from saathi.events import bus
        bus.publish_sync(name, payload)
    except Exception:
        pass


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
