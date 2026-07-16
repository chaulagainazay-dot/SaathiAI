"""M20.3 — Bounded live small-model validation harness.

Never downloads models. Never claims live success when only mocks ran.
Safe when Ollama is missing: returns structured unavailable result.
"""
from __future__ import annotations

import shutil
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Optional
from urllib.parse import urlparse

from saathi.inference.config import InferenceSettings, load_inference_settings
from saathi.inference.hardware import profile_local_hardware


@dataclass
class LiveValidationReport:
    live: bool
    label: str  # "live" | "mock" | "unavailable"
    ollama_installed: bool = False
    ollama_reachable: bool = False
    endpoint_local: bool = False
    models_installed: list[str] = field(default_factory=list)
    selected_model: str = ""
    model_suitable: bool = False
    memory_before_gb: float = 0.0
    memory_after_gb: float = 0.0
    latency_ms: float = 0.0
    response_length: int = 0
    finish_reason: str = ""
    token_usage: dict[str, Any] = field(default_factory=dict)
    ok: bool = False
    error: str = ""
    notes: list[str] = field(default_factory=list)
    prompt_non_sensitive: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# Preferred small models for M2 8GB (no auto-download)
_PREFERRED_SMALL = (
    "qwen2.5:0.5b",
    "qwen2.5:1.5b",
    "qwen2.5:3b",
    "llama3.2:1b",
    "llama3.2:3b",
    "gemma2:2b",
    "phi3:mini",
    "tinyllama",
)


def _host_is_local(url: str, allowed: tuple[str, ...]) -> bool:
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return False
    return host in {h.lower() for h in allowed}


def _pick_small_model(installed: list[str]) -> tuple[str, bool]:
    lower = {m.lower(): m for m in installed}
    for pref in _PREFERRED_SMALL:
        if pref in lower:
            return lower[pref], True
        # prefix match e.g. qwen2.5:3b-instruct
        for k, orig in lower.items():
            if k.startswith(pref.split(":")[0]) and any(
                x in k for x in ("0.5b", "1b", "1.5b", "2b", "3b", "mini", "tiny")
            ):
                # reject obvious large models
                if any(x in k for x in ("7b", "8b", "13b", "70b", "72b")):
                    continue
                return orig, True
    # any installed that doesn't look huge
    for m in installed:
        ml = m.lower()
        if any(x in ml for x in ("7b", "8b", "13b", "14b", "32b", "70b", "72b")):
            continue
        return m, True
    return "", False


