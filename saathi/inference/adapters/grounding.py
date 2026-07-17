"""Governed Gemini google_search grounding transport (M22).

Capability-specific adapter: grounding is not available via plain text ModelRouter
families. Callers must use this module only — never copy the URL into product code.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Callable, Optional

_API = "https://generativelanguage.googleapis.com/v1beta/models"
DEFAULT_MODELS: tuple[str, ...] = ("gemini-2.5-flash-lite", "gemini-2.5-flash")

# Optional injectable transport for tests: (url, params, json, timeout) -> response-like
GroundingTransport = Callable[..., Any]


@dataclass(frozen=True)
class GroundingResult:
    text: str
    model: str
    provider_id: str = "gemini"
    capability: str = "google_search_grounding"
    finish_reason: str = "stop"
    latency_ms: float = 0.0
    usage: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "model": self.model,
            "provider_id": self.provider_id,
            "capability": self.capability,
            "finish_reason": self.finish_reason,
            "latency_ms": self.latency_ms,
            "usage": dict(self.usage or {}),
        }


def _api_key() -> str:
    # Credential isolation: only this adapter (and config bootstrap) may resolve keys.
    try:
        from saathi import config

        key = getattr(config, "GOOGLE_API_KEY", "") or os.getenv("GOOGLE_API_KEY", "")
    except Exception:
        key = os.getenv("GOOGLE_API_KEY", "")
    if not key or str(key).startswith("YOUR"):
        raise RuntimeError("MISCONFIGURED: GOOGLE_API_KEY missing")
    return str(key)


def grounded_generate(
    prompt: str,
    *,
    max_tokens: int = 800,
    timeout: float = 90.0,
    models: tuple[str, ...] | None = None,
    transport: Optional[GroundingTransport] = None,
) -> GroundingResult:
    """Execute google_search-grounded generation via Gemini REST.

    Does not implement caller policy — callers must preflight first.
    Does not silently fall back to non-grounded text models.
    """
    import time

    try:
        from saathi.inference.provider_policy import is_master_killed, is_provider_killed

        if is_master_killed():
            raise RuntimeError("SAATHI_INFERENCE_KILL_ALL is active")
        if is_provider_killed("gemini"):
            raise RuntimeError("provider gemini killed")
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

    key = _api_key()
    model_list = models or DEFAULT_MODELS
    last_status = None
    t0 = time.monotonic()

    if transport is not None:
        # Test path — transport returns text or raises
        text = transport(
            prompt=prompt,
            max_tokens=max_tokens,
            timeout=timeout,
            models=model_list,
            api_key_present=True,
        )
        if isinstance(text, GroundingResult):
            return text
        return GroundingResult(
            text=str(text),
            model=model_list[0],
            latency_ms=(time.monotonic() - t0) * 1000,
        )

    import httpx

    for model in model_list:
        r = httpx.post(
            f"{_API}/{model}:generateContent",
            params={"key": key},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "tools": [{"google_search": {}}],
                "generationConfig": {"maxOutputTokens": max_tokens},
            },
            timeout=timeout,
        )
        if r.status_code == 429:
            last_status = r
            continue
        r.raise_for_status()
        parts = r.json()["candidates"][0]["content"]["parts"]
        text = " ".join(p.get("text", "") for p in parts).strip()
        return GroundingResult(
            text=text,
            model=model,
            latency_ms=(time.monotonic() - t0) * 1000,
        )
    if last_status is not None:
        last_status.raise_for_status()
    raise RuntimeError("research_grounding_failed")
