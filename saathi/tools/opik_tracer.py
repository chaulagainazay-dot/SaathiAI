"""
Opik LLM observability integration for Baadar/SaathiAI.

Traces every LLM call (Claude, Groq, Gemini, OpenAI) with inputs, outputs,
token usage, latency, and cost. Dashboard at http://localhost:5173 (after
`docker compose up` in ~/SaathiAI/opik/).

Self-hosted by default — no cloud account needed.
Set OPIK_URL in .env to override (e.g. https://opik.comet.com for cloud).
"""
from __future__ import annotations

import functools
import os
import time
from typing import Any, Callable


def _opik_enabled() -> bool:
    return os.getenv("OPIK_ENABLED", "1") != "0"


def _get_client():
    """Return opik client, or None if not configured/available."""
    try:
        import opik
        return opik
    except ImportError:
        return None


def track(name: str = "", tags: list[str] | None = None):
    """Decorator: traces any function as an Opik span."""
    def decorator(fn: Callable) -> Callable:
        if not _opik_enabled():
            return fn
        opik = _get_client()
        if opik is None:
            return fn
        try:
            return opik.track(name=name or fn.__name__, tags=tags or [])(fn)
        except Exception:
            return fn
    return decorator


def trace_llm_call(
    provider: str,
    model: str,
    prompt: str,
    system: str,
    output: str,
    latency_ms: float,
    usage: dict | None = None,
    tags: list[str] | None = None,
) -> None:
    """Log a single LLM call to Opik as a trace."""
    if not _opik_enabled():
        return
    try:
        import opik
        client = opik.Opik()
        trace = client.trace(
            name=f"{provider}/{model}",
            input={"system": system[:500], "prompt": prompt[:1000]},
            output={"text": output[:2000]},
            tags=(tags or []) + [provider, model],
            metadata={
                "latency_ms": round(latency_ms),
                "provider": provider,
                "model": model,
                **(usage or {}),
            },
        )
        trace.end()
    except Exception:
        pass  # never break the app for observability failures


def flush() -> None:
    """Flush pending Opik spans (call on shutdown)."""
    try:
        import opik
        opik.flush_tracker()
    except Exception:
        pass
