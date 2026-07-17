"""M21.1 — Canonical inference request contract enforcement.

Extends M20.2 ``validate_inference_request`` with caller policy, kill switches,
fingerprinting, and privacy-safe telemetry. Does not replace ModelRouter.
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from saathi.inference.caller_policy import (
    CallerCertification,
    get_caller_policy,
    is_governed_callable,
    require_caller_policy,
)
from saathi.inference.config import InferenceSettings, load_inference_settings
from saathi.inference.provider_policy import (
    is_master_killed,
    is_provider_killed,
)
from saathi.inference.request import (
    InferenceErrorCategory,
    InferenceRequest,
    InferenceRequestError,
    Sensitivity,
    validate_inference_request,
)

CONTRACT_VERSION = "m21.1.contract.v1"

# Hard errors — never cloud/legacy soft-fallback (governed path)
HARD_DENIAL_CATEGORIES = frozenset({
    InferenceErrorCategory.SECURITY_POLICY_DENIED.value,
    InferenceErrorCategory.CAPABILITY_DENIED.value,
    InferenceErrorCategory.STREAMING_UNSUPPORTED.value,
    InferenceErrorCategory.PROMPT_TOO_LARGE.value,
    InferenceErrorCategory.OUTPUT_LIMIT_INVALID.value,
    InferenceErrorCategory.CLOUD_FALLBACK_DENIED.value,
    InferenceErrorCategory.INVALID_REQUEST.value,
    "unknown_caller",
    "caller_disabled",
    "caller_forbidden",
    "kill_switch",
    "privacy_denial",
    "cost_denial",
    "trading_isolation",
    "auth_denial",
    "tool_denial",
    "streaming_denial",
})


@dataclass
class ContractViolation:
    code: str
    category: str  # maps to InferenceErrorCategory value or hard code
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "category": self.category, "message": self.message}


@dataclass
class ContractValidationResult:
    ok: bool
    violations: list[ContractViolation] = field(default_factory=list)
    request_fingerprint: str = ""
    input_fingerprint: str = ""
    policy_decisions: dict[str, Any] = field(default_factory=dict)
    kill_switch: dict[str, Any] = field(default_factory=dict)
    contract_version: str = CONTRACT_VERSION

    def error_messages(self) -> list[str]:
        return [v.message for v in self.violations]

    def primary_category(self) -> str:
        if not self.violations:
            return ""
        return self.violations[0].category

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "violations": [v.to_dict() for v in self.violations],
            "request_fingerprint": self.request_fingerprint,
            "input_fingerprint": self.input_fingerprint,
            "policy_decisions": self.policy_decisions,
            "kill_switch": self.kill_switch,
            "contract_version": self.contract_version,
        }


def input_fingerprint(req: InferenceRequest) -> str:
    """Hash of input content only (not returned to clients as raw text)."""
    return req.prompt_fingerprint()


def request_fingerprint(req: InferenceRequest) -> str:
    """Stable fingerprint excluding request_id and timestamps.

    Covers caller, capability, input fingerprint, permissions, limits, privacy.
    Does not include raw prompt/output or secrets.
    """
    parts = [
        (req.caller_component or "").strip(),
        (req.preferred_capability or req.task_type or "").strip().lower(),
        req.prompt_fingerprint(),
        str(bool(req.local_only)),
        str(bool(req.cloud_fallback_permitted)),
        str(bool(req.tool_use_permitted)),
        str(bool(req.streaming_requested)),
        str(int(req.max_output_tokens)),
        str(float(req.timeout_seconds)),
        (req.sensitivity.value if isinstance(req.sensitivity, Sensitivity) else str(req.sensitivity)),
        str(bool(getattr(req, "log_prompt", False))),
        str(bool(getattr(req, "log_output", False))),
        (getattr(req, "retention_policy", "") or "metadata_only"),
        (getattr(req, "structured_output_schema", "") or ""),
        str(float(getattr(req, "request_cost_ceiling", 0.0) or 0.0)),
        (getattr(req, "contract_version", "") or CONTRACT_VERSION),
    ]
    raw = "|".join(parts)
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def ensure_idempotency_key(req: InferenceRequest) -> str:
    """Return existing key or derive privacy-safe scoped key (no prompt text)."""
    if (req.idempotency_key or "").strip():
        return req.idempotency_key.strip()
    # Optional for routine; derived for resume-friendly identity without content leak
    scope = "|".join(
        [
            req.caller_component or "",
            req.actor_id or "",
            getattr(req, "tenant_id", "") or "",
            req.workspace_id or "",
            request_fingerprint(req)[:32],
        ]
    )
    return "idem:" + hashlib.sha256(scope.encode("utf-8")).hexdigest()[:32]


def privacy_safe_telemetry(req: InferenceRequest, *, extra: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Fields safe to log — never raw prompt/output/credentials."""
    base = {
        "schema": "m21.1.telemetry.v1",
        "request_id": req.request_id,
        "caller_id": req.caller_component,
        "actor_present": bool(req.actor_id),
        "tenant_present": bool(getattr(req, "tenant_id", "")),
        "capability": req.preferred_capability or req.task_type,
        "local_only": req.local_only,
        "cloud_fallback_permitted": req.cloud_fallback_permitted,
        "tool_use_permitted": req.tool_use_permitted,
        "streaming_requested": req.streaming_requested,
        "max_output_tokens": req.max_output_tokens,
        "timeout_seconds": req.timeout_seconds,
        "privacy": req.sensitivity.value if isinstance(req.sensitivity, Sensitivity) else str(req.sensitivity),
        "input_chars": len(req.prompt or "") + (
            sum(len(str(m.get("content") or "")) for m in (req.messages or ()))
        ),
        "request_fingerprint": request_fingerprint(req),
        "input_fingerprint": input_fingerprint(req),
        "idempotency_present": bool((req.idempotency_key or "").strip()),
        "contract_version": getattr(req, "contract_version", CONTRACT_VERSION) or CONTRACT_VERSION,
        "log_prompt": False,  # never true in telemetry payload content
        "log_output": False,
    }
    if extra:
        for k, v in extra.items():
            if k in ("prompt", "output", "text", "system", "messages", "api_key", "token"):
                continue
            base[k] = v
    return base


