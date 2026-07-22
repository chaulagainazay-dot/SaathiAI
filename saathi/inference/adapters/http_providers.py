"""Canonical HTTP provider transports for ModelRouter family execution (M22).

Owns provider-specific URLs, credentials, request bodies, and response parsing
for the historical multi-provider sink previously embedded in ``saathi.llm``.

Production callers must not import transport internals for business logic —
use ``saathi.llm.generate`` (compatibility facade) or governed engines.
"""
from __future__ import annotations

import os
from typing import Any, Callable

# caller signature: (prompt, system, max_tokens, timeout) -> (text, model_name, usage)
Caller = Callable[[str, str, int, int], "tuple[str, str, dict]"]

# Credential env names (reported by name only — never values)
CREDENTIAL_ENV_NAMES: frozenset[str] = frozenset({
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "GROQ_API_KEY",
    "GOOGLE_API_KEY",
    "OPENROUTER_API_KEY",
    "OLLAMA_HOST",
    "OLLAMA_URL",
})


def credential_present(key: str) -> bool:
    """Return True if a non-placeholder env credential is set. Never logs values."""
    v = os.getenv(key, "")
    return bool(v) and not v.startswith("YOUR")


def env_availability(name: str) -> bool:
    """ModelRouter availability probe by provider/model name."""
    if name.startswith("anthropic/"):
        return credential_present("ANTHROPIC_API_KEY")
    if name.startswith("openai/"):
        return credential_present("OPENAI_API_KEY")
    if name.startswith("groq/"):
        return credential_present("GROQ_API_KEY")
    if name.startswith("gemini/"):
        return credential_present("GOOGLE_API_KEY")
    # GLM / DeepSeek / Qwen are served through OpenRouter (one key, many models).
    if name.startswith(("deepseek/", "glm/", "qwen/")):
        return credential_present("OPENROUTER_API_KEY")
    if name.startswith("ollama/"):
        return bool(os.getenv("OLLAMA_HOST") or os.getenv("OLLAMA_URL"))
    return False


def call_anthropic(prompt: str, system: str, max_tokens: int, timeout: int) -> tuple[str, str, dict]:
    import httpx

    model = os.getenv("CLAUDE_MODEL", "claude-sonnet-5")
    key = os.getenv("ANTHROPIC_API_KEY", "")
    if not key or key.startswith("YOUR"):
        raise RuntimeError("MISCONFIGURED: ANTHROPIC_API_KEY missing")
    r = httpx.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
        },
        json={
            "model": model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=timeout,
    )
    r.raise_for_status()
    d = r.json()
    text = "".join(b.get("text", "") for b in d.get("content", []))
    return text, model, d.get("usage", {}) or {}


def call_openrouter(
    prompt: str,
    system: str,
    max_tokens: int,
    timeout: int,
    model: str,
) -> tuple[str, str, dict]:
    """Shared OpenAI-compatible caller for OpenRouter-served models."""
    import httpx

    key = os.getenv("OPENROUTER_API_KEY", "")
    if not key or key.startswith("YOUR"):
        raise RuntimeError("MISCONFIGURED: OPENROUTER_API_KEY missing")
    r = httpx.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}"},
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": max_tokens,
        },
        timeout=timeout,
    )
    if r.status_code == 429:
        raise RuntimeError("openrouter rate-limited")
    r.raise_for_status()
    d = r.json()
    return d["choices"][0]["message"]["content"], model, d.get("usage", {}) or {}


def call_deepseek(prompt: str, system: str, max_tokens: int, timeout: int) -> tuple[str, str, dict]:
    return call_openrouter(
        prompt,
        system,
        max_tokens,
        timeout,
        os.getenv("DEEPSEEK_MODEL", "deepseek/deepseek-chat"),
    )


def call_glm(prompt: str, system: str, max_tokens: int, timeout: int) -> tuple[str, str, dict]:
    return call_openrouter(
        prompt,
        system,
        max_tokens,
        timeout,
        os.getenv("GLM_MODEL", "z-ai/glm-4.6"),
    )


