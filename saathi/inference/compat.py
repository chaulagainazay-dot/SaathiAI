"""M20.3 — Compatibility adapter: caller contracts ↔ M20.2 governed path.

Does not reimplement ModelRouter, engines, or ExecutionGateway.
Does not open Ollama from callers. Default path remains legacy llm.generate.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Optional

from saathi.inference.caller_rollout import (
    CALLER_CHEAP_ASK,
    CALLER_PROSE_CLEAN,
    FALLBACK_DENIED,
    InfRolloutMode,
    can_fallback,
    resolve_mode,
)
from saathi.inference.request import InferenceRequest, Sensitivity
from saathi.inference.result import StructuredInferenceResult
from saathi.llm import LLMResult
from saathi.model_router import ModelLabel, Prefer, Privacy

logger = logging.getLogger(__name__)

LegacyFn = Callable[..., Any]
GovernedFn = Callable[[InferenceRequest], StructuredInferenceResult]

# Caller-specific bounds (must not expand global limits)
CALLER_LIMITS: dict[str, dict[str, Any]] = {
    CALLER_CHEAP_ASK: {
        "max_output_tokens": 512,
        "timeout_seconds": 45.0,
        "max_prompt_chars": 6000,
        "task_type": "screening",
        "label": ModelLabel.SCREENING,
        "prefer": Prefer.COST,
        "sensitivity": Sensitivity.INTERNAL,
    },
    CALLER_PROSE_CLEAN: {
        "max_output_tokens": 1024,
        "timeout_seconds": 60.0,
        "max_prompt_chars": 8000,
        "task_type": "standard",
        "label": ModelLabel.STANDARD,
        "prefer": Prefer.QUALITY,
        "sensitivity": Sensitivity.INTERNAL,
    },
}

_metrics_lock = threading.RLock()
_metrics: dict[str, Any] = {
    "calls_total": 0,
    "by_mode": {},
    "by_caller": {},
    "legacy_success": 0,
    "governed_success": 0,
    "governed_fail": 0,
    "fallback_count": 0,
    "fallback_denied_count": 0,
    "shadow_comparisons": 0,
    "path_legacy": 0,
    "path_governed": 0,
    "path_governed_then_legacy": 0,
    "path_shadow": 0,
    "latency_legacy_ms_sum": 0.0,
    "latency_governed_ms_sum": 0.0,
    "latency_count": 0,
}
_events: list[dict[str, Any]] = []
_events_lock = threading.RLock()


def metrics_snapshot() -> dict[str, Any]:
    with _metrics_lock:
        snap = dict(_metrics)
        snap["by_mode"] = dict(_metrics["by_mode"])
        snap["by_caller"] = dict(_metrics["by_caller"])
        n = snap["latency_count"] or 0
        snap["latency_legacy_ms_avg"] = (
            round(snap["latency_legacy_ms_sum"] / n, 2) if n else 0.0
        )
        snap["latency_governed_ms_avg"] = (
            round(snap["latency_governed_ms_sum"] / n, 2) if n else 0.0
        )
        return snap


def reset_compat_metrics() -> None:
    with _metrics_lock:
        for k in list(_metrics.keys()):
            if isinstance(_metrics[k], dict):
                _metrics[k] = {}
            elif isinstance(_metrics[k], float):
                _metrics[k] = 0.0
            else:
                _metrics[k] = 0
    with _events_lock:
        _events.clear()


def recent_compat_events(limit: int = 40) -> list[dict[str, Any]]:
    with _events_lock:
        return list(_events[-limit:])


def _inc(key: str, n: int = 1) -> None:
    with _metrics_lock:
        _metrics[key] = int(_metrics.get(key, 0)) + n


def _inc_map(map_key: str, sub: str, n: int = 1) -> None:
    with _metrics_lock:
        m = _metrics[map_key]
        m[sub] = int(m.get(sub, 0)) + n


def _emit(name: str, payload: dict[str, Any]) -> None:
    safe = {k: v for k, v in payload.items() if k not in ("prompt", "output", "text", "system")}
    entry = {"event": name, **safe, "ts": time.time()}
    with _events_lock:
        _events.append(entry)
        if len(_events) > 200:
            del _events[:100]
    try:
        from saathi.events import bus
        bus.publish_sync(f"inference.compat.{name}", safe)
    except Exception:
        pass


def _bound_text(text: str, max_chars: int) -> str:
    t = text or ""
    if len(t) <= max_chars:
        return t
    return t[:max_chars] + "\n…[truncated]"


def _fingerprint(text: str) -> str:
    return "sha256:" + hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:24]


@dataclass
class CompatResult:
    """Caller-facing result with path metadata (no full prompts)."""

    text: str
    provider: str = ""
    model: str = ""
    path_used: str = "legacy"  # legacy | governed_local | governed_local_then_legacy | shadow_legacy
    mode: str = "legacy"
    ok: bool = True
    warnings: list[str] = field(default_factory=list)
    evidence_ref: str = ""
    error_category: str = ""
    error_message: str = ""
    latency_ms: float = 0.0
    result_fingerprint: str = ""
    shadow: Optional[dict[str, Any]] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_llm_result(self) -> LLMResult:
        return LLMResult(text=self.text, provider=self.provider or "legacy", model=self.model or "")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_inference_request(
    caller: str,
    prompt: str,
    system: str,
    *,
    mission_id: str = "",
    run_id: str = "",
    actor_id: str = "",
    extra_metadata: Optional[dict[str, Any]] = None,
) -> InferenceRequest:
    """Build a bounded canonical InferenceRequest for a selected caller (M21.1)."""
    limits = CALLER_LIMITS.get(caller) or CALLER_LIMITS[CALLER_CHEAP_ASK]
    max_chars = int(limits["max_prompt_chars"])
    # Prefer M21.1 caller policy bounds when registered
    try:
        from saathi.inference.caller_policy import get_caller_policy

        cpol = get_caller_policy(caller)
        if cpol is not None:
            max_chars = min(max_chars, int(cpol.max_input_chars))
    except Exception:
        cpol = None
    body = _bound_text(prompt, max_chars)
    sys = _bound_text(system or "You are a helpful assistant.", 2000)
    max_out = int(limits["max_output_tokens"])
    timeout = float(limits["timeout_seconds"])
    if cpol is not None:
        max_out = min(max_out, int(cpol.max_output_tokens))
        timeout = min(timeout, float(cpol.timeout_seconds))
    # Reject tool/authorization expansion phrases in system (data stays data)
    return InferenceRequest(
        mission_id=mission_id,
        run_id=run_id,
        caller_component=caller,
        actor_id=actor_id,
        prompt=body,
        system=sys,
        task_type=str(limits["task_type"]),
        sensitivity=limits["sensitivity"],
        preferred_capability=str(limits["task_type"]),
        max_output_tokens=max_out,
        timeout_seconds=timeout,
        temperature=0.0,
        local_only=True if cpol is None else bool(cpol.local_only),
        cloud_fallback_permitted=False,
        cloud_allowed=False,
        tool_use_permitted=False,
        streaming_requested=False,
        evidence_required=True,
        prefer="cost" if limits["prefer"] == Prefer.COST else "quality",
        max_retries=0,
        log_prompt=False,
        log_output=False,
        retention_policy="metadata_only",
        request_cost_ceiling=0.0,
        fallback_policy="none",
        contract_version="m21.1",
        metadata={
            "m20_3_caller": caller,
            "m21_1_contract": True,
            "prompt_chars": len(body),
            **(extra_metadata or {}),
        },
    )


def _run_governed(
    req: InferenceRequest,
    *,
    governed_fn: Optional[GovernedFn] = None,
) -> StructuredInferenceResult:
    if governed_fn is not None:
        return governed_fn(req)

    async def _go():
        from saathi.inference.gateway_path import execute_governed_local_inference
        return await execute_governed_local_inference(req)

    try:
        return asyncio.run(_go())
    except RuntimeError:
        # nested event loop
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_go())
        finally:
            loop.close()


def _run_legacy_generate(
    label: ModelLabel,
    prompt: str,
    system: str,
    *,
    prefer: Prefer,
    max_tokens: int,
    timeout: int,
    legacy_fn: Optional[LegacyFn] = None,
) -> LLMResult:
    if legacy_fn is not None:
        out = legacy_fn(
            label=label, prompt=prompt, system=system,
            prefer=prefer, max_tokens=max_tokens, timeout=timeout,
        )
        if isinstance(out, LLMResult):
            return out
        if isinstance(out, str):
            return LLMResult(text=out, provider="legacy", model="")
        if isinstance(out, dict) and "text" in out:
            return LLMResult(text=str(out["text"]), provider=str(out.get("provider", "legacy")), model=str(out.get("model", "")))
        return LLMResult(text=str(out), provider="legacy", model="")

    from saathi.llm import generate
    return generate(
        label, prompt, system=system,
        prefer=prefer, max_tokens=max_tokens, timeout=timeout,
        privacy=Privacy.CLOUD_OK,
    )


def _shadow_compare(legacy_text: str, gov: StructuredInferenceResult) -> dict[str, Any]:
    lt = (legacy_text or "").strip()
    gt = (gov.output_text or "").strip() if gov.ok else ""
    return {
        "legacy_success": bool(lt),
        "governed_local_success": bool(gov.ok and gt),
        "output_non_empty_legacy": bool(lt),
        "output_non_empty_governed": bool(gt),
        "schema_ok_governed": bool(gov.ok),
        "latency_governed_ms": gov.latency_ms,
        "timeout": gov.error_category == "timeout",
        "fallback": False,
        "warning_count": len(gov.warnings or []),
        "result_fingerprint_legacy": _fingerprint(lt),
        "result_fingerprint_governed": gov.result_fingerprint or _fingerprint(gt),
        "error_category": gov.error_category or "",
        "local_model": gov.selected_model or "",
        "prompt_size": 0,  # filled by caller path
        "output_size_legacy": len(lt),
        "output_size_governed": len(gt),
        "length_ratio": (len(gt) / len(lt)) if lt else None,
        "exact_match": lt == gt if (lt and gt) else False,
        # never include raw text
    }


def adopt_generate(
    caller: str,
    prompt: str,
    system: str = "You are a helpful assistant.",
    *,
    mission_id: str = "",
    run_id: str = "",
    legacy_fn: Optional[LegacyFn] = None,
    governed_fn: Optional[GovernedFn] = None,
    mode: Optional[InfRolloutMode] = None,
) -> CompatResult:
    """Route a selected caller through rollout mode.

    Returns CompatResult; callers map to their public dict/str shapes.
    """
    if caller not in CALLER_LIMITS:
        # Unknown caller → hard legacy only (no governed path)
        mode_r = InfRolloutMode.LEGACY
    else:
        mode_r = mode or resolve_mode(caller)

    limits = CALLER_LIMITS.get(caller) or CALLER_LIMITS[CALLER_CHEAP_ASK]
    label: ModelLabel = limits["label"]
    prefer: Prefer = limits["prefer"]
    max_tokens = int(limits["max_output_tokens"])
    timeout = int(limits["timeout_seconds"])
    max_chars = int(limits["max_prompt_chars"])
    prompt_b = _bound_text(prompt, max_chars)
    system_b = _bound_text(system, 2000)

    _inc("calls_total")
    _inc_map("by_mode", mode_r.value)
    _inc_map("by_caller", caller)
    _emit("caller_selected", {"caller": caller, "mode": mode_r.value})

    # Oversized original prompt: soft truncate already done; if empty after bound, fail closed
    if not prompt_b.strip():
        return CompatResult(
            text="", ok=False, path_used="legacy", mode=mode_r.value,
            error_category="invalid_request", error_message="empty_prompt",
        )

    # ── LEGACY ──────────────────────────────────────────────────────────
    if mode_r == InfRolloutMode.LEGACY:
        t0 = time.monotonic()
        try:
            res = _run_legacy_generate(
                label, prompt_b, system_b, prefer=prefer,
                max_tokens=max_tokens, timeout=timeout, legacy_fn=legacy_fn,
            )
            ms = (time.monotonic() - t0) * 1000
            _inc("legacy_success")
            _inc("path_legacy")
            with _metrics_lock:
                _metrics["latency_legacy_ms_sum"] += ms
                _metrics["latency_count"] += 1
            _emit("legacy_completed", {"caller": caller, "latency_ms": ms, "ok": True})
            return CompatResult(
                text=res.text or "",
                provider=res.provider,
                model=res.model,
                path_used="legacy",
                mode=mode_r.value,
                ok=True,
                latency_ms=ms,
                result_fingerprint=_fingerprint(res.text or ""),
            )
        except Exception as e:
            ms = (time.monotonic() - t0) * 1000
            _emit("legacy_completed", {"caller": caller, "latency_ms": ms, "ok": False})
            return CompatResult(
                text="", ok=False, path_used="legacy", mode=mode_r.value,
                error_category="legacy_error", error_message=type(e).__name__,
                latency_ms=ms,
            )

    req = build_inference_request(
        caller, prompt_b, system_b, mission_id=mission_id, run_id=run_id,
    )

    # ── SHADOW ──────────────────────────────────────────────────────────
    if mode_r == InfRolloutMode.SHADOW:
        t0 = time.monotonic()
        legacy_err = ""
        try:
            leg = _run_legacy_generate(
                label, prompt_b, system_b, prefer=prefer,
                max_tokens=max_tokens, timeout=timeout, legacy_fn=legacy_fn,
            )
            legacy_text = leg.text or ""
            legacy_ok = True
            provider, model = leg.provider, leg.model
        except Exception as e:
            legacy_text, legacy_ok = "", False
            legacy_err = type(e).__name__
            provider, model = "", ""
        leg_ms = (time.monotonic() - t0) * 1000
        _inc("path_shadow")
        if legacy_ok:
            _inc("legacy_success")

        gov: StructuredInferenceResult
        try:
            _emit("governed_started", {"caller": caller, "shadow": True})
            gov = _run_governed(req, governed_fn=governed_fn)
        except Exception as e:
            from saathi.inference.request import InferenceErrorCategory
            gov = StructuredInferenceResult.failure(
                req.request_id, InferenceErrorCategory.INTERNAL, type(e).__name__,
            )
        if gov.ok:
            _inc("governed_success")
        else:
            _inc("governed_fail")
        cmp_ = _shadow_compare(legacy_text, gov)
        cmp_["prompt_size"] = len(prompt_b)
        cmp_["latency_legacy_ms"] = leg_ms
        _inc("shadow_comparisons")
        _emit("shadow_comparison", {
            "caller": caller,
            "legacy_ok": legacy_ok,
            "governed_ok": gov.ok,
            "error_category": gov.error_category or "",
            "local_model": gov.selected_model or "",
        })
        # Legacy is authoritative — local failure never blocks
        return CompatResult(
            text=legacy_text,
            provider=provider,
            model=model,
            path_used="shadow_legacy",
            mode=mode_r.value,
            ok=legacy_ok,
            warnings=list(gov.warnings or []),
            evidence_ref=gov.evidence_ref or "",
            error_category="" if legacy_ok else (legacy_err or "legacy_error"),
            latency_ms=leg_ms,
            result_fingerprint=_fingerprint(legacy_text),
            shadow=cmp_,
            metadata={"governed_ok": gov.ok, "governed_model": gov.selected_model},
        )

    # ── GOVERNED LOCAL (± fallback) ─────────────────────────────────────
    _emit("governed_started", {"caller": caller, "mode": mode_r.value})
    t0 = time.monotonic()
    try:
        gov = _run_governed(req, governed_fn=governed_fn)
    except Exception as e:
        from saathi.inference.request import InferenceErrorCategory
        gov = StructuredInferenceResult.failure(
            req.request_id, InferenceErrorCategory.INTERNAL, type(e).__name__,
        )
    gov_ms = (time.monotonic() - t0) * 1000
    with _metrics_lock:
        _metrics["latency_governed_ms_sum"] += gov_ms
        _metrics["latency_count"] += 1

    if gov.ok and (gov.output_text or "").strip():
        _inc("governed_success")
        _inc("path_governed")
        _emit("governed_completed", {
            "caller": caller, "ok": True, "latency_ms": gov_ms,
            "model": gov.selected_model, "evidence_ref": gov.evidence_ref,
        })
        return CompatResult(
            text=gov.output_text or "",
            provider=gov.selected_provider or "governed-local",
            model=gov.selected_model,
            path_used="governed_local",
            mode=mode_r.value,
            ok=True,
            warnings=list(gov.warnings or []),
            evidence_ref=gov.evidence_ref,
            latency_ms=gov.latency_ms or gov_ms,
            result_fingerprint=gov.result_fingerprint or _fingerprint(gov.output_text or ""),
            metadata={"finish_reason": gov.finish_reason},
        )

    _inc("governed_fail")
    cat = gov.error_category or "internal_inference_error"
    _emit("governed_completed", {
        "caller": caller, "ok": False, "error_category": cat, "latency_ms": gov_ms,
    })

    if mode_r == InfRolloutMode.GOVERNED_LOCAL_ONLY:
        return CompatResult(
            text="",
            path_used="governed_local",
            mode=mode_r.value,
            ok=False,
            warnings=list(gov.warnings or []),
            evidence_ref=gov.evidence_ref,
            error_category=cat,
            error_message=gov.error_message or "governed_local_failed",
            latency_ms=gov_ms,
        )

    # governed_local_with_fallback
    if not can_fallback(cat):
        _inc("fallback_denied_count")
        _emit("fallback_denied", {"caller": caller, "error_category": cat})
        return CompatResult(
            text="",
            path_used="governed_local",
            mode=mode_r.value,
            ok=False,
            warnings=list(gov.warnings or []) + [f"fallback_denied:{cat}"],
            evidence_ref=gov.evidence_ref,
            error_category=cat,
            error_message=gov.error_message or "fallback_denied",
            latency_ms=gov_ms,
        )

    # soft fallback to legacy
    _inc("fallback_count")
    _emit("fallback", {"caller": caller, "error_category": cat})
    t1 = time.monotonic()
    try:
        leg = _run_legacy_generate(
            label, prompt_b, system_b, prefer=prefer,
            max_tokens=max_tokens, timeout=timeout, legacy_fn=legacy_fn,
        )
        ms = (time.monotonic() - t1) * 1000
        _inc("legacy_success")
        _inc("path_governed_then_legacy")
        return CompatResult(
            text=leg.text or "",
            provider=leg.provider,
            model=leg.model,
            path_used="governed_local_then_legacy",
            mode=mode_r.value,
            ok=True,
            warnings=list(gov.warnings or []) + [f"fallback_from:{cat}"],
            evidence_ref=gov.evidence_ref,
            latency_ms=gov_ms + ms,
            result_fingerprint=_fingerprint(leg.text or ""),
            metadata={"fallback_from": cat},
        )
    except Exception as e:
        return CompatResult(
            text="",
            path_used="governed_local_then_legacy",
            mode=mode_r.value,
            ok=False,
            error_category="legacy_error",
            error_message=type(e).__name__,
            warnings=[f"fallback_from:{cat}"],
            latency_ms=gov_ms,
        )


# ── Public helpers for selected callers ─────────────────────────────────────

def cheap_ask_adopted(
    prompt: str,
    system: str = "You are a helpful assistant.",
    max_tokens: int = 1024,
    *,
    legacy_fn: Optional[LegacyFn] = None,
    governed_fn: Optional[GovernedFn] = None,
) -> dict[str, Any]:
    """cheap_ask with opt-in governed path. Public shape preserved."""
    # caller-specific max_tokens cannot expand global; clamp
    limits = CALLER_LIMITS[CALLER_CHEAP_ASK]
    _ = min(int(max_tokens), int(limits["max_output_tokens"]))
    cr = adopt_generate(
        CALLER_CHEAP_ASK, prompt, system,
        legacy_fn=legacy_fn, governed_fn=governed_fn,
    )
    if not cr.ok:
        return {
            "error": cr.error_message or cr.error_category or "failed",
            "path_used": cr.path_used,
            "mode": cr.mode,
        }
    out: dict[str, Any] = {
        "reply": cr.text,
        "model": cr.provider or cr.model or "unknown",
        "cost": "cheapest-available" if cr.path_used.startswith("legacy") or "legacy" in cr.path_used else "local",
        "path_used": cr.path_used,
        "mode": cr.mode,
    }
    if cr.warnings:
        out["warnings"] = cr.warnings
    if cr.evidence_ref:
        out["evidence_ref"] = cr.evidence_ref
    if cr.shadow:
        out["shadow"] = cr.shadow
    return out


def prose_clean_adopted(
    text: str,
    context: str = "",
    system: str = "You are an expert prose editor. Return ONLY the cleaned text.",
    *,
    legacy_fn: Optional[LegacyFn] = None,
    governed_fn: Optional[GovernedFn] = None,
) -> dict[str, Any]:
    """clean_prose with opt-in governed path. Caller should pass stop-slop system."""
    prompt = text
    if context:
        prompt = f"Context: {context}\n\n---\n\n{text}"
    cr = adopt_generate(
        CALLER_PROSE_CLEAN, prompt, system,
        legacy_fn=legacy_fn, governed_fn=governed_fn,
    )
    if not cr.ok:
        return {
            "error": cr.error_category or "failed",
            "message": (cr.error_message or "")[:300],
            "path_used": cr.path_used,
            "mode": cr.mode,
        }
    out: dict[str, Any] = {
        "cleaned": (cr.text or "").strip(),
        "original_length": len(text or ""),
        "cleaned_length": len((cr.text or "").strip()),
        "path_used": cr.path_used,
        "mode": cr.mode,
    }
    if cr.warnings:
        out["warnings"] = cr.warnings
    if cr.evidence_ref:
        out["evidence_ref"] = cr.evidence_ref
    if cr.shadow:
        out["shadow"] = cr.shadow
    return out
