"""M21.3 — Chat compatibility adapter.

Preserves chat public behavior while constructing a canonical InferenceRequest
and applying kill-switch / caller-policy preflight before provider execution.

Execution path (prefer governed when enabled; else single legacy sink):

  ChatEngine._default_llm
    → chat_generate (this module)
      → preflight (chat_engine caller)
      → optional governed local path
      → EXPLICIT_LEGACY_EXCEPTION: saathi.llm.generate (ModelRouter chain)

Does not rewrite ChatEngine. Does not create a second gateway.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

CALLER_CHAT_ENGINE = "chat_engine"
PATH_ID = "chat_engine"


def chat_generate(
    prompt: str,
    system: str = "",
    *,
    max_tokens: int = 2048,
    timeout: int = 120,
    legacy_fn: Optional[Any] = None,
) -> dict[str, Any]:
    """Return ``{"text", "provider", "tokens"}`` matching ChatLLMAdapter contract.

    Public chat API shape is preserved. Raw prompt/output are never logged.
    """
    from saathi.inference.legacy_facade import preflight_inference

    pf = preflight_inference(
        caller_id=CALLER_CHAT_ENGINE,
        path_id=PATH_ID,
        prompt=prompt or "",
        system=system or "",
        max_tokens=max_tokens,
        timeout=float(timeout),
    )
    if not pf.ok:
        # Honest error — chat engine converts empty/error into user-facing failure
        raise RuntimeError(pf.error_message or pf.reason_code or "chat_preflight_denied")

    # Bound inputs (policy)
    try:
        from saathi.inference.caller_policy import get_caller_policy

        pol = get_caller_policy(CALLER_CHAT_ENGINE)
        max_in = int(pol.max_input_chars) if pol else 32000
    except Exception:
        max_in = 32000
    prompt_b = (prompt or "")[:max_in]
    system_b = (system or "You are Saathi, Ajay's AI operating system. Be direct and useful.")[:4000]
    max_out = int(pf.max_output_tokens)
    timeout_s = int(max(1, min(pf.timeout_seconds, 300)))

    # Optional governed path when dual flags are on (M20.2) — never silent cloud
    try:
        from saathi.inference.config import load_inference_settings

        settings = load_inference_settings()
        if settings.enabled and settings.gateway_enabled:
            from saathi.inference.compat import build_inference_request, _run_governed
            from saathi.inference.caller_rollout import CALLER_CHEAP_ASK

            # Reuse compat builder bounds; force chat caller via request fields
            req = build_inference_request(
                CALLER_CHEAP_ASK,  # limits table fallback
                prompt_b,
                system_b,
            )
            # Rebuild with chat caller (compat limits for chat registered separately)
            from saathi.inference.request import InferenceRequest, Sensitivity

            req = InferenceRequest(
                request_id=pf.request_id,
                prompt=prompt_b,
                system=system_b,
                caller_component=CALLER_CHAT_ENGINE,
                max_output_tokens=max_out,
                timeout_seconds=float(timeout_s),
                local_only=True,
                cloud_allowed=False,
                cloud_fallback_permitted=False,
                task_type="standard",
                preferred_capability="standard",
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
                    "m21_3_chat_adapter": True,
                    "path_id": PATH_ID,
                    "prompt_chars": len(prompt_b),
                    "prompt_fingerprint": pf.prompt_fingerprint,
                },
            )
            # Chat is LEGACY certification — governed path may deny legacy callers.
            # Only attempt governed if policy allows; otherwise skip to legacy sink.
            from saathi.inference.caller_policy import is_governed_callable

            if is_governed_callable(CALLER_CHAT_ENGINE):
                gov = _run_governed(req)
                if gov.ok and (gov.output_text or "").strip():
                    return {
                        "text": gov.output_text or "",
                        "provider": gov.selected_provider or gov.selected_model or "governed_local",
                        "tokens": getattr(gov, "output_tokens", 0) or 0,
                        "path_used": "governed_local",
                        "request_id": pf.request_id,
                    }
    except Exception:
        pass

    # Single allowed legacy sink: ModelRouter via saathi.llm.generate
    from saathi.model_router import ModelLabel, Prefer, Privacy

    if legacy_fn is not None:
        res = legacy_fn(prompt_b, system_b)
        if isinstance(res, dict):
            res.setdefault("path_used", "legacy_injected")
            res.setdefault("request_id", pf.request_id)
            return res
        return {
            "text": str(res),
            "provider": "legacy_injected",
            "tokens": 0,
            "path_used": "legacy_injected",
            "request_id": pf.request_id,
        }

    from saathi.llm import generate

    # Privacy: chat policy allows historical cloud via router only when not killed.
    # Cloud fallback at provider-governance layer remains default-off.
    privacy = Privacy.CLOUD_OK if pf.cloud_allowed else Privacy.LOCAL_ONLY
    try:
        out = generate(
            ModelLabel.STANDARD,
            prompt_b,
            system=system_b,
            privacy=privacy,
            prefer=Prefer.QUALITY,
            max_tokens=max_out,
            timeout=timeout_s,
            caller_id=CALLER_CHAT_ENGINE,
            skip_preflight=False,
        )
    except TypeError:
        # Older signature tests
        out = generate(
            ModelLabel.STANDARD,
            prompt_b,
            system=system_b,
            privacy=privacy,
            prefer=Prefer.QUALITY,
            max_tokens=max_out,
            timeout=timeout_s,
        )
    return {
        "text": out.text or "",
        "provider": out.provider or "",
        "tokens": getattr(out, "tokens", 0) or 0,
        "path_used": "legacy_llm_generate",
        "request_id": pf.request_id,
        "model": getattr(out, "model", "") or "",
    }
