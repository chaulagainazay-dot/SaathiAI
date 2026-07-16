"""Bounded multi-engine execution with fallback, timeout, and retries.

Selection order is supplied by the caller (typically ModelRouter-derived).
This module never invents cloud routes for sensitive data.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Optional, Sequence

from saathi.inference.engine import GenerateResult, InferenceEngine, StreamChunk
from saathi.inference.errors import (
    EngineError,
    EngineRetryExhausted,
    EngineTimeoutError,
    EngineUnhealthyError,
    NormalizedError,
    normalize_error,
)
from saathi.inference.registry import EngineRegistry


@dataclass
class RuntimeAttempt:
    engine_id: str
    ok: bool
    error: Optional[NormalizedError] = None
    latency_ms: float = 0.0


@dataclass
class RuntimeResult:
    result: Optional[GenerateResult]
    attempts: list[RuntimeAttempt] = field(default_factory=list)
    engine_id: str = ""
    fallback_used: bool = False

    @property
    def ok(self) -> bool:
        return self.result is not None


async def _with_timeout(coro, timeout: Optional[float]):
    if timeout is None:
        return await coro
    return await asyncio.wait_for(coro, timeout=timeout)


async def generate_with_fallback(
    registry: EngineRegistry,
    engine_chain: Sequence[str],
    messages: Sequence[dict[str, Any]],
    *,
    model: str,
    timeout: float = 60.0,
    max_retries: int = 1,
    temperature: float = 0.7,
    max_tokens: int = 1024,
    allow_cloud: bool = True,
    **kwargs: Any,
) -> RuntimeResult:
    """Try engines in order. max_retries is per engine (bounded)."""
    if not engine_chain:
        raise EngineError("empty engine chain")

    attempts: list[RuntimeAttempt] = []
    max_retries = max(0, min(int(max_retries), 3))

    for idx, engine_id in enumerate(engine_chain):
        engine = registry.get(engine_id)
        if engine is None:
            attempts.append(
                RuntimeAttempt(
                    engine_id=engine_id,
                    ok=False,
                    error=NormalizedError(
                        code="engine_missing",
                        message=f"engine not registered: {engine_id}",
                        retryable=False,
                        provider=engine_id,
                    ),
                )
            )
            continue
        if engine.is_cloud and not allow_cloud:
            attempts.append(
                RuntimeAttempt(
                    engine_id=engine_id,
                    ok=False,
                    error=NormalizedError(
                        code="cloud_denied",
                        message="cloud engine excluded by policy",
                        retryable=False,
                        provider=engine_id,
                    ),
                )
            )
            continue

        last_err: Optional[NormalizedError] = None
        for _try in range(max_retries + 1):
            try:
                result = await _with_timeout(
                    engine.generate(
                        messages,
                        model=model,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        timeout=timeout,
                        **kwargs,
                    ),
                    timeout,
                )
                attempts.append(RuntimeAttempt(engine_id=engine_id, ok=True, latency_ms=result.latency_ms))
                return RuntimeResult(
                    result=result,
                    attempts=attempts,
                    engine_id=engine_id,
                    fallback_used=idx > 0,
                )
            except asyncio.TimeoutError as e:
                last_err = normalize_error(EngineTimeoutError(str(e)), provider=engine_id, model=model)
            except (EngineTimeoutError, EngineUnhealthyError, EngineError, Exception) as e:
                last_err = normalize_error(e, provider=engine_id, model=model)
                if not last_err.retryable:
                    break
        attempts.append(RuntimeAttempt(engine_id=engine_id, ok=False, error=last_err))

    raise EngineRetryExhausted(
        f"all engines failed for model={model}: "
        + "; ".join(
            f"{a.engine_id}={a.error.code if a.error else 'unknown'}" for a in attempts
        )
    )


async def stream_first_healthy(
    registry: EngineRegistry,
    engine_chain: Sequence[str],
    messages: Sequence[dict[str, Any]],
    *,
    model: str,
    timeout: float = 60.0,
    allow_cloud: bool = True,
    **kwargs: Any,
):
    """Async generator that streams from the first usable engine."""
    last: Optional[BaseException] = None
    for engine_id in engine_chain:
        engine = registry.get(engine_id)
        if engine is None:
            continue
        if engine.is_cloud and not allow_cloud:
            continue
        try:
            async for chunk in engine.stream(messages, model=model, timeout=timeout, **kwargs):
                yield chunk
            return
        except Exception as e:
            last = e
            continue
    if last:
        raise EngineError(f"stream failed: {last}", cause=last)
    raise EngineError("no engine available for stream")
