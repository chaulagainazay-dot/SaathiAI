"""Conversation providers — Ollama-compatible local + unavailable + test inject.

Never auto-downloads models. Never uses shell=True. No public listeners.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
import socket
import threading
import time
import urllib.error
import urllib.request
from typing import Any, Callable, Iterator, Protocol
from urllib.parse import urlparse

from .models import (
    GENERATION_TIMEOUT_SEC,
    MAX_RESPONSE_CHARS,
    MAX_TOKENS_CEILING,
    ConversationResult,
    ConversationStreamEvent,
    StreamEventType,
)


def _ollama_host() -> str:
    host = os.getenv("OLLAMA_HOST") or os.getenv("OLLAMA_URL") or "http://127.0.0.1:11434"
    host = host.rstrip("/")
    if host.endswith("/v1"):
        host = host[:-3]
    return host


def _prefer_model() -> str:
    # Prefer lightweight model on M2/8GB
    return os.getenv("SAATHI_CONVERSATION_MODEL") or os.getenv("OLLAMA_MODEL") or "qwen2.5:1.5b"


def _is_local_host(url: str) -> bool:
    try:
        parsed = urlparse(url)
        hostname = (parsed.hostname or "").lower()
        return hostname in {"127.0.0.1", "localhost", "::1"}
    except Exception:
        return False


@dataclass
class ProviderHealth:
    provider_id: str
    adapter_implemented: bool = True
    executable_available: bool = False
    model_configured: bool = False
    model_loaded: bool = False
    generation_healthy: bool = False
    streaming_healthy: bool = False
    tool_calling_supported: bool = False
    certified: bool = False
    model: str = ""
    detail: str = ""
    auto_download: bool = False

    def to_public(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "adapter_implemented": self.adapter_implemented,
            "executable_available": self.executable_available,
            "model_configured": self.model_configured,
            "model_loaded": self.model_loaded,
            "generation_healthy": self.generation_healthy,
            "streaming_healthy": self.streaming_healthy,
            "tool_calling_supported": self.tool_calling_supported,
            "certified": self.certified,
            "model": self.model,
            "detail": self.detail,
            "auto_download": self.auto_download,
            "state": (
                "ready"
                if self.generation_healthy
                else ("unavailable" if not self.executable_available else "degraded")
            ),
        }


class ConversationProvider(Protocol):
    provider_id: str

    def health(self) -> ProviderHealth: ...

    def cancel(self, request_id: str) -> None: ...

    def stream(
        self,
        messages: list[dict[str, str]],
        *,
        request_id: str,
        model: str = "",
        max_tokens: int = 512,
        timeout_seconds: float = GENERATION_TIMEOUT_SEC,
        temperature: float = 0.5,
    ) -> Iterator[ConversationStreamEvent]: ...


class UnavailableConversationProvider:
    provider_id = "unavailable"

    def health(self) -> ProviderHealth:
        return ProviderHealth(
            provider_id=self.provider_id,
            adapter_implemented=True,
            executable_available=False,
            model_configured=False,
            detail="No conversational model is available.",
            auto_download=False,
        )

    def cancel(self, request_id: str) -> None:
        return None

    def stream(
        self,
        messages: list[dict[str, str]],
        *,
        request_id: str,
        model: str = "",
        max_tokens: int = 512,
        timeout_seconds: float = GENERATION_TIMEOUT_SEC,
        temperature: float = 0.5,
    ) -> Iterator[ConversationStreamEvent]:
        yield ConversationStreamEvent(
            event=StreamEventType.FAILED.value,
            request_id=request_id,
            provider=self.provider_id,
            model=model or "",
            error_code="MODEL_NOT_AVAILABLE",
            error_message="No configured conversational model is available.",
        )


class InjectedConversationProvider:
    """Test-only deterministic provider — never used as real model intelligence."""

    provider_id = "test_injected"

    def __init__(self, reply_fn: Callable[[list[dict[str, str]]], str] | None = None):
        self._reply_fn = reply_fn
        self._cancel: set[str] = set()
        self._lock = threading.Lock()

    def health(self) -> ProviderHealth:
        return ProviderHealth(
            provider_id=self.provider_id,
            adapter_implemented=True,
            executable_available=True,
            model_configured=True,
            model_loaded=True,
            generation_healthy=True,
            streaming_healthy=True,
            model="test-inject",
            detail="Deterministic test provider only.",
            certified=False,
        )

    def cancel(self, request_id: str) -> None:
        with self._lock:
            self._cancel.add(request_id)

    def stream(
        self,
        messages: list[dict[str, str]],
        *,
        request_id: str,
        model: str = "",
        max_tokens: int = 512,
        timeout_seconds: float = GENERATION_TIMEOUT_SEC,
        temperature: float = 0.5,
    ) -> Iterator[ConversationStreamEvent]:
        yield ConversationStreamEvent(
            event=StreamEventType.STARTED.value,
            request_id=request_id,
            provider=self.provider_id,
            model=model or "test-inject",
        )
        if self._reply_fn:
            text = self._reply_fn(messages)
        else:
            user = next(
                (m["content"] for m in reversed(messages) if m.get("role") == "user"),
                "",
            )
            # Echo with multi-turn awareness for tests
            prior = [m for m in messages if m.get("role") == "assistant"]
            if prior:
                text = f"Following up on prior context ({len(prior)} turns): {user}"
            else:
                text = f"Test reply about: {user}"
        words = text.split()
        seq = 0
        buf: list[str] = []
        for word in words:
            with self._lock:
                if request_id in self._cancel:
                    yield ConversationStreamEvent(
                        event=StreamEventType.CANCELLED.value,
                        request_id=request_id,
                        provider=self.provider_id,
                        model=model or "test-inject",
                        cancelled=True,
                        text=" ".join(buf),
                        partial=True,
                        sequence=seq,
                    )
                    return
            buf.append(word)
            if len(buf) >= 4 or word[-1:] in ".!?":
                chunk = " ".join(buf)
                seq += 1
                yield ConversationStreamEvent(
                    event=StreamEventType.TEXT_DELTA.value,
                    request_id=request_id,
                    text=chunk,
                    partial=True,
                    provider=self.provider_id,
                    model=model or "test-inject",
                    sequence=seq,
                )
                buf = []
        if buf:
            seq += 1
            yield ConversationStreamEvent(
                event=StreamEventType.TEXT_DELTA.value,
                request_id=request_id,
                text=" ".join(buf),
                partial=True,
                provider=self.provider_id,
                model=model or "test-inject",
                sequence=seq,
            )
        with self._lock:
            if request_id in self._cancel:
                yield ConversationStreamEvent(
                    event=StreamEventType.LATE_CHUNK_REJECTED.value,
                    request_id=request_id,
                    provider=self.provider_id,
                    cancelled=True,
                    sequence=seq + 1,
                )
                return
        yield ConversationStreamEvent(
            event=StreamEventType.COMPLETED.value,
            request_id=request_id,
            text=text[:MAX_RESPONSE_CHARS],
            partial=False,
            provider=self.provider_id,
            model=model or "test-inject",
            sequence=seq + 1,
        )


class OllamaConversationProvider:
    """Local Ollama-compatible chat provider with real NDJSON streaming."""

    provider_id = "ollama_local"

    def __init__(
        self,
        host: str | None = None,
        *,
        default_model: str | None = None,
        preferred_models: list[str] | None = None,
    ):
        self.host = (host or _ollama_host()).rstrip("/")
        self.default_model = default_model or _prefer_model()
        self.preferred_models = preferred_models or [
            "qwen2.5:1.5b",
            "qwen2.5:3b",
            "qwen3:8b",
            "gemma4:e2b",
        ]
        self._cancel: set[str] = set()
        self._lock = threading.Lock()
        self._installed: list[str] = []
        self._last_health_at = 0.0
        self._last_health: ProviderHealth | None = None

    def cancel(self, request_id: str) -> None:
        with self._lock:
            self._cancel.add(request_id)

    def is_cancelled(self, request_id: str) -> bool:
        with self._lock:
            return request_id in self._cancel

    def clear_cancel(self, request_id: str) -> None:
        with self._lock:
            self._cancel.discard(request_id)

    def _http_json(
        self, method: str, path: str, body: dict | None = None, *, timeout: float = 5.0
    ) -> Any:
        if not _is_local_host(self.host):
            raise RuntimeError("non_local_ollama_host_denied")
        data = None
        headers = {"Content-Type": "application/json"}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            f"{self.host}{path}", data=data, headers=headers, method=method
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec B310 local only
            raw = resp.read()
            if not raw:
                return {}
            return json.loads(raw.decode("utf-8"))

    def _list_models(self) -> list[str]:
        try:
            data = self._http_json("GET", "/api/tags", timeout=3.0)
            models = []
            for item in data.get("models") or []:
                name = str(item.get("name") or item.get("model") or "").strip()
                if name:
                    models.append(name)
            self._installed = models
            return models
        except Exception:
            self._installed = []
            return []

    def resolve_model(self, requested: str = "") -> str:
        installed = self._list_models()
        if requested and any(requested == m or m.startswith(requested) for m in installed):
            return requested
        for pref in self.preferred_models:
            for m in installed:
                if m == pref or m.startswith(pref.split(":")[0]):
                    if pref in m or m == pref:
                        return m
            for m in installed:
                if pref.split(":")[0] in m:
                    return m
        if self.default_model:
            for m in installed:
                if self.default_model in m or m.startswith(self.default_model):
                    return m
        return installed[0] if installed else (requested or self.default_model)

    def health(self) -> ProviderHealth:
        now = time.time()
        if self._last_health and now - self._last_health_at < 5.0:
            return self._last_health
        if not _is_local_host(self.host):
            h = ProviderHealth(
                provider_id=self.provider_id,
                adapter_implemented=True,
                detail="Only localhost Ollama is allowed.",
            )
            self._last_health = h
            self._last_health_at = now
            return h
        # TCP probe
        try:
            parsed = urlparse(self.host)
            port = parsed.port or 11434
            with socket.create_connection((parsed.hostname, port), timeout=1.5):
                pass
            reachable = True
        except Exception:
            reachable = False
        models = self._list_models() if reachable else []
        model = self.resolve_model(self.default_model) if models else self.default_model
        model_present = bool(models) and any(
            model == m or m.startswith(model.split(":")[0]) for m in models
        )
        h = ProviderHealth(
            provider_id=self.provider_id,
            adapter_implemented=True,
            executable_available=reachable,
            model_configured=bool(model),
            model_loaded=model_present,
            generation_healthy=reachable and model_present,
            streaming_healthy=reachable and model_present,
            tool_calling_supported=False,  # conversation path does not grant tools
            certified=reachable and model_present,
            model=model if model_present else model,
            detail=(
                f"Ollama reachable; model={model}"
                if reachable and model_present
                else (
                    "Ollama not reachable on localhost"
                    if not reachable
                    else f"Model not installed among {models[:5]}"
                )
            ),
            auto_download=False,
        )
        self._last_health = h
        self._last_health_at = now
        return h

    def stream(
        self,
        messages: list[dict[str, str]],
        *,
        request_id: str,
        model: str = "",
        max_tokens: int = 512,
        timeout_seconds: float = GENERATION_TIMEOUT_SEC,
        temperature: float = 0.5,
    ) -> Iterator[ConversationStreamEvent]:
        self.clear_cancel(request_id)
        health = self.health()
        chosen = self.resolve_model(model or self.default_model)
        if not health.generation_healthy:
            yield ConversationStreamEvent(
                event=StreamEventType.FAILED.value,
                request_id=request_id,
                provider=self.provider_id,
                model=chosen,
                error_code="MODEL_NOT_AVAILABLE",
                error_message=health.detail or "Local model not available.",
            )
            return

        yield ConversationStreamEvent(
            event=StreamEventType.STARTED.value,
            request_id=request_id,
            provider=self.provider_id,
            model=chosen,
        )

        payload = {
            "model": chosen,
            "messages": messages,
            "stream": True,
            "options": {
                "temperature": float(temperature),
                "num_predict": int(max(16, min(int(max_tokens), MAX_TOKENS_CEILING))),
            },
        }
        if not _is_local_host(self.host):
            yield ConversationStreamEvent(
                event=StreamEventType.FAILED.value,
                request_id=request_id,
                provider=self.provider_id,
                error_code="NON_LOCAL_DENIED",
                error_message="Remote Ollama hosts are not allowed.",
            )
            return

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.host}/api/chat",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        assembled: list[str] = []
        seq = 0
        try:
            with urllib.request.urlopen(  # nosec B310 local only
                req, timeout=max(5.0, min(float(timeout_seconds), 120.0))
            ) as resp:
                while True:
                    if self.is_cancelled(request_id):
                        yield ConversationStreamEvent(
                            event=StreamEventType.CANCELLED.value,
                            request_id=request_id,
                            provider=self.provider_id,
                            model=chosen,
                            text="".join(assembled)[:MAX_RESPONSE_CHARS],
                            partial=True,
                            cancelled=True,
                            sequence=seq,
                        )
                        # Drain may continue; reject late chunks
                        return
                    line = resp.readline()
                    if not line:
                        break
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line.decode("utf-8"))
                    except Exception:
                        continue
                    if self.is_cancelled(request_id):
                        yield ConversationStreamEvent(
                            event=StreamEventType.LATE_CHUNK_REJECTED.value,
                            request_id=request_id,
                            provider=self.provider_id,
                            model=chosen,
                            cancelled=True,
                            sequence=seq + 1,
                        )
                        return
                    msg = chunk.get("message") or {}
                    piece = msg.get("content") or chunk.get("response") or ""
                    if piece:
                        assembled.append(piece)
                        seq += 1
                        yield ConversationStreamEvent(
                            event=StreamEventType.TEXT_DELTA.value,
                            request_id=request_id,
                            text=piece,
                            partial=True,
                            provider=self.provider_id,
                            model=chosen,
                            sequence=seq,
                        )
                    if chunk.get("done"):
                        break
        except urllib.error.HTTPError as exc:
            yield ConversationStreamEvent(
                event=StreamEventType.FAILED.value,
                request_id=request_id,
                provider=self.provider_id,
                model=chosen,
                error_code="PROVIDER_HTTP",
                error_message=f"Ollama HTTP {exc.code}",
            )
            return
        except Exception as exc:
            yield ConversationStreamEvent(
                event=StreamEventType.FAILED.value,
                request_id=request_id,
                provider=self.provider_id,
                model=chosen,
                error_code="PROVIDER_ERROR",
                error_message="Local generation failed.",
            )
            return

        if self.is_cancelled(request_id):
            yield ConversationStreamEvent(
                event=StreamEventType.CANCELLED.value,
                request_id=request_id,
                provider=self.provider_id,
                model=chosen,
                text="".join(assembled)[:MAX_RESPONSE_CHARS],
                partial=True,
                cancelled=True,
                sequence=seq,
            )
            return

        full = "".join(assembled)[:MAX_RESPONSE_CHARS]
        yield ConversationStreamEvent(
            event=StreamEventType.COMPLETED.value,
            request_id=request_id,
            text=full,
            partial=False,
            provider=self.provider_id,
            model=chosen,
            sequence=seq + 1,
        )


def default_providers(
    *,
    inject: InjectedConversationProvider | None = None,
) -> list[ConversationProvider]:
    providers: list[ConversationProvider] = [
        OllamaConversationProvider(),
        UnavailableConversationProvider(),
    ]
    if inject is not None:
        providers.insert(0, inject)
    return providers


def select_provider(
    prefer: str = "auto",
    providers: list[ConversationProvider] | None = None,
) -> ConversationProvider:
    catalog = providers or default_providers()
    by_id = {p.provider_id: p for p in catalog}
    if prefer and prefer not in {"", "auto"}:
        chosen = by_id.get(prefer)
        if chosen and chosen.health().generation_healthy:
            return chosen
        if prefer == "unavailable":
            return by_id.get("unavailable") or UnavailableConversationProvider()
        # Prefer truthful unavailable over unhealthy forced provider
        return by_id.get("unavailable") or UnavailableConversationProvider()
    for pid in ("test_injected", "ollama_local"):
        p = by_id.get(pid)
        if p and p.health().generation_healthy:
            return p
    ollama = by_id.get("ollama_local")
    if ollama and ollama.health().executable_available:
        # executable but maybe model missing — still return so errors are truthful
        if ollama.health().generation_healthy:
            return ollama
    return by_id.get("unavailable") or UnavailableConversationProvider()
