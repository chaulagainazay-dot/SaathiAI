"""M21.3 — Shared preflight governance for residual / compatibility inference paths.

Does not select providers, invoke SDKs, or open network sockets.
Callers still execute through ModelRouter + approved adapters / legacy sinks
after this preflight returns ok.

Emits privacy-safe telemetry only (no prompt/output bodies).
"""
from __future__ import annotations

import hashlib
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Telemetry ring (privacy-safe only)
_events: list[dict[str, Any]] = []
_MAX_EVENTS = 200


@dataclass(frozen=True)
class PreflightResult:
    ok: bool
    request_id: str
    caller_id: str
    path_id: str
    reason_code: str = ""
    error_message: str = ""
    max_output_tokens: int = 512
    timeout_seconds: float = 45.0
    privacy: str = "internal"
    cloud_allowed: bool = False
    cloud_fallback_allowed: bool = False
    max_retries: int = 0
    prompt_fingerprint: str = ""
    prompt_chars: int = 0
    system_chars: int = 0
    kill_all: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "request_id": self.request_id,
            "caller_id": self.caller_id,
            "path_id": self.path_id,
            "reason_code": self.reason_code,
            "error_message": self.error_message,
            "max_output_tokens": self.max_output_tokens,
            "timeout_seconds": self.timeout_seconds,
            "privacy": self.privacy,
            "cloud_allowed": self.cloud_allowed,
            "cloud_fallback_allowed": self.cloud_fallback_allowed,
            "max_retries": self.max_retries,
            "prompt_fingerprint": self.prompt_fingerprint,
            "prompt_chars": self.prompt_chars,
            "system_chars": self.system_chars,
            "kill_all": self.kill_all,
            "metadata": dict(self.metadata),
        }


def _fp(text: str) -> str:
    return "sha256:" + hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:24]


