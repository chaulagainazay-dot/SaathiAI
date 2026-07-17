"""LLM execution via the Model Router (SES-002) — the capability-based path.

M22: ``generate`` is a **pure compatibility facade**.

  * Builds / attaches caller identity + preflight governance
  * Kill switches checked before any provider network call
  * ModelRouter remains the sole selection authority
  * Provider HTTP lives only in ``saathi.inference.adapters.http_providers``
  * New call sites remain frozen by ``saathi.inference.release_check``
  * Does not log raw prompts/outputs in preflight telemetry

    request → preflight → label → ModelRouter → ordered chain
    → governed family transport → result

Testable in isolation (AP-12): availability + callers are injected; no network.

Note: adapter imports are **lazy** to avoid circular import with
``saathi.inference.compat`` which re-exports ``LLMResult``.
"""
from __future__ import annotations

import os
import time
import warnings
from dataclasses import dataclass
from typing import Any, Callable, Optional

from saathi.model_router import ModelRouter, ModelLabel, Privacy, Prefer, ProviderSpec

# caller signature: (prompt, system, max_tokens, timeout) -> (text, model_name, usage)
Caller = Callable[[str, str, int, int], "tuple[str, str, dict]"]

_DEPRECATION_EMITTED = False


@dataclass
class LLMResult:
    text: str
    provider: str
    model: str


def _http_providers():
    from saathi.inference.adapters import http_providers as hp

    return hp


def env_availability(name: str) -> bool:
    return _http_providers().env_availability(name)


def _default_callers() -> dict[str, Caller]:
    return dict(_http_providers().DEFAULT_FAMILY_CALLERS)


# Module-level alias populated lazily for ``from saathi.llm import DEFAULT_CALLERS``
def __getattr__(name: str) -> Any:
    if name == "DEFAULT_CALLERS":
        return _default_callers()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


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
    """Route to a provider by capability and execute via governed transports.

    .. deprecated:: M21.3 / M22
        Prefer governed ``InferenceRequest`` + ``execute_governed_local_inference``
        or an approved compatibility adapter (``chat_adapter``, ``cheap_ask``,
        ``prose_clean``). This facade remains provider-agnostic; HTTP is not here.
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
            warnings.warn(
                "saathi.llm.generate is a compatibility facade (M22); use governed "
                "InferenceRequest or an approved adapter. Provider HTTP is adapter-only.",
                DeprecationWarning,
                stacklevel=2,
            )
            _DEPRECATION_EMITTED = True

    cid = (caller_id or "").strip() or "legacy_llm_generate"
    max_tok = int(max_tokens)
    timeout_i = int(timeout)
    hp = _http_providers()

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
            if not pf.cloud_allowed and privacy is Privacy.CLOUD_OK:
                try:
                    privacy = Privacy.LOCAL_ONLY
                except Exception:
                    pass
        except RuntimeError:
            raise
        except Exception:
            if os.getenv("SAATHI_INFERENCE_KILL_ALL", "").strip().lower() in {
                "1",
                "true",
                "yes",
                "on",
            }:
                raise RuntimeError("SAATHI_INFERENCE_KILL_ALL is active")

    router = router or ModelRouter(is_available=hp.env_availability)
    callers = callers if callers is not None else _default_callers()
    chain = router.route(label, privacy=privacy, prefer=prefer)
    if not chain:
        raise RuntimeError(
            f"No available provider serves label '{label.value}' (privacy={privacy.value})"
        )

    last_err: Exception | None = None
    for spec in chain:
        fam = _family(spec.name)
        try:
            from saathi.inference.provider_policy import is_provider_killed

            if is_provider_killed(fam):
                last_err = RuntimeError(f"provider {fam} killed")
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
        if callers.get(fam) is None:
            continue
        try:
            t0 = time.monotonic()
            text, model, usage = hp.invoke_family(
                fam,
                prompt,
                system,
                max_tok,
                timeout_i,
                callers=callers,
            )
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
        except Exception as e:
            last_err = e
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
    _event(
        "model.failed",
        {
            "label": label.value,
            "error": type(last_err).__name__ if last_err else "none",
            "caller_id": cid,
        },
    )
    raise RuntimeError(
        f"All providers failed for '{label.value}': "
        f"{type(last_err).__name__ if last_err else 'none'}"
    )


def _event(name: str, payload: dict) -> None:
    """Publish a Model Router event to the platform Event Fabric (best-effort)."""
    try:
        from saathi.events import bus

        safe = {
            k: v
            for k, v in payload.items()
            if k not in ("prompt", "output", "text", "system", "api_key")
        }
        bus.publish_sync(name, safe)
    except Exception:
        pass


def _trace(spec: ProviderSpec, model, prompt, system, output, ms, usage):
    try:
        from saathi.tools.opik_tracer import trace_llm_call

        if os.getenv("SAATHI_TRACE_RAW_LLM", "").strip().lower() not in {
            "1",
            "true",
            "yes",
            "on",
        }:
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
                tags=["router", label_tag(spec), "m22_privacy"],
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
    "migrated": "M22",
    "expiry_milestone": "n/a",
    "replacement": "saathi.inference.gateway_path.execute_governed_local_inference",
    "classification": "COMPATIBILITY_FACADE",
    "provider_http": "saathi.inference.adapters.http_providers",
}
