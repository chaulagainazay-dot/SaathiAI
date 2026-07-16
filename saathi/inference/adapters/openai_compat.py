"""OpenAI-compatible local endpoint adapter (Shimmy, llama.cpp server, LM Studio, etc.)."""
from __future__ import annotations

import json
import os
import time
from collections.abc import AsyncIterator
from typing import Any, Callable, Optional, Sequence
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from saathi.inference.engine import (
    CostEstimate,
    EngineCapabilities,
    GenerateResult,
    InferenceEngine,
    StreamChunk,
)
from saathi.inference.errors import EngineError, EngineTimeoutError, EngineUnhealthyError, normalize_error


class OpenAICompatEngine(InferenceEngine):
    engine_id = "openai_compat"
    is_cloud = False

    def __init__(
        self,
        base_url: Optional[str] = None,
        *,
        api_key: Optional[str] = None,
        default_model: Optional[str] = None,
        engine_id: str = "openai_compat",
        is_cloud: bool = False,
        transport: Optional[Callable[..., Any]] = None,
    ):
        base = base_url or os.getenv("OPENAI_COMPAT_BASE_URL") or os.getenv("SHIMMY_URL") or "http://127.0.0.1:11435/v1"
        self.base_url = base.rstrip("/")
        self.api_key = api_key if api_key is not None else (
            os.getenv("OPENAI_COMPAT_API_KEY") or os.getenv("SHIMMY_API_KEY") or "sk-local"
        )
        self.default_model = default_model or os.getenv("SHIMMY_MODEL") or "local-model"
        self.engine_id = engine_id
        self.is_cloud = is_cloud
        self._transport = transport

    def _request(
        self,
        method: str,
        path: str,
        body: Optional[dict] = None,
        *,
        timeout: float = 30.0,
    ) -> Any:
        url = f"{self.base_url}{path}"
        if self._transport is not None:
            return self._transport(method, url, body=body, timeout=timeout)
        data = None
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        if body is not None:
            data = json.dumps(body).encode("utf-8")
        req = Request(url, data=data, headers=headers, method=method)
        try:
            with urlopen(req, timeout=timeout) as resp:  # nosec B310
                raw = resp.read()
                return json.loads(raw.decode("utf-8")) if raw else {}
        except HTTPError as e:
            raise EngineError(f"openai_compat HTTP {e.code}: {e.reason}") from e
        except URLError as e:
            raise EngineUnhealthyError(f"openai_compat unreachable: {e.reason}") from e
        except TimeoutError as e:
            raise EngineTimeoutError("openai_compat timeout") from e

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
        model = model or self.default_model
        t0 = time.monotonic()
        try:
            payload = {
                "model": model,
                "messages": list(messages),
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": False,
            }
            data = self._request("POST", "/chat/completions", payload, timeout=timeout or 60.0)
            choice = (data.get("choices") or [{}])[0]
            msg = choice.get("message") or {}
            text = msg.get("content") or ""
            usage = data.get("usage") or {}
            return GenerateResult(
                text=text,
                model=model,
                engine_id=self.engine_id,
                usage=dict(usage) if isinstance(usage, dict) else {},
                latency_ms=(time.monotonic() - t0) * 1000,
                finish_reason=str(choice.get("finish_reason") or "stop"),
            )
        except (EngineError, EngineTimeoutError, EngineUnhealthyError):
            raise
        except Exception as e:
            ne = normalize_error(e, provider=self.engine_id, model=model)
            raise EngineError(ne.message, cause=e) from e

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
        result = await self.generate(
            messages, model=model, temperature=temperature, max_tokens=max_tokens, timeout=timeout, **kwargs
        )
        if result.text:
            yield StreamChunk(content=result.text)
        yield StreamChunk(finish_reason=result.finish_reason, usage=result.usage)

    async def health(self) -> dict[str, Any]:
        try:
            data = self._request("GET", "/models", timeout=3.0)
            ok = isinstance(data, dict)
            return {"ok": ok, "engine_id": self.engine_id, "base_url": self.base_url}
        except Exception as e:
            return {"ok": False, "engine_id": self.engine_id, "error": str(e)}

    async def list_models(self) -> list[str]:
        data = self._request("GET", "/models", timeout=5.0)
        items = data.get("data") if isinstance(data, dict) else None
        if not items:
            return [self.default_model]
        out = []
        for m in items:
            if isinstance(m, dict) and m.get("id"):
                out.append(str(m["id"]))
        return out or [self.default_model]

    async def estimate_cost(
        self,
        *,
        model: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
    ) -> CostEstimate:
        if self.is_cloud:
            return CostEstimate(known=False, notes="cloud openai-compat cost not configured")
        return CostEstimate(amount=0.0, known=True, notes="local openai-compatible endpoint")

    async def capabilities(self) -> EngineCapabilities:
        return EngineCapabilities(
            streaming=True,
            tool_calling=True,
            structured_output=True,
            local=not self.is_cloud,
            notes="OpenAI-compatible HTTP API",
        )
