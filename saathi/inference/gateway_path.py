"""M20.2 — Governed local inference execution path.

Flow:
  request → feature gates → validation → ModelRouter (authoritative)
  → catalogue + hardware + engine health → saathi.inference engine
  → structured result + evidence events

Does not replace ModelRouter. Does not start OpenJarvis. Default-off.
"""
from __future__ import annotations

import hashlib
import logging
import threading
import time
from typing import Any, Callable, Optional
from urllib.parse import urlparse

from saathi.inference.adapters.ollama import OllamaEngine
from saathi.inference.catalogue import ModelCatalogue, get_default_catalogue
from saathi.inference.config import InferenceSettings, load_inference_settings
from saathi.inference.engine import InferenceEngine
from saathi.inference.errors import EngineTimeoutError, EngineUnhealthyError
from saathi.inference.hardware import HardwareProfile, m2_8gb_reference_profile, profile_local_hardware
from saathi.inference.request import (
    InferenceErrorCategory,
    InferenceRequest,
    Sensitivity,
    validate_inference_request,
)
from saathi.inference.result import StructuredInferenceResult
from saathi.inference.router_bridge import (
    RouteRequest,
    engine_ids_for_providers,
    make_availability_checker,
    route_with_governance,
)
from saathi.model_router import ModelLabel, ModelRouter, Prefer, Privacy, ProviderSpec

logger = logging.getLogger(__name__)

# Process-local concurrency + idempotency (pilot scope; not a second scheduler)
_CONCURRENCY = threading.BoundedSemaphore(1)
_CONCURRENCY_LIMIT = 1
_ACTIVE = 0
_ACTIVE_LOCK = threading.Lock()
_IDEM: dict[str, StructuredInferenceResult] = {}
_IDEM_LOCK = threading.Lock()
_IDEM_MAX = 64

EventSink = Callable[[str, dict[str, Any]], None]


def _default_event(name: str, payload: dict[str, Any]) -> None:
    try:
        from saathi.events import bus

        bus.publish_sync(name, payload)
    except Exception:
        logger.debug("event %s: %s", name, {k: payload.get(k) for k in list(payload)[:8]})


def _emit(sink: Optional[EventSink], name: str, payload: dict[str, Any]) -> None:
    (sink or _default_event)(name, payload)


def _configure_concurrency(limit: int) -> None:
    global _CONCURRENCY, _CONCURRENCY_LIMIT
    limit = max(1, min(int(limit), 2))
    if limit != _CONCURRENCY_LIMIT:
        _CONCURRENCY = threading.BoundedSemaphore(limit)
        _CONCURRENCY_LIMIT = limit


def _validate_ollama_url(url: str, allowed_hosts: tuple[str, ...]) -> Optional[str]:
    try:
        parsed = urlparse(url)
    except Exception:
        return "invalid ollama URL"
    if parsed.scheme not in {"http", "https"}:
        return "ollama URL scheme must be http(s)"
    host = (parsed.hostname or "").lower()
    if host not in {h.lower() for h in allowed_hosts}:
        return f"ollama host not allowlisted: {host}"
    return None


def _catalogue_records_for_provider(catalogue: ModelCatalogue, provider_name: str) -> list:
    return [r for r in catalogue.list_records() if r.router_provider_name == provider_name]


