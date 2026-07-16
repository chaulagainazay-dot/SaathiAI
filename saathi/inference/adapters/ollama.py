"""Ollama inference adapter (local-first).

Uses the Ollama HTTP API. Does not download models. No automatic cloud routing.
"""
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


def _default_host() -> str:
    host = os.getenv("OLLAMA_HOST") or os.getenv("OLLAMA_URL") or "http://127.0.0.1:11434"
    # config may store OpenAI-compatible /v1 suffix — strip for native API
    host = host.rstrip("/")
    if host.endswith("/v1"):
        host = host[:-3]
    return host


class OllamaEngine(InferenceEngine):
    engine_id = "ollama"
    is_cloud = False

    def __init__(
        self,
        host: Optional[str] = None,
        *,
        default_model: Optional[str] = None,
        transport: Optional[Callable[..., Any]] = None,
    ):
        self.host = (host or _default_host()).rstrip("/")
        self.default_model = default_model or os.getenv("OLLAMA_MODEL", "qwen2.5:3b")
        # transport(method, url, body=None, timeout=None) -> dict|str|bytes
        self._transport = transport

    def _request(
        self,
        method: str,
        path: str,
        body: Optional[dict] = None,
        *,
        timeout: float = 30.0,
        stream: bool = False,
    ) -> Any:
        url = f"{self.host}{path}"
        if self._transport is not None:
            return self._transport(method, url, body=body, timeout=timeout, stream=stream)
        data = None
        headers = {"Content-Type": "application/json"}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
        req = Request(url, data=data, headers=headers, method=method)
        try:
            with urlopen(req, timeout=timeout) as resp:  # nosec B310 — local/user-configured host
                raw = resp.read()
                if not raw:
                    return {}
                return json.loads(raw.decode("utf-8"))
        except HTTPError as e:
            raise EngineError(f"ollama HTTP {e.code}: {e.reason}") from e
        except URLError as e:
            raise EngineUnhealthyError(f"ollama unreachable: {e.reason}") from e
        except TimeoutError as e:
            raise EngineTimeoutError("ollama timeout") from e

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
                "stream": False,
                "options": {
                    "temperature": temperature,
                    "num_predict": max_tokens,
                },
            }
            data = self._request("POST", "/api/chat", payload, timeout=timeout or 60.0)
            if not isinstance(data, dict):
                raise EngineError("unexpected ollama response")
            msg = data.get("message") or {}
            text = msg.get("content") or data.get("response") or ""
            usage = {
                "prompt_tokens": data.get("prompt_eval_count"),
                "completion_tokens": data.get("eval_count"),
            }
            return GenerateResult(
                text=text,
                model=model,
                engine_id=self.engine_id,
                usage={k: v for k, v in usage.items() if v is not None},
                latency_ms=(time.monotonic() - t0) * 1000,
                raw=data if kwargs.get("include_raw") else None,
            )
        except (EngineError, EngineTimeoutError, EngineUnhealthyError):
            raise
        except Exception as e:
            ne = normalize_error(e, provider=self.engine_id, model=model)
            if ne.code == "engine_timeout":
                raise EngineTimeoutError(ne.message, cause=e) from e
            if ne.code == "engine_unhealthy":
                raise EngineUnhealthyError(ne.message, cause=e) from e
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
        # Minimal streaming: single-shot generate then yield once (safe offline).
        # Real NDJSON streaming can be added when transport supports stream=True.
        result = await self.generate(
            messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
            **kwargs,
        )
        if result.text:
            yield StreamChunk(content=result.text)
        yield StreamChunk(finish_reason=result.finish_reason, usage=result.usage)

    async def health(self) -> dict[str, Any]:
        try:
            data = self._request("GET", "/api/tags", timeout=3.0)
            ok = isinstance(data, dict)
            return {"ok": ok, "engine_id": self.engine_id, "host": self.host}
        except Exception as e:
            return {
                "ok": False,
                "engine_id": self.engine_id,
                "host": self.host,
                "error": str(e),
            }

    async def list_models(self) -> list[str]:
        data = self._request("GET", "/api/tags", timeout=5.0)
        if not isinstance(data, dict):
            return []
        models = data.get("models") or []
        out = []
        for m in models:
            if isinstance(m, dict) and m.get("name"):
                out.append(str(m["name"]))
            elif isinstance(m, str):
                out.append(m)
        return out

    async def estimate_cost(
        self,
        *,
        model: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
    ) -> CostEstimate:
        return CostEstimate(amount=0.0, known=True, notes="local ollama")

    async def capabilities(self) -> EngineCapabilities:
        return EngineCapabilities(
            streaming=True,
            tool_calling=True,
            structured_output=True,
            vision=False,
            audio=False,
            local=True,
            notes="ollama local runtime",
        )