def _emit(event: str, payload: dict[str, Any]) -> None:
    safe = {
        k: v
        for k, v in payload.items()
        if k
        not in (
            "prompt",
            "output",
            "text",
            "system",
            "messages",
            "content",
            "api_key",
            "authorization",
        )
    }
    entry = {"event": event, "ts": time.time(), **safe}
    _events.append(entry)
    if len(_events) > _MAX_EVENTS:
        del _events[: _MAX_EVENTS // 2]
    try:
        from saathi.events import bus

        bus.publish_sync(f"inference.legacy.{event}", safe)
    except Exception:
        pass


def recent_preflight_events(limit: int = 40) -> list[dict[str, Any]]:
    return list(_events[-limit:])


def preflight_inference(
    *,
    caller_id: str,
    path_id: str,
    prompt: str,
    system: str = "",
    max_tokens: int = 2048,
    timeout: float = 60.0,
    require_registered_caller: bool = True,
    respect_master_kill: bool = True,
) -> PreflightResult:
    """Validate caller policy + kill switches before any provider execution.

    Never logs raw prompt/system/output.
    """
    rid = f"m21.3-{uuid.uuid4().hex[:16]}"
    cid = (caller_id or "").strip() or "unknown"
    prompt_s = prompt or ""
    system_s = system or ""
    meta: dict[str, Any] = {"path_id": path_id, "contract": "m21.3"}

    kill_all = False
    try:
        from saathi.inference.provider_policy import is_master_killed

        kill_all = bool(is_master_killed())
    except Exception:
        kill_all = os.getenv("SAATHI_INFERENCE_KILL_ALL", "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

    if respect_master_kill and kill_all:
        res = PreflightResult(
            ok=False,
            request_id=rid,
            caller_id=cid,
            path_id=path_id,
            reason_code="kill_switch_active",
            error_message="SAATHI_INFERENCE_KILL_ALL is active",
            kill_all=True,
            prompt_fingerprint=_fp(prompt_s),
            prompt_chars=len(prompt_s),
            system_chars=len(system_s),
            metadata=meta,
        )
        _emit("preflight_denied", res.to_dict())
        return res

    # Transitional unknown: fail closed everywhere (M21.3)
    if cid == "unknown":
        res = PreflightResult(
            ok=False,
            request_id=rid,
            caller_id=cid,
            path_id=path_id,
            reason_code="unknown_caller",
            error_message="unknown caller denied (M21.3 fail-closed)",
            kill_all=kill_all,
            prompt_fingerprint=_fp(prompt_s),
            prompt_chars=len(prompt_s),
            system_chars=len(system_s),
            metadata=meta,
        )
        _emit("preflight_denied", res.to_dict())
        return res

    pol = None
    try:
        from saathi.inference.caller_policy import (
            CallerCertification,
            get_caller_policy,
            require_caller_policy,
        )

        pol = get_caller_policy(cid)
        if require_registered_caller and pol is None:
            res = PreflightResult(
                ok=False,
                request_id=rid,
                caller_id=cid,
                path_id=path_id,
                reason_code="unknown_caller",
                error_message=f"unregistered caller {cid!r} denied",
                kill_all=kill_all,
                prompt_fingerprint=_fp(prompt_s),
                prompt_chars=len(prompt_s),
                system_chars=len(system_s),
                metadata=meta,
            )
            _emit("preflight_denied", res.to_dict())
            return res
        if pol is None:
            pol = require_caller_policy(cid)
        if pol.certification is CallerCertification.FORBIDDEN or not pol.enabled:
            res = PreflightResult(
                ok=False,
                request_id=rid,
                caller_id=cid,
                path_id=path_id,
                reason_code="caller_forbidden",
                error_message=f"caller {cid} disabled or forbidden",
                kill_all=kill_all,
                prompt_fingerprint=_fp(prompt_s),
                prompt_chars=len(prompt_s),
                system_chars=len(system_s),
                metadata=meta,
            )
            _emit("preflight_denied", res.to_dict())
            return res
    except Exception as e:
        # Fail closed on policy load failure for production posture
        prod = os.getenv("SAATHI_PRODUCTION_POSTURE", "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        if prod:
            res = PreflightResult(
                ok=False,
                request_id=rid,
                caller_id=cid,
                path_id=path_id,
                reason_code="policy_error",
                error_message=type(e).__name__,
                kill_all=kill_all,
                prompt_fingerprint=_fp(prompt_s),
                prompt_chars=len(prompt_s),
                system_chars=len(system_s),
                metadata=meta,
            )
            _emit("preflight_denied", res.to_dict())
            return res

    max_out = int(max_tokens or 512)
    timeout_s = float(timeout or 60.0)
    cloud_ok = False
    cloud_fb = False
    privacy = "internal"
    max_retries = 0
    if pol is not None:
        max_out = min(max_out, int(pol.max_output_tokens))
        timeout_s = min(timeout_s, float(pol.timeout_seconds))
        # Bound input size without logging content
        max_in = int(pol.max_input_chars)
        if len(prompt_s) > max_in:
            meta["prompt_truncated"] = True
        cloud_ok = bool(pol.cloud_allowed)
        cloud_fb = bool(pol.cloud_fallback_allowed)
        privacy = str(pol.privacy_default or "internal")
        max_retries = int(pol.max_retries or 0)
        # Legacy callers retain historical cloud posture only when policy says so
        if pol.legacy and pol.log_prompt:
            # Never allow log_prompt=True on residual paths (M21.3 privacy)
            meta["log_prompt_forced_off"] = True

    # Hard ceiling: never unbounded
    if max_out <= 0 or max_out > 8192:
        max_out = min(max(max_out, 1), 8192) if max_out > 0 else 512
    if timeout_s <= 0 or timeout_s > 300:
        timeout_s = min(max(timeout_s, 1.0), 300.0) if timeout_s > 0 else 60.0
    if max_retries < 0:
        max_retries = 0
    if max_retries > 2:
        max_retries = 2  # residual paths cannot expand beyond M21.2 defaults

    res = PreflightResult(
        ok=True,
        request_id=rid,
        caller_id=cid,
        path_id=path_id,
        max_output_tokens=max_out,
        timeout_seconds=timeout_s,
        privacy=privacy,
        cloud_allowed=cloud_ok,
        cloud_fallback_allowed=cloud_fb,
        max_retries=max_retries,
        prompt_fingerprint=_fp(prompt_s),
        prompt_chars=len(prompt_s),
        system_chars=len(system_s),
        kill_all=kill_all,
        metadata=meta,
    )
    _emit("preflight_ok", res.to_dict())
    return res


def build_canonical_request_for_legacy(
    *,
    caller_id: str,
    prompt: str,
    system: str = "",
    max_tokens: int = 512,
    timeout: float = 60.0,
    task_type: str = "standard",
) -> Any:
    """Build a canonical InferenceRequest for telemetry / contract checks.

    Does not execute inference.
    """
    from saathi.inference.request import InferenceRequest, Sensitivity

    pf = preflight_inference(
        caller_id=caller_id,
        path_id="canonical_request_builder",
        prompt=prompt,
        system=system,
        max_tokens=max_tokens,
        timeout=timeout,
    )
    # Truncate to policy bounds without logging
    try:
        from saathi.inference.caller_policy import get_caller_policy

        pol = get_caller_policy(caller_id)
        max_in = int(pol.max_input_chars) if pol else 8000
    except Exception:
        max_in = 8000
    body = (prompt or "")[:max_in]
    sys = (system or "You are a helpful assistant.")[:2000]
    return InferenceRequest(
        request_id=pf.request_id,
        prompt=body,
        system=sys,
        caller_component=caller_id,
        max_output_tokens=pf.max_output_tokens if pf.ok else min(int(max_tokens), 512),
        timeout_seconds=pf.timeout_seconds if pf.ok else min(float(timeout), 60.0),
        local_only=not (pf.cloud_allowed if pf.ok else False),
        cloud_allowed=pf.cloud_allowed if pf.ok else False,
        cloud_fallback_permitted=False,  # M21.3: never silent cloud fallback
        task_type=task_type,
        preferred_capability=task_type,
        sensitivity=Sensitivity.INTERNAL,
        max_retries=0,
        fallback_policy="none",
        tool_use_permitted=False,
        streaming_requested=False,
        log_prompt=False,
        log_output=False,
        retention_policy="metadata_only",
        request_cost_ceiling=0.0,
        contract_version="m21.3",
        metadata={
            "m21_3_legacy_facade": True,
            "path_id": "legacy_facade",
            "prompt_chars": len(body),
            "prompt_fingerprint": pf.prompt_fingerprint,
            "preflight_ok": pf.ok,
            "preflight_reason": pf.reason_code,
        },
    )