def _pick_local_model_id(
    provider: ProviderSpec,
    catalogue: ModelCatalogue,
    hardware: HardwareProfile,
    *,
    model_hint: str = "",
    installed: Optional[list[str]] = None,
) -> tuple[Optional[str], list[str]]:
    """Choose a catalogue model id for the router-selected provider. No silent cloud sub."""
    warnings: list[str] = []
    recs = _catalogue_records_for_provider(catalogue, provider.name)
    local_recs = [r for r in recs if r.local_or_cloud == "local"]
    if not local_recs and provider.is_local:
        if model_hint:
            return model_hint, warnings
        if installed:
            return installed[0], warnings + ["catalogue sparse; using first installed model"]
        return "qwen2.5:3b", warnings + ["catalogue sparse; using default small local model"]

    candidates = local_recs or recs
    fit_ok = []
    for r in candidates:
        if r.parameter_count is None:
            fit_ok.append(r)
            continue
        fit = hardware.estimate_model_fit(
            model_id=r.model_id,
            parameter_count_b=r.parameter_count,
            memory_estimate_gb=r.memory_estimate,
            disk_estimate_gb=r.disk_estimate,
            quantization=r.quantization,
        )
        if fit.fits_memory and r.parameter_count <= hardware.recommended_max_model_size_b:
            fit_ok.append(r)
        else:
            warnings.append(f"skip {r.model_id}: hardware unfit")
    if not fit_ok:
        return None, warnings + ["no hardware-suitable model in catalogue for provider"]

    def _installed_match(model_id: str) -> bool:
        if not installed:
            return True  # unknown install set — defer
        return model_id in installed or any(model_id in m or m in model_id for m in installed)

    # Prefer installed + smaller
    fit_ok.sort(
        key=lambda r: (
            0 if _installed_match(r.model_id) else 1,
            r.parameter_count is None,
            r.parameter_count or 99,
        )
    )
    if model_hint:
        for r in fit_ok:
            if (r.model_id == model_hint or model_hint in r.model_id) and _installed_match(r.model_id):
                return r.model_id, warnings
        warnings.append(f"model_hint {model_hint!r} not used (unfit, unregistered, or not installed)")
    # Prefer an installed model when list is known
    for r in fit_ok:
        if _installed_match(r.model_id):
            return r.model_id, warnings
    return None, warnings + ["no hardware-suitable installed model (no auto-download)"]


