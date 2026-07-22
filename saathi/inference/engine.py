"""SaathiOS InferenceEngine contract.

Conceptually informed by OpenJarvis ``InferenceEngine`` (Apache-2.0 reference),
implemented as original SaathiOS code. Model selection remains in ``ModelRouter``.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Optional, Sequence


@dataclass(frozen=True)
class StreamChunk:
    content: Optional[str] = None
    finish_reason: Optional[str] = None
    usage: Optional[dict[str, Any]] = None
    tool_calls: Optional[list[dict[str, Any]]] = None


@dataclass(frozen=True)
class EngineCapabilities:
    streaming: bool = False
    tool_calling: bool = False
    structured_output: bool = False
    vision: bool = False
    audio: bool = False
    local: bool = True
    max_context_window: Optional[int] = None
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "streaming": self.streaming,
            "tool_calling": self.tool_calling,
            "structured_output": self.structured_output,
            "vision": self.vision,
            "audio": self.audio,
            "local": self.local,
            "max_context_window": self.max_context_window,
            "notes": self.notes,
        }


@dataclass
class GenerateResult:
    text: str
    model: str
    engine_id: str
    usage: dict[str, Any] = field(default_factory=dict)
    latency_ms: float = 0.0
    finish_reason: str = "stop"
    raw: Optional[dict[str, Any]] = None


@dataclass(frozen=True)
class CostEstimate:
    currency: str = "USD"
    amount: Optional[float] = None  # None = unknown
    per_1k_input: Optional[float] = None
    per_1k_output: Optional[float] = None
    known: bool = False
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "currency": self.currency,
            "amount": self.amount,
            "per_1k_input": self.per_1k_input,
            "per_1k_output": self.per_1k_output,
            "known": self.known,
            "notes": self.notes,
        }


class InferenceEngine(ABC):
    """Uniform local/cloud provider interface for SaathiOS.

    Engines execute. They do **not** own final routing — that stays with
    ``saathi.model_router.ModelRouter``.
    """

    engine_id: str = "base"
    is_cloud: bool = False

    @abstractmethod
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
        """Produce a completion."""

    @abstractmethod
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
        """Yield streaming chunks. Implementations must be async generators."""
        if False:  # pragma: no cover — satisfies type checkers
            yield StreamChunk()

    @abstractmethod
    async def health(self) -> dict[str, Any]:
        """Return health status dict with at least ``ok: bool``."""

    @abstractmethod
    async def list_models(self) -> list[str]:
        """Model identifiers available on this engine."""

    async def estimate_cost(
        self,
        *,
        model: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
    ) -> CostEstimate:
        """Default: unknown cost (safe — never invent dollars)."""
        if not self.is_cloud:
            return CostEstimate(amount=0.0, known=True, notes="local inference")
        return CostEstimate(known=False, notes="cost not configured for this engine")

    async def capabilities(self) -> EngineCapabilities:
        """Default capability claim (engines should override)."""
        return EngineCapabilities(local=not self.is_cloud)

    def can_serve(self, model: str) -> bool:
        return True

    async def close(self) -> None:
        return None
