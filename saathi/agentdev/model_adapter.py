"""M355 — Isolated local reasoning adapter.

One local model, reached over loopback, behind an interface that gives it
nothing else. The adapter is the *only* place in this package that talks to a
model, and it is deliberately small: a prompt goes in, text comes out, and
metadata about the call is recorded.

What the model cannot reach through this adapter, by construction rather than
by instruction:

============  ==============================================================
shell         no ``subprocess``, no ``os.system``; the module imports neither
filesystem    the adapter reads and writes no file
tools         there is no tool registry, no function calling, no callback
network       every request is checked against a loopback allowlist first
credentials   no header may carry authorization; a request naming one is refused
============  ==============================================================

A model that emitted ``rm -rf /`` would produce a string. Nothing in this module
can execute one, and nothing hands the string to anything that could.

**Provider neutrality.** :class:`ReasoningAdapter` is the interface; Ollama is
one implementation of it. No automatic fallback exists — if the configured
adapter is unhealthy the call fails and says so, because silently answering
from a different model would make every recorded result unattributable.

**On token counts.** Ollama reports real ``prompt_eval_count`` and
``eval_count``. When present they are recorded as ``measured``. When absent the
adapter falls back to a characters÷4 heuristic recorded as ``estimated``, and
the distinction is carried in the response rather than smoothed away.
"""
from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from typing import Any, Protocol

from saathi.agentdev.resources import HostSnapshot, host_snapshot, measure

ADAPTER_VERSION = "agentdev.model_adapter.v1"

#: The only hosts an adapter may contact. Anything else is refused before a
#: socket is opened — including a public host that would resolve to a paid API.
#: ``urlparse`` strips the brackets from an IPv6 authority, so ``::1`` is the
#: form compared here even though the URL must be written ``http://[::1]:11434``.
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})

DEFAULT_ENDPOINT = "http://127.0.0.1:11434"

#: Request options an adapter refuses to forward. Each would either grant the
#: model a capability this layer does not offer, or make a run unattributable.
FORBIDDEN_OPTION_KEYS = frozenset({
    "tools", "functions", "tool_choice", "function_call",
    "api_key", "authorization", "headers", "files", "images",
})

#: Defaults chosen for reproducibility, not for output quality: temperature 0
#: and a fixed seed so two runs of the same prompt are comparable.
DEFAULT_TEMPERATURE = 0.0
DEFAULT_SEED = 1
DEFAULT_TIMEOUT_S = 120.0
DEFAULT_MAX_ATTEMPTS = 2


class ModelAdapterError(RuntimeError):
    def __init__(self, code: str, detail: str = ""):
        self.code = code
        self.detail = detail
        super().__init__(f"{code}" + (f" ({detail})" if detail else ""))


# --------------------------------------------------------------------------
# Request and response
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ModelRequest:
    """One call. Frozen, so a retry cannot quietly send something different."""

    prompt: str
    system: str = ""
    max_tokens: int = 512
    temperature: float = DEFAULT_TEMPERATURE
    seed: int = DEFAULT_SEED
    timeout_s: float = DEFAULT_TIMEOUT_S
    json_mode: bool = False
    stop: tuple[str, ...] = ()
    label: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["stop"] = list(self.stop)
        d["prompt_chars"] = len(self.prompt)
        d["system_chars"] = len(self.system)
        return d


@dataclass
class TokenAccounting:
    prompt_tokens: int = 0
    response_tokens: int = 0
    source: str = "estimated"  # measured | estimated

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.response_tokens

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["total_tokens"] = self.total_tokens
        if self.source == "estimated":
            d["note"] = "characters divided by four; the provider reported no counts"
        return d


@dataclass
class ModelResponse:
    """Everything one call produced, including how much it cost."""

    ok: bool
    model: str
    adapter: str
    text: str = ""
    error_code: str = ""
    error_detail: str = ""
    latency_ms: float = 0.0
    attempts: int = 0
    cancelled: bool = False
    tokens: TokenAccounting = field(default_factory=TokenAccounting)
    peak_memory_growth_bytes: int = 0
    finish_reason: str = ""
    request_label: str = ""

    @property
    def throughput_tokens_per_second(self) -> float:
        if self.latency_ms <= 0 or not self.tokens.response_tokens:
            return 0.0
        return round(self.tokens.response_tokens / (self.latency_ms / 1000.0), 2)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["tokens"] = self.tokens.to_dict()
        d["throughput_tokens_per_second"] = self.throughput_tokens_per_second
        d["peak_memory_growth_mib"] = round(
            self.peak_memory_growth_bytes / (1024 ** 2), 2
        )
        d["memory_note"] = (
            "Growth in this process's peak RSS. The model runs in the provider "
            "daemon, so its resident size is reported by health(), not here."
        )
        return d


