"""LLM execution via the Model Router (SES-002) — the capability-based path.

M21.3: ``generate`` is a **deprecated compatibility facade**.

  * Builds / attaches caller identity + preflight governance
  * Kill switches checked before any provider network call
  * ModelRouter remains the sole selection authority
  * Provider HTTP callers remain an EXPLICIT_LEGACY_EXCEPTION (expiry M22)
  * New call sites are frozen by ``saathi.inference.release_check``
  * Does not log raw prompts/outputs in preflight telemetry

    request → preflight → label → ModelRouter → ordered chain → try each → result

Provider identity lives only in the router registry + the caller table here.
Testable in isolation (AP-12): availability + callers are injected; no network.
"""
from __future__ import annotations

import os
import time
import warnings
from dataclasses import dataclass
from typing import Callable, Optional

from saathi.model_router import ModelRouter, ModelLabel, Privacy, Prefer, ProviderSpec

# caller signature: (prompt, system, max_tokens, timeout) -> (text, model_name, usage)
Caller = Callable[[str, str, int, int], "tuple[str, str, dict]"]

_DEPRECATION_EMITTED = False


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


# ── real provider callers (compact; mirror historical _llm_helper) ────────
# M21.3: EXPLICIT_LEGACY_EXCEPTION — only reachable via generate() after preflight.
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
    from saathi import config
    model = os.getenv("GEMINI_MODEL") or config.GEMINI_MODEL
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
    *,
    caller_id: str = "legacy_llm_generate",
    skip_preflight: bool = False,
) -> LLMResult:
    """Route to a provider by capability and execute, falling back down the chain.

    .. deprecated:: M21.3
        Prefer governed ``InferenceRequest`` + ``execute_governed_local_inference``
        or an approved compatibility adapter (``chat_adapter``, ``cheap_ask``,
        ``prose_clean``). This facade remains for residual callers until M22.
    """
    global _DEPRECATION_EMITTED
    if not _DEPRECATION_EMITTED and os.getenv("SAATHI_ENV", "").strip().lower() in {
        "dev",
        "development",
        "",
    }:
        if os.getenv("SAATHI_LLM_GENERATE_DEPRECATION_WARN", "1").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }:
            # Once per process; never includes prompt
            warnings.warn(
                "saathi.llm.generate is deprecated (M21.3); use governed InferenceRequest "
                "or an approved compatibility adapter. Expiry: M22.",
                DeprecationWarning,
                stacklevel=2,
            )
            _DEPRECATION_EMITTED = True

    cid = (caller_id or "").strip() or "legacy_llm_generate"
    max_tok = int(max_tokens)
    timeout_i = int(timeout)

    if not skip_preflight:
        try:
            from saathi.inference.legacy_facade import preflight_inference

            pf = preflight_inference(
                caller_id=cid,
                path_id="legacy_llm_generate",
                prompt=prompt or "",
                system=system or "",
                max_tokens=max_tok,
                timeout=float(timeout_i),
            )
            if not pf.ok:
                raise RuntimeError(pf.error_message or pf.reason_code or "preflight_denied")
            max_tok = int(pf.max_output_tokens)
            timeout_i = int(max(1, min(pf.timeout_seconds, 300)))
            # If caller policy disallows cloud, force LOCAL_ONLY privacy
            if not pf.cloud_allowed and privacy is Privacy.CLOUD_OK:
                try:
                    privacy = Privacy.LOCAL_ONLY
                except Exception:
                    pass
        except RuntimeError:
            raise
        except Exception:
            # Preflight module unavailable: still honor master kill
            if os.getenv("SAATHI_INFERENCE_KILL_ALL", "").strip().lower() in {
                "1",
                "true",
                "yes",
                "on",
            }:
                raise RuntimeError("SAATHI_INFERENCE_KILL_ALL is active")

    router = router or ModelRouter(is_available=env_availability)
    callers = callers or DEFAULT_CALLERS
    chain = router.route(label, privacy=privacy, prefer=prefer)
    if not chain:
        raise RuntimeError(f"No available provider serves label '{label.value}' (privacy={privacy.value})")

    last_err: Exception | None = None
    for spec in chain:
        # Provider-level kill before network
        try:
            from saathi.inference.provider_policy import is_provider_killed

            if is_provider_killed(_family(spec.name)):
                last_err = RuntimeError(f"provider {_family(spec.name)} killed")
                _event(
                    "model.fallback",
                    {
                        "label": label.value,
                        "provider": spec.name,
                        "error": "provider_killed",
                        "caller_id": cid,
                    },
                )
                continue
        except Exception:
            pass
        caller = callers.get(_family(spec.name))
        if caller is None:
            continue
        try:
            t0 = time.monotonic()
            text, model, usage = caller(prompt, system, max_tok, timeout_i)
            if trace:
                _trace(spec, model, prompt, system, text, (time.monotonic() - t0) * 1000, usage)
            _event(
                "model.selected",
                {
                    "label": label.value,
                    "provider": spec.name,
                    "model": model,
                    "caller_id": cid,
                },
            )
            return LLMResult(text=text, provider=spec.name, model=model)
        except Exception as e:  # fall through to the next provider in the chain
            last_err = e
            # Redact: never put full exception bodies that may contain prompts
            err_name = type(e).__name__
            _event(
                "model.fallback",
                {
                    "label": label.value,
                    "provider": spec.name,
                    "error": err_name,
                    "caller_id": cid,
                },
            )
            continue
    _event("model.failed", {"label": label.value, "error": type(last_err).__name__ if last_err else "none", "caller_id": cid})
    raise RuntimeError(f"All providers failed for '{label.value}': {type(last_err).__name__ if last_err else 'none'}")


