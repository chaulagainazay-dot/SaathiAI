"""Cloud engine adapter wrapping canonical HTTP provider transports (M22).

Cloud traffic must still pass privacy/cost/approval policy at the router and
ExecutionGateway layers. This adapter only normalizes the engine interface.
Provider HTTP lives in ``http_providers`` — not in product callers.
"""
from __future__ import annotations

import time
from collections.abc import AsyncIterator
from typing import Any, Callable, Optional, Sequence

from saathi.inference.engine import (
    CostEstimate,
    EngineCapabilities,
    GenerateResult,
    InferenceEngine,
    StreamChunk,
)
from saathi.inference.errors import EngineError, EngineUnhealthyError


# caller: (prompt, system, max_tokens, timeout) -> (text, model_name, usage)
Caller = Callable[[str, str, int, int], tuple[str, str, dict]]


def _split_messages(messages: Sequence[dict[str, Any]]) -> tuple[str, str]:
    system_parts: list[str] = []
    user_parts: list[str] = []
    for m in messages:
        role = (m.get("role") or "user").lower()
        content = str(m.get("content") or "")
        if role == "system":
            system_parts.append(content)
        else:
            user_parts.append(content)
    system = "\n\n".join(system_parts) if system_parts else "You are a helpful assistant."
    prompt = "\n\n".join(user_parts) if user_parts else ""
    return prompt, system


class CloudCallerEngine(InferenceEngine):
    """Wraps family callers from ``saathi.llm`` without replacing them."""

    is_cloud = True

    def __init__(
        self,
        engine_id: str,
        caller: Caller,
        *,
        available: Optional[Callable[[], bool]] = None,
        cost_per_1k: Optional[float] = None,
        default_model: str = "",
        capabilities: Optional[EngineCapabilities] = None,
    ):
        self.engine_id = engine_id
        self._caller = caller
        self._available = available or (lambda: True)
        self._cost_per_1k = cost_per_1k
        self.default_model = default_model
        self._caps = capabilities or EngineCapabilities(
            streaming=False,
            tool_calling=True,
            structured_output=True,
            local=False,
            notes=f"cloud family {engine_id}",
        )

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
        if not self._available():
            raise EngineUnhealthyError(f"{self.engine_id} not available (keys/config)")
        prompt, system = _split_messages(messages)
        t0 = time.monotonic()
        try:
            text, used_model, usage = self._caller(
                prompt, system, max_tokens, int(timeout or 60)
            )
        except Exception as e:
            raise EngineError(f"{self.engine_id} generate failed: {e}", cause=e) from e
        return GenerateResult(
            text=text,
            model=used_model or model or self.default_model,
            engine_id=self.engine_id,
            usage=dict(usage or {}),
            latency_ms=(time.monotonic() - t0) * 1000,
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
        # Existing callers are non-streaming; expose as single chunk.
        result = await self.generate(
            messages, model=model, temperature=temperature, max_tokens=max_tokens, timeout=timeout, **kwargs
        )
        if result.text:
            yield StreamChunk(content=result.text)
        yield StreamChunk(finish_reason="stop", usage=result.usage)

    async def health(self) -> dict[str, Any]:
        ok = bool(self._available())
        return {"ok": ok, "engine_id": self.engine_id, "is_cloud": True}

    async def list_models(self) -> list[str]:
        if self.default_model:
            return [self.default_model]
        return [self.engine_id]

    async def estimate_cost(
        self,
        *,
        model: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
    ) -> CostEstimate:
        if self._cost_per_1k is None:
            return CostEstimate(known=False, notes="provider cost not configured")
        amount = (prompt_tokens + completion_tokens) / 1000.0 * self._cost_per_1k
        return CostEstimate(
            amount=amount,
            per_1k_input=self._cost_per_1k,
            per_1k_output=self._cost_per_1k,
            known=True,
        )

    async def capabilities(self) -> EngineCapabilities:
        return self._caps


def register_builtin_cloud_engines(registry) -> None:
    """Optional helper: register cloud engines from canonical HTTP transports."""
    try:
        from saathi.inference.adapters import http_providers as hp
    except Exception:
        return

    mapping = [
        ("anthropic", "anthropic", 6.0),
        ("openai", "openai", 5.0),
        ("groq", "groq", 0.0),
        ("gemini", "gemini", 0.0),
        ("deepseek", "deepseek", 0.3),
        ("glm", "glm", 0.5),
        ("qwen", "qwen", 0.4),
    ]
    callers = getattr(hp, "DEFAULT_FAMILY_CALLERS", {})
    for engine_id, family, cost in mapping:
        caller = callers.get(family)
        if caller is None:
            continue

        def _avail(name=engine_id):
            try:
                return bool(hp.env_availability(f"{name}/x"))
            except Exception:
                return False

        registry.register(
            engine_id,
            CloudCallerEngine(
                engine_id,
                caller,
                available=_avail,
                cost_per_1k=cost,
            ),
            replace=True,
        )