def estimate_tokens(text: str) -> int:
    """Characters divided by four. Labelled ``estimated`` wherever it is used."""
    return max(0, (len(text) + 3) // 4)


# --------------------------------------------------------------------------
# Interface
# --------------------------------------------------------------------------


class ReasoningAdapter(Protocol):
    """The provider-neutral surface. Nine capabilities, nothing more."""

    name: str
    model: str

    def health(self) -> dict[str, Any]: ...
    def load(self) -> dict[str, Any]: ...
    def generate(self, request: ModelRequest) -> ModelResponse: ...
    def cancel(self) -> None: ...
    def capabilities(self) -> dict[str, Any]: ...


def assert_loopback(endpoint: str) -> str:
    """Refuse any endpoint that is not local. Checked before a socket exists."""
    parsed = urllib.parse.urlparse(endpoint)
    if parsed.scheme not in ("http", "https"):
        raise ModelAdapterError("endpoint_scheme_not_allowed", parsed.scheme or endpoint)
    host = (parsed.hostname or "").lower()
    if host not in LOOPBACK_HOSTS:
        raise ModelAdapterError("endpoint_not_loopback", host or endpoint)
    return endpoint.rstrip("/")


def assert_no_forbidden_options(options: dict[str, Any]) -> None:
    offending = sorted(set(options) & FORBIDDEN_OPTION_KEYS)
    if offending:
        raise ModelAdapterError("forbidden_option", ",".join(offending))


# --------------------------------------------------------------------------
# Ollama
# --------------------------------------------------------------------------


class OllamaAdapter:
    """One local Ollama model. No key, no cloud, no fallback.

    The adapter holds a cancel flag rather than a thread pool: a call is
    synchronous, and :meth:`cancel` stops the *next* attempt and any pending
    retry. Interrupting a request already in flight is the provider's business,
    and claiming otherwise would overstate the control.
    """

    name = "ollama"

    def __init__(
        self,
        model: str,
        *,
        endpoint: str = DEFAULT_ENDPOINT,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        opener: Any = None,
    ):
        if not model.strip():
            raise ModelAdapterError("missing_model")
        self.model = model
        self.endpoint = assert_loopback(endpoint)
        self.max_attempts = max(1, int(max_attempts))
        self._cancelled = threading.Event()
        #: Injected in tests so the suite never needs a running daemon.
        self._opener = opener or self._urlopen

    # ---- transport ----------------------------------------------------------

    def _urlopen(self, url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=body,
            method="POST",
            # Content-Type only. No Authorization header is ever constructed,
            # so no credential can leave this process through this path.
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def _get(self, path: str, timeout: float = 5.0) -> dict[str, Any]:
        request = urllib.request.Request(f"{self.endpoint}{path}", method="GET")
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    # ---- capabilities -------------------------------------------------------

    def capabilities(self) -> dict[str, Any]:
        return {
            "adapter": self.name,
            "adapter_version": ADAPTER_VERSION,
            "model": self.model,
            "endpoint": self.endpoint,
            "supports": sorted([
                "load", "health_check", "send_prompt", "receive_response",
                "record_metadata", "timeout", "cancel", "retry",
                "resource_measurement",
            ]),
            "denies": sorted([
                "shell_access", "filesystem_writes", "tool_invocation",
                "non_loopback_network", "credentials", "provider_fallback",
                "paid_api_calls",
            ]),
            "max_attempts": self.max_attempts,
            "deterministic_defaults": {
                "temperature": DEFAULT_TEMPERATURE,
                "seed": DEFAULT_SEED,
            },
            "limitation": (
                "Determinism is requested, not guaranteed: temperature 0 and a "
                "fixed seed make runs comparable, but the provider may still "
                "vary output across versions, quantisations or hardware."
            ),
        }

    def health(self) -> dict[str, Any]:
        """Is the daemon up, and is this model present and resident?"""
        started = time.perf_counter()
        try:
            tags = self._get("/api/tags")
        except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
            return {
                "healthy": False,
                "endpoint": self.endpoint,
                "model": self.model,
                "error_code": "provider_unreachable",
                "error_detail": str(exc)[:200],
                "latency_ms": round((time.perf_counter() - started) * 1000, 3),
            }
        available = sorted(
            str(entry.get("name", "")) for entry in (tags.get("models") or [])
        )
        resident: list[dict[str, Any]] = []
        try:
            running = self._get("/api/ps")
            resident = [
                {
                    "model": entry.get("name"),
                    "size_bytes": entry.get("size"),
                    "size_gib": round((entry.get("size") or 0) / (1024 ** 3), 2),
                }
                for entry in (running.get("models") or [])
            ]
        except (urllib.error.URLError, OSError, json.JSONDecodeError):
            resident = []
        return {
            "healthy": self.model in available,
            "endpoint": self.endpoint,
            "model": self.model,
            "model_present": self.model in available,
            "available_models": available,
            "resident_models": resident,
            "resident_count": len(resident),
            "latency_ms": round((time.perf_counter() - started) * 1000, 3),
            "error_code": "" if self.model in available else "model_not_installed",
        }

    def load(self) -> dict[str, Any]:
        """Ask the provider to make the model resident, and time it.

        An empty prompt is Ollama's documented way to load without generating.
        """
        with measure(f"load:{self.model}") as m:
            try:
                self._opener(
                    f"{self.endpoint}/api/generate",
                    {"model": self.model, "prompt": "", "stream": False},
                    30.0,
                )
                ok, error = True, ""
            except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
                ok, error = False, str(exc)[:200]
        return {
            "loaded": ok,
            "model": self.model,
            "duration_ms": m.duration_ms,
            "error_detail": error,
            "resident_after": self.health().get("resident_models", []) if ok else [],
        }

    # ---- generation ---------------------------------------------------------

    def cancel(self) -> None:
        """Stop the next attempt and any pending retry."""
        self._cancelled.set()

    def reset_cancel(self) -> None:
        self._cancelled.clear()

    def generate(self, request: ModelRequest) -> ModelResponse:
        options: dict[str, Any] = {
            "temperature": request.temperature,
            "seed": request.seed,
            "num_predict": request.max_tokens,
        }
        if request.stop:
            options["stop"] = list(request.stop)
        assert_no_forbidden_options(options)

        payload: dict[str, Any] = {
            "model": self.model,
            "prompt": request.prompt,
            "stream": False,
            # Reasoning traces are not requested: this layer evaluates the
            # answer it is given, and a hidden trace is neither.
            "think": False,
            "options": options,
        }
        if request.system:
            payload["system"] = request.system
        if request.json_mode:
            payload["format"] = "json"

        response = ModelResponse(
            ok=False, model=self.model, adapter=self.name,
            request_label=request.label,
        )
        last_error: tuple[str, str] = ("", "")

        with measure(f"generate:{request.label or self.model}") as m:
            for attempt in range(1, self.max_attempts + 1):
                if self._cancelled.is_set():
                    response.cancelled = True
                    last_error = ("cancelled", "cancelled before attempt")
                    break
                response.attempts = attempt
                try:
                    raw = self._opener(
                        f"{self.endpoint}/api/generate", payload, request.timeout_s
                    )
                except TimeoutError as exc:
                    last_error = ("timeout", str(exc)[:200])
                    continue
                except (urllib.error.URLError, OSError) as exc:
                    reason = getattr(exc, "reason", exc)
                    code = "timeout" if isinstance(reason, TimeoutError) else "provider_unreachable"
                    last_error = (code, str(exc)[:200])
                    continue
                except json.JSONDecodeError as exc:
                    last_error = ("provider_response_not_json", str(exc)[:200])
                    continue

                text = str(raw.get("response", ""))
                response.ok = True
                response.text = text
                response.finish_reason = str(raw.get("done_reason", "") or "")
                prompt_tokens = raw.get("prompt_eval_count")
                eval_tokens = raw.get("eval_count")
                if isinstance(prompt_tokens, int) and isinstance(eval_tokens, int):
                    response.tokens = TokenAccounting(
                        prompt_tokens=prompt_tokens,
                        response_tokens=eval_tokens,
                        source="measured",
                    )
                else:
                    response.tokens = TokenAccounting(
                        prompt_tokens=estimate_tokens(request.prompt + request.system),
                        response_tokens=estimate_tokens(text),
                        source="estimated",
                    )
                break

        response.latency_ms = m.duration_ms
        response.peak_memory_growth_bytes = m.peak_memory_growth_bytes
        if not response.ok:
            response.error_code = last_error[0] or "no_attempt_made"
            response.error_detail = last_error[1]
        return response


# --------------------------------------------------------------------------
# Offline adapter, for tests and for a host with no provider
# --------------------------------------------------------------------------


class ScriptedAdapter:
    """A deterministic stand-in. Returns canned text; contacts nothing.

    This exists so the suite can exercise every adapter path — timeout, retry,
    cancel, malformed output — on a machine with no daemon running. It is never
    a fallback for :class:`OllamaAdapter`: a caller chooses one explicitly, and
    a response records which adapter produced it.
    """

    name = "scripted"

    def __init__(self, model: str = "scripted-v1", responses: list[str] | None = None):
        self.model = model
        self.responses = list(responses or [])
        self.calls: list[ModelRequest] = []
        self._cancelled = threading.Event()

    def capabilities(self) -> dict[str, Any]:
        return {
            "adapter": self.name,
            "adapter_version": ADAPTER_VERSION,
            "model": self.model,
            "endpoint": "none",
            "supports": ["send_prompt", "receive_response", "record_metadata", "cancel"],
            "denies": sorted([
                "shell_access", "filesystem_writes", "tool_invocation",
                "non_loopback_network", "credentials", "provider_fallback",
            ]),
            "limitation": "Canned text. Establishes nothing about any model.",
        }

    def health(self) -> dict[str, Any]:
        return {"healthy": True, "model": self.model, "endpoint": "none", "error_code": ""}

    def load(self) -> dict[str, Any]:
        return {"loaded": True, "model": self.model, "duration_ms": 0.0}

    def cancel(self) -> None:
        self._cancelled.set()

    def reset_cancel(self) -> None:
        self._cancelled.clear()

    def generate(self, request: ModelRequest) -> ModelResponse:
        self.calls.append(request)
        with measure("scripted") as m:
            if self._cancelled.is_set():
                return ModelResponse(
                    ok=False, model=self.model, adapter=self.name, cancelled=True,
                    error_code="cancelled", attempts=0, request_label=request.label,
                )
            text = self.responses.pop(0) if self.responses else ""
        return ModelResponse(
            ok=True, model=self.model, adapter=self.name, text=text, attempts=1,
            latency_ms=m.duration_ms,
            peak_memory_growth_bytes=m.peak_memory_growth_bytes,
            tokens=TokenAccounting(
                prompt_tokens=estimate_tokens(request.prompt),
                response_tokens=estimate_tokens(text),
                source="estimated",
            ),
            finish_reason="stop",
            request_label=request.label,
        )


# --------------------------------------------------------------------------
# Verification
# --------------------------------------------------------------------------

#: The model M356 evaluates. Chosen for the 8 GB host: 2.5 GB on disk, ~3.2 GB
#: resident, and it honours ``format: json`` with ``think: false``.
DEFAULT_MODEL = "qwen3:4b"

VERIFICATION_PROMPTS: tuple[tuple[str, ModelRequest], ...] = (
    (
        "single_word",
        ModelRequest(prompt="Reply with exactly one word: ready", max_tokens=8,
                     label="single_word"),
    ),
    (
        "json_object",
        ModelRequest(
            prompt='Return a JSON object with keys "status" and "reason".',
            max_tokens=96, json_mode=True, label="json_object",
        ),
    ),
    (
        "refusal_of_unknown",
        ModelRequest(
            prompt=(
                "You have been given no evidence. Answer only from what you "
                "were given. What is the SHA of the current commit?"
            ),
            max_tokens=96, label="refusal_of_unknown",
        ),
    ),
)


def verify_adapter(
    adapter: ReasoningAdapter | None = None, *, model: str = DEFAULT_MODEL
) -> dict[str, Any]:
    """Health, load, three calls, and the measured cost of each.

    Returns a report whether or not the provider is reachable; an unreachable
    provider is a result, not an exception.
    """
    adapter = adapter or OllamaAdapter(model)
    host_before: HostSnapshot = host_snapshot()
    health = adapter.health()
    report: dict[str, Any] = {
        "report": "agentdev.adapter_verification.v1",
        "adapter": adapter.name,
        "model": adapter.model,
        "capabilities": adapter.capabilities(),
        "health": health,
        "host_before": host_before.to_dict(),
    }
    if not health.get("healthy"):
        report["verified"] = False
        report["reason"] = health.get("error_code") or "unhealthy"
        report["calls"] = []
        return report

    report["load"] = adapter.load()
    calls: list[dict[str, Any]] = []
    for label, request in VERIFICATION_PROMPTS:
        response = adapter.generate(request)
        row = response.to_dict()
        row["label"] = label
        row["request"] = request.to_dict()
        if label == "json_object" and response.ok:
            try:
                json.loads(response.text)
                row["json_parsed"] = True
            except json.JSONDecodeError:
                row["json_parsed"] = False
        calls.append(row)
    report["calls"] = calls
    report["host_after"] = host_snapshot().to_dict()
    report["verified"] = all(c["ok"] for c in calls)
    latencies = [c["latency_ms"] for c in calls if c["ok"]]
    report["latency_ms"] = {
        "min": round(min(latencies), 1) if latencies else 0.0,
        "max": round(max(latencies), 1) if latencies else 0.0,
        "mean": round(sum(latencies) / len(latencies), 1) if latencies else 0.0,
    }
    report["throughput_tokens_per_second"] = [
        c["throughput_tokens_per_second"] for c in calls if c["ok"]
    ]
    report["limitation"] = (
        "Three calls on one host at one moment. Establishes that the adapter "
        "path works and what it cost here — not what any model will do."
    )
    return report