def validate_contract(
    req: InferenceRequest,
    settings: Optional[InferenceSettings] = None,
    *,
    governed: bool = True,
    provider_family: str = "ollama",
) -> ContractValidationResult:
    """Full M21.1 contract validation. Empty violations ⇒ ok."""
    settings = settings or load_inference_settings()
    violations: list[ContractViolation] = []
    decisions: dict[str, Any] = {"governed": governed}

    def deny(code: str, category: str, message: str) -> None:
        violations.append(ContractViolation(code, category, message))

    # Kill switches first — before any provider
    kill = {
        "kill_all": is_master_killed(),
        "provider_killed": is_provider_killed(provider_family) if provider_family else False,
        "provider_family": provider_family,
    }
    if kill["kill_all"]:
        deny("kill_all", "kill_switch", "SAATHI_INFERENCE_KILL_ALL is active")
    if kill["provider_killed"]:
        deny(
            "provider_kill",
            InferenceErrorCategory.PROVIDER_UNAVAILABLE.value,
            f"provider {provider_family} killed by policy",
        )

    caller = (req.caller_component or "").strip() or "unknown"
    # Empty caller is coerced to transitional "unknown" (test-only under M21.2).
    # New production code must set an explicit registered caller_id.
    pol = require_caller_policy(caller)
    decisions["caller_certification"] = pol.certification.value
    decisions["caller_enabled"] = pol.enabled

    if governed:
        # M21.3: transitional unknown denied in all environments (dev/staging/prod/pytest)
        if caller == "unknown":
            deny(
                "unknown_caller",
                "unknown_caller",
                "unknown caller denied (M21.3 fail-closed in all environments)",
            )

        if get_caller_policy(caller) is None:
            deny(
                "unknown_caller",
                "unknown_caller",
                f"unknown caller {caller!r} fail closed on governed path",
            )
        elif pol.certification is CallerCertification.FORBIDDEN or not pol.enabled:
            deny(
                "caller_forbidden" if pol.certification is CallerCertification.FORBIDDEN else "caller_disabled",
                "caller_forbidden" if pol.certification is CallerCertification.FORBIDDEN else "caller_disabled",
                f"caller {caller} disabled or forbidden",
            )
        elif pol.legacy and pol.certification is CallerCertification.LEGACY:
            deny(
                "legacy_not_governed",
                InferenceErrorCategory.SECURITY_POLICY_DENIED.value,
                f"legacy caller {caller} cannot use governed path without migration",
            )
        elif not is_governed_callable(caller) and pol.certification is CallerCertification.UNKNOWN:
            deny("unknown_caller", "unknown_caller", f"caller {caller!r} not governed-callable")

        # Capability
        cap = (req.preferred_capability or req.task_type or "standard").lower()
        if cap not in pol.allowed_capabilities and cap not in {"standard", "private"}:
            # private always allowed for local-only
            if not (cap == "private" and req.local_only):
                if cap not in pol.allowed_capabilities:
                    deny(
                        "capability_denied",
                        InferenceErrorCategory.CAPABILITY_DENIED.value,
                        f"capability {cap!r} not allowed for caller {caller}",
                    )

        # Cloud / local policy
        if not req.local_only and not pol.cloud_allowed:
            deny(
                "cloud_not_allowed",
                InferenceErrorCategory.CLOUD_FALLBACK_DENIED.value,
                "cloud not allowed for this caller",
            )
        if req.cloud_fallback_permitted:
            if not pol.cloud_fallback_allowed:
                deny(
                    "cloud_fallback_caller",
                    InferenceErrorCategory.CLOUD_FALLBACK_DENIED.value,
                    "cloud fallback not allowed for this caller",
                )
            if not settings.allow_cloud_fallback:
                deny(
                    "cloud_fallback_settings",
                    InferenceErrorCategory.CLOUD_FALLBACK_DENIED.value,
                    "SAATHI_ALLOW_CLOUD_FALLBACK is false",
                )
        if req.local_only is False and req.sensitivity in {
            Sensitivity.CONFIDENTIAL,
            Sensitivity.SENSITIVE,
        }:
            deny(
                "privacy_local",
                "privacy_denial",
                "sensitive/confidential requires local_only",
            )

        # Tools / streaming
        if req.tool_use_permitted and not pol.tools_allowed:
            deny(
                "tool_denial",
                InferenceErrorCategory.CAPABILITY_DENIED.value,
                "tool use not allowed for this caller",
            )
        if req.streaming_requested and not pol.streaming_allowed:
            deny(
                "streaming_denial",
                InferenceErrorCategory.STREAMING_UNSUPPORTED.value,
                "streaming not certified for this caller",
            )

        # Bounds vs caller policy
        prompt_len = len(req.prompt or "")
        if req.messages:
            prompt_len = sum(len(str(m.get("content") or "")) for m in req.messages)
        if prompt_len > pol.max_input_chars:
            deny(
                "input_too_large",
                InferenceErrorCategory.PROMPT_TOO_LARGE.value,
                f"input exceeds caller max_input_chars={pol.max_input_chars}",
            )
        if req.max_output_tokens > pol.max_output_tokens:
            deny(
                "output_too_large",
                InferenceErrorCategory.OUTPUT_LIMIT_INVALID.value,
                f"max_output_tokens exceeds caller max {pol.max_output_tokens}",
            )
        if req.timeout_seconds > pol.timeout_seconds + 0.01:
            deny(
                "timeout_too_large",
                InferenceErrorCategory.INVALID_REQUEST.value,
                f"timeout exceeds caller max {pol.timeout_seconds}",
            )
        retries = int(getattr(req, "max_retries", 0) or 0)
        if retries < 0:
            deny("negative_retry", InferenceErrorCategory.INVALID_REQUEST.value, "max_retries negative")
        if retries > pol.max_retries:
            deny(
                "retry_above_policy",
                InferenceErrorCategory.INVALID_REQUEST.value,
                f"max_retries {retries} > policy {pol.max_retries}",
            )

        # Logging privacy
        if getattr(req, "log_prompt", False) and req.sensitivity in {
            Sensitivity.CONFIDENTIAL,
            Sensitivity.SENSITIVE,
            Sensitivity.INTERNAL,
        }:
            deny(
                "raw_log_prompt",
                "privacy_denial",
                "log_prompt denied for non-public sensitivity",
            )
        if getattr(req, "log_output", False) and req.sensitivity != Sensitivity.PUBLIC:
            deny(
                "raw_log_output",
                "privacy_denial",
                "log_output denied for non-public sensitivity",
            )

        # Cost ceiling
        ceiling = float(getattr(req, "request_cost_ceiling", 0.0) or 0.0)
        if ceiling > pol.request_cost_ceiling + 1e-9 and pol.request_cost_ceiling == 0.0:
            # request asks for paid cloud budget while policy is local-free only
            if ceiling > 0 and not pol.cloud_allowed:
                deny(
                    "cost_ceiling",
                    "cost_denial",
                    "request_cost_ceiling above caller policy for non-cloud caller",
                )

        # Trading isolation
        if "trading" in caller.lower() or caller == "trading_guardian":
            deny(
                "trading_isolation",
                "trading_isolation",
                "Trading Guardian callers forbidden on inference contract",
            )

        # Metadata hard bypasses
        meta = req.metadata or {}
        if meta.get("force_model") or meta.get("bypass_router"):
            deny(
                "model_override",
                InferenceErrorCategory.SECURITY_POLICY_DENIED.value,
                "direct model override / router bypass denied",
            )
        if meta.get("force_engine_url"):
            deny(
                "engine_url",
                InferenceErrorCategory.SECURITY_POLICY_DENIED.value,
                "arbitrary engine URL denied",
            )
        if meta.get("force_provider"):
            deny(
                "provider_override",
                InferenceErrorCategory.SECURITY_POLICY_DENIED.value,
                "caller-supplied provider override denied",
            )

    # Base M20.2 structural validation (settings bounds)
    for msg in validate_inference_request(req, settings):
        # Map messages to categories
        cat = InferenceErrorCategory.INVALID_REQUEST.value
        if "stream" in msg:
            cat = InferenceErrorCategory.STREAMING_UNSUPPORTED.value
        elif "tool" in msg:
            cat = InferenceErrorCategory.CAPABILITY_DENIED.value
        elif "prompt exceeds" in msg:
            cat = InferenceErrorCategory.PROMPT_TOO_LARGE.value
        elif "max_output_tokens" in msg:
            cat = InferenceErrorCategory.OUTPUT_LIMIT_INVALID.value
        elif "override" in msg or "bypass" in msg or "URL" in msg:
            cat = InferenceErrorCategory.SECURITY_POLICY_DENIED.value
        elif "sensitive" in msg:
            cat = "privacy_denial"
        # Dedupe if already covered
        if not any(msg in v.message for v in violations):
            deny("base_validation", cat, msg)

    rfp = request_fingerprint(req)
    ifp = input_fingerprint(req)
    return ContractValidationResult(
        ok=len(violations) == 0,
        violations=violations,
        request_fingerprint=rfp,
        input_fingerprint=ifp,
        policy_decisions=decisions,
        kill_switch=kill,
    )


def is_hard_denial(category: str | None) -> bool:
    if not category:
        return False
    return str(category).strip().lower() in HARD_DENIAL_CATEGORIES or str(category) in HARD_DENIAL_CATEGORIES


def enforce_or_errors(
    req: InferenceRequest,
    settings: Optional[InferenceSettings] = None,
    *,
    governed: bool = True,
) -> list[str]:
    """Compatibility helper returning message list (gateway style)."""
    return validate_contract(req, settings, governed=governed).error_messages()


def emit_contract_telemetry(req: InferenceRequest, *, stage: str, **extra: Any) -> dict[str, Any]:
    payload = privacy_safe_telemetry(req, extra={"stage": stage, **extra, "ts": time.time()})
    try:
        from saathi.events import bus

        bus.publish_sync("inference.contract." + stage, payload)
    except Exception:
        pass
    return payload