def run_live_small_model_validation(
    *,
    settings: Optional[InferenceSettings] = None,
    force_mock: bool = False,
    engine=None,
) -> LiveValidationReport:
    """Run at most one/two bounded non-sensitive prompts against local Ollama.

    If Ollama is not installed or no small model is present, returns
    ``live=False, label=unavailable`` without downloading anything.
    """
    settings = settings or load_inference_settings()
    notes: list[str] = []
    hw = profile_local_hardware()
    mem_before = float(hw.available_memory_gb or 0.0)

    if force_mock:
        return LiveValidationReport(
            live=False,
            label="mock",
            memory_before_gb=mem_before,
            memory_after_gb=mem_before,
            ok=True,
            notes=["force_mock: no live network"],
            selected_model="fake:qwen2.5:3b",
            model_suitable=True,
            response_length=11,
            finish_reason="stop",
            latency_ms=1.0,
        )

    ollama_bin = shutil.which("ollama") is not None
    endpoint = settings.ollama_base_url
    local = _host_is_local(endpoint, settings.allowed_ollama_hosts)
    if not local:
        return LiveValidationReport(
            live=False,
            label="unavailable",
            ollama_installed=ollama_bin,
            endpoint_local=False,
            memory_before_gb=mem_before,
            memory_after_gb=mem_before,
            error="endpoint_not_local",
            notes=["refusing non-local Ollama host"],
        )

    # List models — no pull
    models: list[str] = []
    reachable = False
    try:
        from saathi.inference.adapters.ollama import OllamaEngine
        eng = engine or OllamaEngine(host=endpoint)
        # health
        import asyncio

        async def _health():
            return await eng.health()

        try:
            h = asyncio.run(_health())
        except RuntimeError:
            loop = asyncio.new_event_loop()
            try:
                h = loop.run_until_complete(_health())
            finally:
                loop.close()
        reachable = bool(getattr(h, "ok", False) or (isinstance(h, dict) and h.get("ok")))
        if not reachable and hasattr(h, "status"):
            reachable = str(getattr(h, "status", "")).lower() in {"ok", "healthy", "up"}

        async def _list():
            return await eng.list_models()

        try:
            listed = asyncio.run(_list())
        except RuntimeError:
            loop = asyncio.new_event_loop()
            try:
                listed = loop.run_until_complete(_list())
            finally:
                loop.close()
        if isinstance(listed, list):
            for m in listed:
                if isinstance(m, str):
                    models.append(m)
                elif isinstance(m, dict) and m.get("name"):
                    models.append(str(m["name"]))
                elif hasattr(m, "id"):
                    models.append(str(m.id))
                elif hasattr(m, "name"):
                    models.append(str(m.name))
    except Exception as e:
        notes.append(f"list_failed:{type(e).__name__}")
        return LiveValidationReport(
            live=False,
            label="unavailable",
            ollama_installed=ollama_bin,
            ollama_reachable=False,
            endpoint_local=local,
            models_installed=models,
            memory_before_gb=mem_before,
            memory_after_gb=mem_before,
            error="ollama_unavailable",
            notes=notes + ["no model download attempted"],
        )

    if not models:
        return LiveValidationReport(
            live=False,
            label="unavailable",
            ollama_installed=ollama_bin,
            ollama_reachable=reachable,
            endpoint_local=local,
            models_installed=[],
            memory_before_gb=mem_before,
            memory_after_gb=mem_before,
            error="no_installed_models",
            notes=["no model download attempted"],
        )

    selected, suitable = _pick_small_model(models)
    if not selected or not suitable:
        return LiveValidationReport(
            live=False,
            label="unavailable",
            ollama_installed=ollama_bin,
            ollama_reachable=reachable,
            endpoint_local=local,
            models_installed=models,
            memory_before_gb=mem_before,
            memory_after_gb=mem_before,
            error="no_suitable_small_model",
            notes=["refusing automatic large-model use; no download"],
        )

    if mem_before < settings.min_available_memory_gb:
        return LiveValidationReport(
            live=False,
            label="unavailable",
            ollama_installed=ollama_bin,
            ollama_reachable=reachable,
            endpoint_local=local,
            models_installed=models,
            selected_model=selected,
            model_suitable=True,
            memory_before_gb=mem_before,
            memory_after_gb=mem_before,
            error="insufficient_memory",
            notes=["memory headroom too low for live generation"],
        )

    # One non-sensitive bounded prompt
    prompt = "Reply with exactly: ok"
    system = "You are a test harness. Be brief."
    t0 = time.monotonic()
    try:
        from saathi.inference.adapters.ollama import OllamaEngine
        eng = engine or OllamaEngine(host=endpoint)
        import asyncio

        async def _gen():
            return await eng.generate(
                [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
                model=selected,
                max_tokens=16,
                timeout=min(30.0, settings.request_timeout_seconds),
            )

        try:
            gen = asyncio.run(_gen())
        except RuntimeError:
            loop = asyncio.new_event_loop()
            try:
                gen = loop.run_until_complete(_gen())
            finally:
                loop.close()
        latency = (time.monotonic() - t0) * 1000
        text = getattr(gen, "text", None) or (gen.get("text") if isinstance(gen, dict) else "") or ""
        usage = getattr(gen, "usage", None) or {}
        finish = getattr(gen, "finish_reason", None) or "stop"
        hw2 = profile_local_hardware()
        return LiveValidationReport(
            live=True,
            label="live",
            ollama_installed=ollama_bin,
            ollama_reachable=True,
            endpoint_local=local,
            models_installed=models,
            selected_model=selected,
            model_suitable=True,
            memory_before_gb=mem_before,
            memory_after_gb=float(hw2.available_memory_gb or 0.0),
            latency_ms=latency,
            response_length=len(text),
            finish_reason=str(finish),
            token_usage=dict(usage) if isinstance(usage, dict) else {},
            ok=bool(str(text).strip()),
            notes=["single bounded non-sensitive prompt; no download"],
        )
    except Exception as e:
        hw2 = profile_local_hardware()
        return LiveValidationReport(
            live=False,
            label="unavailable",
            ollama_installed=ollama_bin,
            ollama_reachable=reachable,
            endpoint_local=local,
            models_installed=models,
            selected_model=selected,
            model_suitable=True,
            memory_before_gb=mem_before,
            memory_after_gb=float(hw2.available_memory_gb or 0.0),
            latency_ms=(time.monotonic() - t0) * 1000,
            error=type(e).__name__,
            notes=["generation failed; no download attempted"],
        )
