"""FM-I6 local model transports: mock + hardened loopback Ollama HTTP.

Never starts/stops/kills Ollama. Never pulls models. No proxy, no redirects,
no non-loopback endpoints.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterator, List, Mapping, Optional, Protocol, Sequence, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener, ProxyHandler
import io
import json
import socket
import threading
import time

from saathi.agent_runtime.harness.local_model_types import (
    ALLOWED_ENDPOINT,
    CONNECT_TIMEOUT_S,
    FIRST_TOKEN_TIMEOUT_S,
    INTER_TOKEN_TIMEOUT_S,
    MAX_NDJSON_LINE_BYTES,
    MAX_STREAM_RESPONSE_BYTES,
    MAX_TRANSIENT_CONNECT_RETRIES,
    MODEL_LOAD_WAIT_S,
    ModelInventoryEntry,
    PINNED_MODEL,
    PINNED_MODEL_DIGEST,
    PRIVATE_COT_KEYS,
    RuntimeInventory,
    StreamChunk,
    TOTAL_TURN_TIMEOUT_S,
    validate_loopback_endpoint,
    version_compatible,
)


class TransportError(Exception):
    def __init__(self, kind: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.kind = kind
        self.message = message
        self.retryable = retryable


class LocalModelTransport(Protocol):
    def inventory(self) -> RuntimeInventory: ...

    def stream_chat(
        self,
        *,
        model: str,
        messages: Sequence[Mapping[str, str]],
        options: Mapping[str, Any],
        cancel_event: threading.Event,
        correlation_id: str,
    ) -> Iterator[StreamChunk]: ...

    def close(self) -> None: ...


# ── NDJSON decoder ──────────────────────────────────────────────────────────


@dataclass
class NdjsonStreamDecoder:
    """Incremental NDJSON decoder for Ollama /api/chat streams."""

    max_line_bytes: int = MAX_NDJSON_LINE_BYTES
    max_total_bytes: int = MAX_STREAM_RESPONSE_BYTES
    _buf: bytearray = field(default_factory=bytearray)
    _total: int = 0
    _terminal_seen: bool = False
    _closed: bool = False

    def feed(self, data: bytes) -> List[StreamChunk]:
        if self._closed:
            raise TransportError("MALFORMED_STREAM", "feed after close")
        if not data:
            return []
        self._total += len(data)
        if self._total > self.max_total_bytes:
            raise TransportError("OUTPUT_LIMIT", "stream response exceeded size limit")
        self._buf.extend(data)
        if len(self._buf) > self.max_line_bytes * 4:
            # Prevent unbounded partial-line growth.
            if b"\n" not in self._buf:
                raise TransportError("MALFORMED_STREAM", "partial line exceeds buffer")
        out: List[StreamChunk] = []
        while True:
            nl = self._buf.find(b"\n")
            if nl < 0:
                break
            line = bytes(self._buf[:nl])
            del self._buf[: nl + 1]
            chunk = self._parse_line(line)
            if chunk is not None:
                out.append(chunk)
        return out

    def finish(self) -> List[StreamChunk]:
        self._closed = True
        out: List[StreamChunk] = []
        if self._buf:
            chunk = self._parse_line(bytes(self._buf))
            self._buf.clear()
            if chunk is not None:
                out.append(chunk)
        if not self._terminal_seen and not any(c.done or c.error for c in out):
            # Connection closed without terminal marker.
            raise TransportError("MALFORMED_STREAM", "stream ended without terminal marker")
        return out

    def _parse_line(self, line: bytes) -> Optional[StreamChunk]:
        if not line.strip():
            return None
        if len(line) > self.max_line_bytes:
            raise TransportError("MALFORMED_STREAM", "ndjson line too large")
        if self._terminal_seen:
            raise TransportError("MALFORMED_STREAM", "data after terminal marker")
        try:
            text = line.decode("utf-8")
        except UnicodeDecodeError as e:
            raise TransportError("MALFORMED_STREAM", f"invalid unicode: {e}") from e
        try:
            obj = json.loads(text)
        except json.JSONDecodeError as e:
            raise TransportError("MALFORMED_JSON", f"invalid json: {e}") from e
        if not isinstance(obj, dict):
            raise TransportError("MALFORMED_JSON", "ndjson object must be a dict")
        if obj.get("error"):
            err = obj.get("error")
            msg = err if isinstance(err, str) else json.dumps(err)[:200]
            raise TransportError("RUNTIME_ERROR", msg)
        thinking_stripped = False
        # Strip private CoT / thinking fields without emitting them.
        for k in list(obj.keys()):
            if k in PRIVATE_COT_KEYS or k.lower() in PRIVATE_COT_KEYS:
                thinking_stripped = True
                obj.pop(k, None)
            elif isinstance(obj.get(k), dict):
                inner = obj[k]
                for ik in list(inner.keys()):
                    if ik in PRIVATE_COT_KEYS or ik.lower() in PRIVATE_COT_KEYS:
                        thinking_stripped = True
                        inner.pop(ik, None)
        message = obj.get("message") if isinstance(obj.get("message"), dict) else {}
        content = ""
        if message:
            for k in list(message.keys()):
                if k in PRIVATE_COT_KEYS or k.lower() in PRIVATE_COT_KEYS:
                    thinking_stripped = True
                    message.pop(k, None)
            raw_c = message.get("content")
            if isinstance(raw_c, str):
                content = raw_c
        elif isinstance(obj.get("response"), str):
            content = obj["response"]
        done = bool(obj.get("done"))
        if done:
            self._terminal_seen = True
        keys = tuple(sorted(str(k) for k in obj.keys()))
        return StreamChunk(
            text=content,
            done=done,
            raw_keys=keys,
            thinking_stripped=thinking_stripped,
        )


# ── Mock transport ──────────────────────────────────────────────────────────


@dataclass
class MockScript:
    """Scripted mock behavior for deterministic tests."""

    inventory: Optional[RuntimeInventory] = None
    chunks: Tuple[StreamChunk, ...] = ()
    fail_on_inventory: Optional[TransportError] = None
    fail_on_stream: Optional[TransportError] = None
    fail_after_n_chunks: Optional[int] = None
    fail_with: Optional[TransportError] = None
    delay_per_chunk_s: float = 0.0
    hang_until_cancel: bool = False
    raw_ndjson_lines: Optional[Tuple[str, ...]] = None  # exercise decoder
    connect_fail_count: int = 0  # first N stream attempts fail as retryable


class MockOllamaTransport:
    """Deterministic in-process transport. No network."""

    def __init__(
        self,
        script: Optional[MockScript] = None,
        *,
        clock: Optional[Callable[[], float]] = None,
    ) -> None:
        self._script = script or MockScript(
            inventory=RuntimeInventory(
                reachable=True,
                version="0.32.5",
                models=(
                    ModelInventoryEntry(
                        name=PINNED_MODEL,
                        digest=PINNED_MODEL_DIGEST,
                        size_bytes=986_061_892,
                    ),
                ),
                loaded_models=(),
                bindings=("127.0.0.1:11434",),
            ),
            chunks=(
                StreamChunk(text="Hello", done=False),
                StreamChunk(text=" world", done=False),
                StreamChunk(text="", done=True),
            ),
        )
        self._clock = clock or time.time
        self._closed = False
        self._stream_attempts = 0
        self._lock = threading.Lock()

    def set_script(self, script: MockScript) -> None:
        with self._lock:
            self._script = script
            self._stream_attempts = 0

    def inventory(self) -> RuntimeInventory:
        if self._closed:
            raise TransportError("ENDPOINT_UNAVAILABLE", "transport closed")
        s = self._script
        if s.fail_on_inventory is not None:
            raise s.fail_on_inventory
        if s.inventory is None:
            raise TransportError("ENDPOINT_UNAVAILABLE", "no inventory")
        return s.inventory

    def stream_chat(
        self,
        *,
        model: str,
        messages: Sequence[Mapping[str, str]],
        options: Mapping[str, Any],
        cancel_event: threading.Event,
        correlation_id: str,
    ) -> Iterator[StreamChunk]:
        if self._closed:
            raise TransportError("ENDPOINT_UNAVAILABLE", "transport closed")
        with self._lock:
            self._stream_attempts += 1
            attempt = self._stream_attempts
            s = self._script
        if s.connect_fail_count and attempt <= s.connect_fail_count:
            raise TransportError(
                "ENDPOINT_UNAVAILABLE",
                "transient connect failure",
                retryable=True,
            )
        if s.fail_on_stream is not None:
            raise s.fail_on_stream
        if cancel_event.is_set():
            raise TransportError("CANCELLED", "cancelled before stream")
        if s.hang_until_cancel:
            while not cancel_event.is_set():
                time.sleep(0.01)
            raise TransportError("CANCELLED", "cancelled during hang")
        if s.raw_ndjson_lines is not None:
            dec = NdjsonStreamDecoder()
            for line in s.raw_ndjson_lines:
                if cancel_event.is_set():
                    raise TransportError("CANCELLED", "cancelled mid-stream")
                for ch in dec.feed((line + "\n").encode("utf-8")):
                    yield ch
            for ch in dec.finish():
                yield ch
            return
        n = 0
        for ch in s.chunks:
            if cancel_event.is_set():
                raise TransportError("CANCELLED", "cancelled mid-stream")
            if s.delay_per_chunk_s:
                time.sleep(s.delay_per_chunk_s)
            if s.fail_after_n_chunks is not None and n >= s.fail_after_n_chunks:
                err = s.fail_with or TransportError("MALFORMED_STREAM", "scripted fail")
                raise err
            n += 1
            yield ch

    def cancel_active(self) -> None:
        """Mock has no socket; cancel is via cancel_event only."""

    def close(self) -> None:
        self._closed = True


# ── Loopback Ollama transport ───────────────────────────────────────────────


class LoopbackOllamaTransport:
    """Hardened HTTP client for fixed loopback Ollama only.

    - No proxy inheritance
    - No redirects
    - Endpoint structurally validated to 127.0.0.1:11434
    - No process control / model pull
    """

    def __init__(
        self,
        endpoint: str = ALLOWED_ENDPOINT,
        *,
        connect_timeout_s: float = CONNECT_TIMEOUT_S,
        read_timeout_s: float = TOTAL_TURN_TIMEOUT_S,
        opener_factory: Optional[Callable[[], Any]] = None,
    ) -> None:
        self.endpoint = validate_loopback_endpoint(endpoint)
        self.connect_timeout_s = connect_timeout_s
        self.read_timeout_s = read_timeout_s
        # ProxyHandler({}) disables proxy env inheritance.
        self._opener = (opener_factory or (lambda: build_opener(ProxyHandler({}))))()
        self._closed = False
        self._active_resp: Any = None
        self._lock = threading.Lock()

    def cancel_active(self) -> None:
        """Abort in-flight HTTP body only; transport remains usable."""
        with self._lock:
            resp = self._active_resp
            self._active_resp = None
        if resp is not None:
            try:
                resp.close()
            except Exception:
                pass

    def close(self) -> None:
        self._closed = True
        self.cancel_active()

    def _request(
        self,
        method: str,
        path: str,
        body: Optional[dict] = None,
        *,
        timeout: float,
        stream: bool = False,
    ) -> Any:
        if self._closed:
            raise TransportError("ENDPOINT_UNAVAILABLE", "transport closed")
        if not path.startswith("/"):
            raise TransportError("ENDPOINT_INVALID", "path must be absolute")
        # Path allowlist
        allowed_prefixes = ("/api/tags", "/api/ps", "/api/show", "/api/chat", "/api/version")
        if not any(path == p or path.startswith(p + "?") for p in allowed_prefixes):
            raise TransportError("ENDPOINT_INVALID", f"path not allowed: {path}")
        url = f"{self.endpoint}{path}"
        data = None
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
        req = Request(url, data=data, headers=headers, method=method)
        try:
            # urllib does not follow redirects for non-http by default; we still
            # refuse Location-based re-requests by not implementing redirect handlers.
            resp = self._opener.open(req, timeout=timeout)
        except HTTPError as e:
            raise TransportError("RUNTIME_ERROR", f"http {e.code}", retryable=False) from e
        except (URLError, socket.timeout, TimeoutError, ConnectionError, OSError) as e:
            retryable = True
            raise TransportError(
                "ENDPOINT_UNAVAILABLE",
                f"unreachable: {getattr(e, 'reason', e)}",
                retryable=retryable,
            ) from e
        if stream:
            return resp
        try:
            raw = resp.read()
            if not raw:
                return {}
            return json.loads(raw.decode("utf-8"))
        finally:
            resp.close()

    def inventory(self) -> RuntimeInventory:
        try:
            tags = self._request("GET", "/api/tags", timeout=self.connect_timeout_s)
        except TransportError as e:
            return RuntimeInventory(reachable=False, detail=e.message)
        version = ""
        try:
            # Ollama may not always expose /api/version; tolerate failure.
            ver = self._request("GET", "/api/version", timeout=self.connect_timeout_s)
            if isinstance(ver, dict):
                version = str(ver.get("version") or "")
        except TransportError:
            version = ""
        models: List[ModelInventoryEntry] = []
        for m in (tags.get("models") or []) if isinstance(tags, dict) else []:
            if not isinstance(m, dict):
                continue
            name = str(m.get("name") or m.get("model") or "")
            digest = str(m.get("digest") or "")
            # Some Ollama versions nest digest under details
            if not digest and isinstance(m.get("details"), dict):
                digest = str(m["details"].get("digest") or "")
            size = int(m.get("size") or 0)
            if name:
                models.append(ModelInventoryEntry(name=name, digest=digest, size_bytes=size))
        loaded: List[str] = []
        try:
            ps = self._request("GET", "/api/ps", timeout=self.connect_timeout_s)
            for m in (ps.get("models") or []) if isinstance(ps, dict) else []:
                if isinstance(m, dict):
                    n = str(m.get("name") or m.get("model") or "")
                    if n:
                        loaded.append(n)
        except TransportError:
            pass
        return RuntimeInventory(
            reachable=True,
            version=version,
            models=tuple(models),
            loaded_models=tuple(loaded),
            bindings=("127.0.0.1:11434",),  # client-side target; OS bind separate
            detail="ok",
        )

    def stream_chat(
        self,
        *,
        model: str,
        messages: Sequence[Mapping[str, str]],
        options: Mapping[str, Any],
        cancel_event: threading.Event,
        correlation_id: str,
    ) -> Iterator[StreamChunk]:
        payload = {
            "model": model,
            "messages": list(messages),
            "stream": True,
            "options": dict(options),
        }
        # At most one transient connect retry before any output.
        last_err: Optional[TransportError] = None
        resp = None
        for attempt in range(MAX_TRANSIENT_CONNECT_RETRIES + 1):
            if cancel_event.is_set():
                raise TransportError("CANCELLED", "cancelled before connect")
            try:
                resp = self._request(
                    "POST",
                    "/api/chat",
                    payload,
                    timeout=self.read_timeout_s,
                    stream=True,
                )
                last_err = None
                break
            except TransportError as e:
                last_err = e
                if not e.retryable or attempt >= MAX_TRANSIENT_CONNECT_RETRIES:
                    raise
                continue
        if last_err is not None or resp is None:
            raise last_err or TransportError("ENDPOINT_UNAVAILABLE", "no response")
        with self._lock:
            self._active_resp = resp
        dec = NdjsonStreamDecoder()
        start = time.monotonic()
        last_chunk_at = start
        first = True
        try:
            while True:
                if cancel_event.is_set():
                    raise TransportError("CANCELLED", "cancelled during stream")
                now = time.monotonic()
                if now - start > TOTAL_TURN_TIMEOUT_S:
                    raise TransportError("TIMEOUT", "total turn timeout")
                if first and now - start > max(FIRST_TOKEN_TIMEOUT_S, MODEL_LOAD_WAIT_S):
                    raise TransportError("TIMEOUT", "first token / model load timeout")
                if not first and now - last_chunk_at > INTER_TOKEN_TIMEOUT_S:
                    raise TransportError("TIMEOUT", "inter-token timeout")
                # Bounded read
                try:
                    chunk = resp.read(4096)
                except Exception as e:
                    if cancel_event.is_set():
                        raise TransportError("CANCELLED", "cancelled during read") from e
                    raise TransportError("ENDPOINT_UNAVAILABLE", f"read failed: {e}") from e
                if not chunk:
                    for ch in dec.finish():
                        yield ch
                    break
                for ch in dec.feed(chunk):
                    last_chunk_at = time.monotonic()
                    if ch.text or ch.done:
                        first = False
                    yield ch
                    if ch.done:
                        return
        finally:
            try:
                resp.close()
            except Exception:
                pass
            with self._lock:
                if self._active_resp is resp:
                    self._active_resp = None


def check_os_bindings_loopback_only(listener_lines: Sequence[str]) -> Tuple[bool, str]:
    """Parse lsof-style lines; return (safe, reason).

    Safe only if every 11434 listener is 127.0.0.1 or [::1]/1.
    Wildcard (*), 0.0.0.0, or other addresses → unsafe.
    """
    found = False
    for line in listener_lines:
        if "11434" not in line:
            continue
        found = True
        # Expect TOKEN like 127.0.0.1:11434 or *:11434 or [::1]:11434
        for token in line.split():
            if ":11434" not in token and "11434" not in token:
                continue
            addr = token
            # Strip IPv6 brackets form
            if addr.startswith("[") and "]:11434" in addr:
                host = addr[1 : addr.index("]")]
            elif addr.endswith(":11434"):
                host = addr[: -len(":11434")]
            else:
                continue
            if host in ("127.0.0.1", "::1"):
                continue
            if host in ("*", "0.0.0.0", "::"):
                return False, f"LIVE_OLLAMA_BINDING_UNSAFE: listener {addr}"
            # Any other host is non-loopback
            if host not in ("127.0.0.1", "::1"):
                return False, f"LIVE_OLLAMA_BINDING_UNSAFE: non-loopback {addr}"
    if not found:
        return False, "LIVE_OLLAMA_BINDING_UNSAFE: no listeners found"
    return True, "loopback_only"
