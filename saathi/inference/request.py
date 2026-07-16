"""M20.2 governed local inference request contract.

Callers express requirements; they cannot force an unapproved model.
ModelRouter remains the sole selection authority.
"""
from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional, Sequence

from saathi.inference.config import InferenceSettings, load_inference_settings
from saathi.model_router import ModelLabel, Prefer


class Sensitivity(str, Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    SENSITIVE = "sensitive"


class InferenceErrorCategory(str, Enum):
    INFERENCE_DISABLED = "inference_disabled"
    GATEWAY_DISABLED = "gateway_path_disabled"
    INVALID_REQUEST = "invalid_request"
    CAPABILITY_DENIED = "capability_denied"
    ROUTER_FAILED = "router_failed"
    NO_SUITABLE_MODEL = "no_suitable_model"
    MODEL_NOT_REGISTERED = "model_not_registered"
    ENGINE_UNAVAILABLE = "engine_unavailable"
    MODEL_UNAVAILABLE = "model_unavailable"
    HARDWARE_POLICY_DENIED = "hardware_policy_denied"
    PROMPT_TOO_LARGE = "prompt_too_large"
    OUTPUT_LIMIT_INVALID = "output_limit_invalid"
    TIMEOUT = "timeout"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    MALFORMED_PROVIDER_RESPONSE = "malformed_provider_response"
    CLOUD_FALLBACK_DENIED = "cloud_fallback_denied"
    STREAMING_UNSUPPORTED = "streaming_unsupported"
    SECURITY_POLICY_DENIED = "security_policy_denied"
    CONCURRENCY_LIMIT = "concurrency_limit"
    INTERNAL = "internal_inference_error"


class InferenceRequestError(ValueError):
    def __init__(self, category: InferenceErrorCategory, message: str):
        super().__init__(message)
        self.category = category


_LABEL_MAP = {
    "screening": ModelLabel.SCREENING,
    "standard": ModelLabel.STANDARD,
    "reasoning": ModelLabel.REASONING,
    "multimodal": ModelLabel.MULTIMODAL,
    "fast": ModelLabel.FAST,
    "long": ModelLabel.LONG,
    "private": ModelLabel.PRIVATE,
}


@dataclass(frozen=True)
class InferenceRequest:
    """Typed inference request for the governed gateway path."""

    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    mission_id: str = ""
    run_id: str = ""
    caller_component: str = "unknown"
    actor_id: str = ""
    prompt: str = ""
    system: str = "You are a helpful assistant."
    messages: Optional[tuple[dict[str, Any], ...]] = None
    task_type: str = "standard"  # maps to ModelLabel
    sensitivity: Sensitivity = Sensitivity.INTERNAL
    preferred_capability: str = "standard"
    max_output_tokens: int = 512
    timeout_seconds: float = 60.0
    temperature: float = 0.0  # deterministic default for pilot
    local_only: bool = True
    cloud_fallback_permitted: bool = False
    tool_use_permitted: bool = False
    streaming_requested: bool = False
    evidence_required: bool = True
    prefer: str = "cost"  # cost | latency | quality
    # Callers may *hint* but cannot force unapproved models:
    model_hint: str = ""
    engine_hint: str = ""
    workspace_id: str = ""
    idempotency_key: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def prompt_fingerprint(self) -> str:
        raw = (self.system or "") + "\n" + (self.prompt or "")
        if self.messages:
            raw += "\n" + repr(self.messages)
        return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def label(self) -> ModelLabel:
        key = (self.preferred_capability or self.task_type or "standard").lower()
        if self.local_only or self.sensitivity in {
            Sensitivity.CONFIDENTIAL,
            Sensitivity.SENSITIVE,
        }:
            # Prefer private when local-only / sensitive
            if key not in _LABEL_MAP:
                return ModelLabel.PRIVATE
        return _LABEL_MAP.get(key, ModelLabel.STANDARD)

    def prefer_enum(self) -> Prefer:
        p = (self.prefer or "cost").lower()
        if p == "latency":
            return Prefer.LATENCY
        if p == "quality":
            return Prefer.QUALITY
        return Prefer.COST

    def build_messages(self) -> list[dict[str, Any]]:
        if self.messages:
            return [dict(m) for m in self.messages]
        out: list[dict[str, Any]] = []
        if self.system:
            out.append({"role": "system", "content": self.system})
        out.append({"role": "user", "content": self.prompt})
        return out


def validate_inference_request(
    req: InferenceRequest,
    settings: Optional[InferenceSettings] = None,
) -> list[str]:
    """Return validation error messages (empty = valid). Raises not used for multi-error."""
    settings = settings or load_inference_settings()
    errors: list[str] = []
    if not req.request_id:
        errors.append("request_id required")
    if not (req.prompt or "").strip() and not req.messages:
        errors.append("empty prompt")
    prompt_text = req.prompt or ""
    if req.messages:
        prompt_text = " ".join(str(m.get("content") or "") for m in req.messages)
    if len(prompt_text) > settings.max_prompt_chars:
        errors.append(f"prompt exceeds max_prompt_chars={settings.max_prompt_chars}")
    if req.max_output_tokens < 1 or req.max_output_tokens > settings.max_output_tokens:
        errors.append(
            f"max_output_tokens must be 1..{settings.max_output_tokens}"
        )
    if req.timeout_seconds <= 0 or req.timeout_seconds > 600:
        errors.append("timeout_seconds must be in (0, 600]")
    if req.streaming_requested:
        errors.append("streaming unsupported in M20.2")
    if req.tool_use_permitted:
        errors.append("tool use not authorized on local inference pilot")
    # Direct model/engine override attempts are recorded but rejected as force-bypass
    if req.metadata.get("force_model") or req.metadata.get("bypass_router"):
        errors.append("direct model override / router bypass denied")
    if req.metadata.get("force_engine_url"):
        errors.append("arbitrary engine URL denied")
    if req.cloud_fallback_permitted and not settings.allow_cloud_fallback:
        # not a hard request error — handled at policy time; still note if sensitive
        pass
    if req.local_only is False and req.sensitivity in {
        Sensitivity.CONFIDENTIAL,
        Sensitivity.SENSITIVE,
    }:
        errors.append("sensitive requests require local_only=True")
    return errors


def request_from_toolintent_parameters(
    parameters: dict[str, Any],
    *,
    metadata: Optional[dict[str, Any]] = None,
    mission_id: str = "",
    actor_id: str = "",
    intent_id: str = "",
    timeout: Optional[int] = None,
) -> InferenceRequest:
    """Build InferenceRequest from ToolIntent.parameters + metadata."""
    meta = metadata or {}
    sens_raw = str(meta.get("data_sensitivity") or parameters.get("sensitivity") or "internal").lower()
    try:
        sensitivity = Sensitivity(sens_raw)
    except ValueError:
        sensitivity = Sensitivity.INTERNAL
    local_only = bool(
        meta.get("local_only", sensitivity in {Sensitivity.CONFIDENTIAL, Sensitivity.SENSITIVE})
    )
    if sensitivity in {Sensitivity.CONFIDENTIAL, Sensitivity.SENSITIVE}:
        local_only = True
    prompt = str(parameters.get("prompt") or parameters.get("input") or "")
    system = str(parameters.get("system") or "You are a helpful assistant.")
    max_tok = int(parameters.get("max_tokens") or parameters.get("max_output_tokens") or 512)
    task = str(parameters.get("task_type") or parameters.get("label") or meta.get("task_type") or "standard")
    # model: "auto" / empty = no force; explicit force only via metadata.force_model
    model_hint = str(parameters.get("model") or "")
    if model_hint.lower() in {"auto", "auto-select", ""}:
        model_hint = ""
    return InferenceRequest(
        request_id=intent_id or str(uuid.uuid4()),
        mission_id=mission_id or str(meta.get("mission_id") or ""),
        run_id=str(meta.get("run_id") or ""),
        caller_component=str(meta.get("caller") or "execution_gateway"),
        actor_id=actor_id,
        prompt=prompt,
        system=system,
        task_type=task,
        sensitivity=sensitivity,
        preferred_capability=str(
            parameters.get("capability") or task or ("private" if local_only else "standard")
        ),
        max_output_tokens=max_tok,
        timeout_seconds=float(timeout or parameters.get("timeout") or meta.get("max_latency_sec") or 60),
        temperature=float(parameters.get("temperature", 0.0)),
        local_only=local_only,
        cloud_fallback_permitted=bool(meta.get("cloud_fallback") or parameters.get("cloud_fallback")),
        tool_use_permitted=bool(parameters.get("tools") or meta.get("tool_use")),
        streaming_requested=bool(parameters.get("stream") or meta.get("stream")),
        evidence_required=bool(meta.get("evidence_required", True)),
        prefer=str(meta.get("prefer") or parameters.get("prefer") or "cost"),
        model_hint=model_hint,
        engine_hint=str(parameters.get("engine") or ""),
        workspace_id=str(meta.get("workspace_id") or ""),
        idempotency_key=str(meta.get("idempotency_key") or ""),
        metadata={
            k: v
            for k, v in meta.items()
            if k
            not in {
                "data_sensitivity",
                "local_only",
                "cloud_fallback",
                "stream",
                "tool_use",
            }
        },
    )