class GovernedLocalInferencePath:
    """Single bounded entry for local LLM via ModelRouter + saathi.inference."""

    OPERATION = "local-llm-inference"

    def __init__(
        self,
        *,
        settings: Optional[InferenceSettings] = None,
        router: Optional[ModelRouter] = None,
        catalogue: Optional[ModelCatalogue] = None,
        hardware: Optional[HardwareProfile] = None,
        engine: Optional[InferenceEngine] = None,
        event_sink: Optional[EventSink] = None,
        is_available: Optional[Callable[[str], bool]] = None,
    ):
        self.settings = settings or load_inference_settings()
        self.catalogue = catalogue or get_default_catalogue()
        self.hardware = hardware
        self._engine = engine
        self.event_sink = event_sink
        self._is_available = is_available
        if router is not None:
            self.router = router
        else:
            avail = is_available or (lambda _n: True)
            self.router = ModelRouter(is_available=make_availability_checker(avail))

    def _hw(self) -> HardwareProfile:
        if self.hardware is not None:
            return self.hardware
        if self.settings.auto_detect_hardware:
            return profile_local_hardware(
                memory_safety_margin_gb=self.settings.memory_safety_margin_gb,
                disk_warning_gb=self.settings.disk_warning_gb,
            )
        return m2_8gb_reference_profile()

    def _engine_instance(self) -> InferenceEngine:
        if self._engine is not None:
            return self._engine
        err = _validate_ollama_url(
            self.settings.ollama_base_url, self.settings.allowed_ollama_hosts
        )
        if err:
            raise PermissionError(err)
        if "ollama" not in self.settings.local_engine_allowlist:
            raise PermissionError("ollama not in local engine allowlist")
        return OllamaEngine(host=self.settings.ollama_base_url)

    async def execute(self, req: InferenceRequest) -> StructuredInferenceResult:
        t0 = time.monotonic()
        settings = self.settings
        _configure_concurrency(settings.max_concurrent_local)
        fp = req.prompt_fingerprint()
        _emit(
            self.event_sink,
            "inference.request_received",
            {
                "request_id": req.request_id,
                "caller": req.caller_component,
                "prompt_fingerprint": fp,
                "local_only": req.local_only,
                "sensitivity": req.sensitivity.value,
            },
        )

        # Feature gates
        if not settings.enabled:
            return self._fail(
                req, InferenceErrorCategory.INFERENCE_DISABLED, "SAATHI_INFERENCE_ENABLED is false", fp, t0
            )
        if not settings.gateway_enabled:
            return self._fail(
                req,
                InferenceErrorCategory.GATEWAY_DISABLED,
                "SAATHI_INFERENCE_GATEWAY_ENABLED is false",
                fp,
                t0,
            )

        # Idempotency
        if req.idempotency_key:
            with _IDEM_LOCK:
                if req.idempotency_key in _IDEM:
                    cached = _IDEM[req.idempotency_key]
                    _emit(
                        self.event_sink,
                        "inference.idempotent_hit",
                        {"request_id": req.request_id, "key": req.idempotency_key[:16]},
                    )
                    return cached

        # Validation
        v_errors = validate_inference_request(req, settings)
        if v_errors:
            cat = InferenceErrorCategory.INVALID_REQUEST
            if any("stream" in e for e in v_errors):
                cat = InferenceErrorCategory.STREAMING_UNSUPPORTED
            if any("tool" in e for e in v_errors):
                cat = InferenceErrorCategory.CAPABILITY_DENIED
            if any("override" in e or "bypass" in e or "URL" in e for e in v_errors):
                cat = InferenceErrorCategory.SECURITY_POLICY_DENIED
            if any("prompt exceeds" in e for e in v_errors):
                cat = InferenceErrorCategory.PROMPT_TOO_LARGE
            if any("max_output_tokens" in e for e in v_errors):
                cat = InferenceErrorCategory.OUTPUT_LIMIT_INVALID
            return self._fail(req, cat, "; ".join(v_errors), fp, t0)

        # Cloud fallback policy
        if req.cloud_fallback_permitted and not settings.allow_cloud_fallback:
            # request may continue local-only; if local fails, no cloud
            pass
        if (not req.local_only) and (not settings.allow_cloud_fallback):
            # still allow local execution; cloud denied later
            pass

        # Hardware pre-gate
        hw = self._hw()
        if hw.available_memory_gb < settings.min_available_memory_gb:
            return self._fail(
                req,
                InferenceErrorCategory.HARDWARE_POLICY_DENIED,
                f"available memory {hw.available_memory_gb} GB below minimum "
                f"{settings.min_available_memory_gb} GB",
                fp,
                t0,
                warnings=list(hw.warnings),
            )
        _emit(
            self.event_sink,
            "inference.hardware_ok",
            {
                "request_id": req.request_id,
                "available_memory_gb": hw.available_memory_gb,
                "recommended_max_model_size_b": hw.recommended_max_model_size_b,
            },
        )

        # ModelRouter — authoritative
        privacy = Privacy.LOCAL_ONLY if req.local_only else Privacy.CLOUD_OK
        if req.sensitivity in {Sensitivity.CONFIDENTIAL, Sensitivity.SENSITIVE}:
            privacy = Privacy.LOCAL_ONLY
        try:
            chain = route_with_governance(
                RouteRequest(
                    label=req.label(),
                    privacy=privacy,
                    prefer=req.prefer_enum(),
                    mission_local_only=req.local_only
                    or req.sensitivity in {Sensitivity.CONFIDENTIAL, Sensitivity.SENSITIVE},
                ),
                router=self.router,
                catalogue=self.catalogue,
                settings=settings,
                hardware=hw,
            )
        except Exception as e:
            return self._fail(
                req, InferenceErrorCategory.ROUTER_FAILED, f"router error: {e}", fp, t0
            )

        if not chain:
            return self._fail(
                req,
                InferenceErrorCategory.NO_SUITABLE_MODEL,
                "ModelRouter returned empty chain",
                fp,
                t0,
            )

        chain_names = [p.name for p in chain]
        _emit(
            self.event_sink,
            "inference.router_decision",
            {"request_id": req.request_id, "chain": chain_names, "selected": chain_names[0]},
        )

        # Local-only: strip cloud providers; do not invent alternatives
        if privacy is Privacy.LOCAL_ONLY:
            chain = [p for p in chain if p.is_local]
            if not chain:
                return self._fail(
                    req,
                    InferenceErrorCategory.CLOUD_FALLBACK_DENIED,
                    "no local provider in router chain; cloud fallback denied",
                    fp,
                    t0,
                    router_chain=chain_names,
                )

        selected = chain[0]
        # Reject cloud if fallback not permitted by config/request
        # ProviderSpec uses is_local (no is_cloud attribute).
        if not selected.is_local:
            if not settings.allow_cloud_fallback or not req.cloud_fallback_permitted:
                return self._fail(
                    req,
                    InferenceErrorCategory.CLOUD_FALLBACK_DENIED,
                    "cloud provider selected but fallback/cloud disabled",
                    fp,
                    t0,
                    router_chain=chain_names,
                )
            return self._fail(
                req,
                InferenceErrorCategory.CLOUD_FALLBACK_DENIED,
                "M20.2 pilot executes local engines only",
                fp,
                t0,
                router_chain=chain_names,
            )

        # Engine resolution — ollama first for local
        engine_ids = engine_ids_for_providers([selected])
        engine_id = engine_ids[0] if engine_ids else "ollama"
        if engine_id not in settings.local_engine_allowlist:
            return self._fail(
                req,
                InferenceErrorCategory.SECURITY_POLICY_DENIED,
                f"engine {engine_id} not allowlisted",
                fp,
                t0,
                router_chain=chain_names,
            )
        if req.engine_hint and req.engine_hint != engine_id:
            return self._fail(
                req,
                InferenceErrorCategory.SECURITY_POLICY_DENIED,
                "engine_hint cannot override router-selected engine",
                fp,
                t0,
                router_chain=chain_names,
            )

        # Concurrency
        acquired = _CONCURRENCY.acquire(blocking=False)
        if not acquired:
            return self._fail(
                req,
                InferenceErrorCategory.CONCURRENCY_LIMIT,
                f"max concurrent local inference is {_CONCURRENCY_LIMIT}",
                fp,
                t0,
                router_chain=chain_names,
            )
        global _ACTIVE
        with _ACTIVE_LOCK:
            _ACTIVE += 1
        model_warnings: list[str] = []
        try:
            try:
                engine = self._engine_instance()
            except PermissionError as e:
                return self._fail(
                    req,
                    InferenceErrorCategory.SECURITY_POLICY_DENIED,
                    str(e),
                    fp,
                    t0,
                    router_chain=chain_names,
                )

            health = await engine.health()
            health_ok = bool(health.get("ok")) if isinstance(health, dict) else bool(health)
            _emit(
                self.event_sink,
                "inference.engine_health",
                {"request_id": req.request_id, "ok": health_ok, "engine": engine.engine_id},
            )
            if not health_ok:
                return self._fail(
                    req,
                    InferenceErrorCategory.ENGINE_UNAVAILABLE,
                    "local engine unhealthy",
                    fp,
                    t0,
                    router_chain=chain_names,
                )

            try:
                available = list(await engine.list_models())
            except Exception:
                available = []

            model_id, model_warnings = _pick_local_model_id(
                selected,
                self.catalogue,
                hw,
                model_hint=req.model_hint,
                installed=available or None,
            )
            if not model_id:
                cat = (
                    InferenceErrorCategory.MODEL_UNAVAILABLE
                    if available
                    else InferenceErrorCategory.HARDWARE_POLICY_DENIED
                )
                return self._fail(
                    req,
                    cat,
                    "no suitable installed local model (no auto-download)",
                    fp,
                    t0,
                    warnings=model_warnings,
                    router_chain=chain_names,
                )

            _emit(
                self.event_sink,
                "inference.execution_started",
                {
                    "request_id": req.request_id,
                    "provider": selected.name,
                    "model": model_id,
                    "engine": engine.engine_id,
                },
            )
            messages = req.build_messages()
            try:
                gen = await engine.generate(
                    messages,
                    model=model_id,
                    temperature=req.temperature,
                    max_tokens=min(req.max_output_tokens, settings.max_output_tokens),
                    timeout=min(req.timeout_seconds, settings.request_timeout_seconds),
                )
            except EngineTimeoutError as e:
                return self._fail(
                    req,
                    InferenceErrorCategory.TIMEOUT,
                    str(e),
                    fp,
                    t0,
                    router_chain=chain_names,
                )
            except EngineUnhealthyError as e:
                return self._fail(
                    req,
                    InferenceErrorCategory.PROVIDER_UNAVAILABLE,
                    str(e),
                    fp,
                    t0,
                    router_chain=chain_names,
                )
            except Exception as e:
                return self._fail(
                    req,
                    InferenceErrorCategory.INTERNAL,
                    str(e),
                    fp,
                    t0,
                    router_chain=chain_names,
                )

            latency = (time.monotonic() - t0) * 1000
            usage = gen.usage or {}
            in_tok = usage.get("prompt_tokens")
            out_tok = usage.get("completion_tokens") or usage.get("output_tokens")
            total = None
            if in_tok is not None or out_tok is not None:
                total = int(in_tok or 0) + int(out_tok or 0)
            result = StructuredInferenceResult(
                request_id=req.request_id,
                mission_id=req.mission_id,
                run_id=req.run_id,
                ok=True,
                selected_model=gen.model or model_id,
                selected_provider=selected.name,
                selected_engine=engine.engine_id,
                output_text=gen.text or "",
                finish_reason=gen.finish_reason or "stop",
                input_tokens=int(in_tok) if in_tok is not None else None,
                output_tokens=int(out_tok) if out_tok is not None else None,
                total_tokens=total,
                latency_ms=latency if not gen.latency_ms else gen.latency_ms,
                engine_health="ok",
                classification="local",
                fallback_used=False,
                warnings=model_warnings,
                evidence_ref=f"inference:{req.request_id}",
                prompt_fingerprint=fp,
                energy_supported=False,
                energy_joules=None,
                router_chain=chain_names,
            )
            result.finalize_fingerprint()
            _emit(
                self.event_sink,
                "inference.execution_completed",
                {
                    "request_id": req.request_id,
                    "ok": True,
                    "model": result.selected_model,
                    "latency_ms": result.latency_ms,
                    "result_fingerprint": result.result_fingerprint,
                    "input_tokens": result.input_tokens,
                    "output_tokens": result.output_tokens,
                },
            )
            if req.idempotency_key:
                with _IDEM_LOCK:
                    if len(_IDEM) >= _IDEM_MAX:
                        _IDEM.clear()
                    _IDEM[req.idempotency_key] = result
            return result
        finally:
            with _ACTIVE_LOCK:
                _ACTIVE = max(0, _ACTIVE - 1)
            _CONCURRENCY.release()

    def _fail(
        self,
        req: InferenceRequest,
        category: InferenceErrorCategory,
        message: str,
        fp: str,
        t0: float,
        *,
        warnings: Optional[list[str]] = None,
        router_chain: Optional[list[str]] = None,
    ) -> StructuredInferenceResult:
        r = StructuredInferenceResult.failure(
            req.request_id,
            category,
            message,
            mission_id=req.mission_id,
            run_id=req.run_id,
            warnings=warnings,
            router_chain=router_chain,
            prompt_fingerprint=fp,
            latency_ms=(time.monotonic() - t0) * 1000,
        )
        _emit(
            self.event_sink,
            "inference.failed",
            {
                "request_id": req.request_id,
                "category": category.value,
                "message": r.error_message,
            },
        )
        return r


async def execute_governed_local_inference(
    req: InferenceRequest,
    **kwargs: Any,
) -> StructuredInferenceResult:
    """Module-level entry for tests and adapters."""
    path = GovernedLocalInferencePath(**kwargs)
    return await path.execute(req)


def reset_gateway_path_state() -> None:
    """Test helper: clear idempotency cache."""
    with _IDEM_LOCK:
        _IDEM.clear()