def call_qwen(prompt: str, system: str, max_tokens: int, timeout: int) -> tuple[str, str, dict]:
    return call_openrouter(
        prompt,
        system,
        max_tokens,
        timeout,
        os.getenv("QWEN_MODEL", "qwen/qwen-2.5-72b-instruct"),
    )


def call_openai(prompt: str, system: str, max_tokens: int, timeout: int) -> tuple[str, str, dict]:
    import httpx

    model = os.getenv("OPENAI_MODEL", "gpt-4o")
    key = os.getenv("OPENAI_API_KEY", "")
    if not key or key.startswith("YOUR"):
        raise RuntimeError("MISCONFIGURED: OPENAI_API_KEY missing")
    r = httpx.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}"},
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": max_tokens,
        },
        timeout=timeout,
    )
    r.raise_for_status()
    d = r.json()
    return d["choices"][0]["message"]["content"], model, d.get("usage", {}) or {}


def call_groq(prompt: str, system: str, max_tokens: int, timeout: int) -> tuple[str, str, dict]:
    import httpx

    model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    key = os.getenv("GROQ_API_KEY", "")
    if not key or key.startswith("YOUR"):
        raise RuntimeError("MISCONFIGURED: GROQ_API_KEY missing")
    r = httpx.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}"},
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": max_tokens,
        },
        timeout=timeout,
    )
    if r.status_code == 429:
        raise RuntimeError("groq rate-limited")
    r.raise_for_status()
    d = r.json()
    return d["choices"][0]["message"]["content"], model, d.get("usage", {}) or {}


def call_gemini(prompt: str, system: str, max_tokens: int, timeout: int) -> tuple[str, str, dict]:
    import httpx

    from saathi import config

    model = os.getenv("GEMINI_MODEL") or config.GEMINI_MODEL
    key = os.getenv("GOOGLE_API_KEY", "")
    if not key or key.startswith("YOUR"):
        raise RuntimeError("MISCONFIGURED: GOOGLE_API_KEY missing")
    r = httpx.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        f"?key={key}",
        json={"contents": [{"parts": [{"text": f"{system}\n\n{prompt}"}]}]},
        timeout=timeout,
    )
    r.raise_for_status()
    return r.json()["candidates"][0]["content"]["parts"][0]["text"], model, {}


def call_ollama(prompt: str, system: str, max_tokens: int, timeout: int) -> tuple[str, str, dict]:
    import httpx

    model = os.getenv("OLLAMA_MODEL", "llama3.1")
    host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    r = httpx.post(
        f"{host}/api/generate",
        json={
            "model": model,
            "prompt": f"{system}\n\n{prompt}",
            "stream": False,
        },
        timeout=timeout,
    )
    r.raise_for_status()
    return r.json().get("response", ""), model, {}


DEFAULT_FAMILY_CALLERS: dict[str, Caller] = {
    "anthropic": call_anthropic,
    "openai": call_openai,
    "deepseek": call_deepseek,
    "glm": call_glm,
    "qwen": call_qwen,
    "groq": call_groq,
    "gemini": call_gemini,
    "ollama": call_ollama,
}


def invoke_family(
    family: str,
    prompt: str,
    system: str,
    max_tokens: int,
    timeout: int,
    *,
    callers: dict[str, Caller] | None = None,
) -> tuple[str, str, dict]:
    """Execute one provider family via registered transport. No failover here."""
    table = callers if callers is not None else DEFAULT_FAMILY_CALLERS
    caller = table.get(family)
    if caller is None:
        raise RuntimeError(f"no transport for family {family!r}")
    # Kill before network
    try:
        from saathi.inference.provider_policy import is_provider_killed

        if is_provider_killed(family):
            raise RuntimeError(f"provider {family} killed")
    except RuntimeError:
        raise
    except Exception:
        pass
    return caller(prompt, system, max_tokens, timeout)


def transport_inventory() -> list[dict[str, Any]]:
    """Privacy-safe inventory for M22 audit / release checks."""
    return [
        {
            "family": fam,
            "module": "saathi.inference.adapters.http_providers",
            "transport": "httpx",
            "classification": "CANONICAL_TRANSPORT",
        }
        for fam in sorted(DEFAULT_FAMILY_CALLERS)
    ]