def _event(name: str, payload: dict) -> None:
    """Publish a Model Router event to the platform Event Fabric (best-effort)."""
    try:
        from saathi.events import bus
        # Strip any accidental sensitive keys
        safe = {
            k: v
            for k, v in payload.items()
            if k not in ("prompt", "output", "text", "system", "api_key")
        }
        bus.publish_sync(name, safe)
    except Exception:
        pass


def _trace(spec: ProviderSpec, model, prompt, system, output, ms, usage):
    # Historical Opik tracer may log content — best-effort only; do not expand.
    try:
        from saathi.tools.opik_tracer import trace_llm_call
        # Prefer fingerprint-only if tracer supports it; keep call shape for compat
        if os.getenv("SAATHI_TRACE_RAW_LLM", "").strip().lower() not in {
            "1",
            "true",
            "yes",
            "on",
        }:
            # Privacy-safe: pass empty strings for content; metadata only
            trace_llm_call(
                _family(spec.name),
                model,
                "",
                "",
                "",
                ms,
                {
                    "prompt_tokens": usage.get("prompt_tokens"),
                    "completion_tokens": usage.get("completion_tokens"),
                    "raw_content_suppressed": True,
                },
                tags=["router", label_tag(spec), "m21_3_privacy"],
            )
        else:
            trace_llm_call(
                _family(spec.name),
                model,
                prompt,
                system,
                output,
                ms,
                {
                    "prompt_tokens": usage.get("prompt_tokens"),
                    "completion_tokens": usage.get("completion_tokens"),
                },
                tags=["router", label_tag(spec)],
            )
    except Exception:
        pass


def label_tag(spec: ProviderSpec) -> str:
    return "routed"


# Deprecation metadata for release checks / docs
LLM_GENERATE_DEPRECATION = {
    "deprecated": True,
    "since": "M21.3",
    "expiry_milestone": "M22",
    "replacement": "saathi.inference.gateway_path.execute_governed_local_inference",
    "classification": "EXPLICIT_LEGACY_EXCEPTION",
}
