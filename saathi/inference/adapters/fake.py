"""Deterministic fake engine for tests (no network)."""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any, Optional, Sequence

from saathi.inference.engine import (
    CostEstimate,
    EngineCapabilities,
    GenerateResult,
    InferenceEngine,
    StreamChunk,
)
from saathi.inference.errors import EngineTimeoutError, EngineUnhealthyError


class FakeEngine(InferenceEngine):
    engine_id = "fake"
    is_cloud = False

    def __init__(
        self,
        *,
        engine_id: str = "fake",
        healthy: bool = True,
        models: Optional[list[str]] = None,
        responses: Optional[dict[str, str]] = None,
        stream_tokens: Optional[list[str]] = None,
        fail_times: int = 0,
        timeout: bool = False,
        is_cloud: bool = False,
        latency_ms: float = 1.0,
        cost_per_1k: Optional[float] = None,
    ):
        self.engine_id = engine_id
        self.is_cloud = is_cloud
        self._healthy = healthy
        self._models = list(models or ["fake-model"])
        self._responses = dict(responses or {})
        self._stream_tokens = list(stream_tokens or ["ok"])
        self._fail_times = fail_times
        self._timeout = timeout
        self._latency_ms = latency_ms
        self._cost_per_1k = cost_per_1k
        self.generate_calls = 0
        self.stream_calls = 0

    def set_healthy(self, ok: bool) -> None:
        self._healthy = ok

    async def generate(
        self,
        messages: Sequence[dict[str, Any]],
        *,
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        timeout: Optional[float] = None,
        **kwargs: Any,
    ) -> GenerateResult:
        self.generate_calls += 1
        if not self._healthy:
            raise EngineUnhealthyError(f"{self.engine_id} unhealthy")
        if self._timeout:
            raise EngineTimeoutError(f"{self.engine_id} timed out")
        if self._fail_times > 0:
            self._fail_times -= 1
            raise EngineUnhealthyError(f"{self.engine_id} transient failure")
        if timeout is not None and timeout <= 0:
            raise EngineTimeoutError("timeout <= 0")
        text = self._responses.get(model)
        if text is None:
            last = ""
            if messages:
                last = str(messages[-1].get("content", ""))
            text = f"echo:{last}" if last else "ok"
        return GenerateResult(
            text=text,
            model=model,
            engine_id=self.engine_id,
            usage={"prompt_tokens": 1, "completion_tokens": max(1, len(text.split()))},
            latency_ms=self._latency_ms,
        )

    async def stream(
        self,
        messages: Sequence[dict[str, Any]],
        *,
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        timeout: Optional[float] = None,
        **kwargs: Any,
    ) -> AsyncIterator[StreamChunk]:
        self.stream_calls += 1
        if not self._healthy:
            raise EngineUnhealthyError(f"{self.engine_id} unhealthy")
        for tok in self._stream_tokens:
            yield StreamChunk(content=tok)
            await asyncio.sleep(0)
        yield StreamChunk(finish_reason="stop", usage={"completion_tokens": len(self._stream_tokens)})

    async def health(self) -> dict[str, Any]:
        return {"ok": self._healthy, "engine_id": self.engine_id}

    async def list_models(self) -> list[str]:
        if not self._healthy:
            raise EngineUnhealthyError(f"{self.engine_id} unhealthy")
        return list(self._models)

    async def estimate_cost(
        self,
        *,
        model: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
    ) -> CostEstimate:
        if self._cost_per_1k is None:
            return await super().estimate_cost(
                model=model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )
        amount = (prompt_tokens + completion_tokens) / 1000.0 * self._cost_per_1k
        return CostEstimate(
            amount=amount,
            per_1k_input=self._cost_per_1k,
            per_1k_output=self._cost_per_1k,
            known=True,
        )

    async def capabilities(self) -> EngineCapabilities:
        return EngineCapabilities(
            streaming=True,
            tool_calling=True,
            structured_output=True,
            local=not self.is_cloud,
            max_context_window=8192,
        )
