"""cheap_llm — routine/non-critical tasks via ModelRouter + governed paths.

M21.2: direct CHEAP_PROXY httpx bypass removed. Public API unchanged
(returns ``{reply|error, ...}``). Flow:

  compat adoption (canonical request) → provider decision → ModelRouter/legacy
  → explicit error if all governed paths fail (no ungoverned proxy)
"""
from __future__ import annotations

import os
from typing import Any

from .. import config


def _kill_blocks() -> bool:
    try:
        from saathi.inference.provider_policy import is_master_killed, is_provider_killed

        return is_master_killed() or is_provider_killed("ollama")
    except Exception:
        return False


def _provider_decision_gate(prompt: str, system: str, max_tokens: int) -> dict[str, Any] | None:
    """Run M21.2 provider decision; return error dict if blocked, else None."""
    try:
        from saathi.inference.provider_decision import decide_providers
        from saathi.inference.request import InferenceRequest
        from saathi.inference.caller_rollout import CALLER_CHEAP_ASK

        req = InferenceRequest(
            prompt=prompt,
            system=system,
            caller_component=CALLER_CHEAP_ASK,
            max_output_tokens=min(int(max_tokens or 512), 512),
            timeout_seconds=45.0,
            local_only=True,
            cloud_fallback_permitted=False,
            cloud_allowed=False,
            fallback_policy="none",
            max_retries=0,
        )
        dec = decide_providers(
            req,
            production_context=False,
            allow_cloud_fallback=False,
            master_inference_enabled=True,
        )
        if not dec.ok:
            return {
                "error": dec.explanation or dec.reason_code,
                "path_used": "provider_decision",
                "mode": "blocked",
                "reason_code": dec.reason_code,
                "selected_provider_id": dec.selected_provider_id or "",
            }
        # Never silently select cloud
        if dec.selected_provider_id:
            from saathi.inference.provider_descriptor import get_descriptor

            d = get_descriptor(dec.selected_provider_id)
            if d and d.local_or_cloud == "cloud":
                return {
                    "error": "cloud_provider_denied_for_cheap_ask",
                    "path_used": "provider_decision",
                    "mode": "blocked",
                    "reason_code": "cloud_denied",
                }
    except Exception:
        return None
    return None


def cheap_ask(prompt: str, system: str = "You are a helpful assistant.", max_tokens: int = 1024) -> dict:
    """Cheapest capable model for routine work (captions, summaries, rewrites).

    Routes SCREENING + COST via Model Router / M20.3 compat adoption.
    M21.2: no direct provider proxy bypass; kill switches and provider
    decision apply before network attempts on the governed branch.
    """
    if _kill_blocks() and os.getenv("SAATHI_CHEAP_ASK_RESPECT_KILL", "1").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        # Kill still blocks governed path; legacy generate may continue unless
        # master kill is intended to mean all inference — document both.
        # When KILL_ALL is set, fail closed for cheap_ask entirely.
        try:
            from saathi.inference.provider_policy import is_master_killed

            if is_master_killed():
                return {
                    "error": "SAATHI_INFERENCE_KILL_ALL is active",
                    "path_used": "kill_switch",
                    "mode": "blocked",
                    "reason_code": "kill_switch_active",
                }
        except Exception:
            pass

    gate = _provider_decision_gate(prompt, system, max_tokens)
    # Only hard-block when decision explicitly kill/privacy/unknown; allow legacy
    # when providers simply degraded (offline ollama) so public API keeps working.
    if gate and gate.get("reason_code") in {
        "kill_switch_active",
        "unknown_caller",
        "cloud_denied",
        "privacy_mismatch",
        "privacy_cloud_denied",
    }:
        return gate

    try:
        from saathi.inference.compat import cheap_ask_adopted
        from ..llm import generate
        from ..model_router import ModelLabel, Prefer

        def _legacy(**kwargs):
            return generate(
                kwargs.get("label", ModelLabel.SCREENING),
                kwargs["prompt"],
                system=kwargs.get("system", system),
                prefer=kwargs.get("prefer", Prefer.COST),
                max_tokens=min(int(kwargs.get("max_tokens") or max_tokens), 512),
                timeout=int(kwargs.get("timeout") or 60),
            )

        out = cheap_ask_adopted(
            prompt, system=system, max_tokens=max_tokens, legacy_fn=_legacy,
        )
        if "error" in out and out.get("path_used") in (
            "governed_local", "governed_local_then_legacy",
        ) and out.get("mode") == "governed_local_only":
            return out
        if "reply" in out:
            return out
        if out.get("mode") and out.get("mode") != "legacy":
            if out.get("path_used") != "legacy":
                return out
    except Exception:
        pass

    try:
        from ..llm import generate
        from ..model_router import ModelLabel, Prefer
        res = generate(ModelLabel.SCREENING, prompt, system,
                       prefer=Prefer.COST, max_tokens=max_tokens, timeout=60)
        return {"reply": res.text, "model": res.provider, "cost": "cheapest-available",
                "path_used": "legacy", "mode": "legacy"}
    except Exception as e:
        # M21.2: historical direct CHEAP_PROXY httpx path removed (was DIRECT_PROVIDER_BYPASS).
        # Explicit compatibility residual: no network proxy; return structured error.
        return {
            "error": f"legacy_paths_failed:{type(e).__name__}",
            "path_used": "legacy_exhausted",
            "mode": "legacy",
            "reason_code": "no_ungoverned_proxy",
            "note": "M21.2 blocked direct cheap proxy; use governed/local or legacy generate",
        }


def cheap_proxy_status() -> dict:
    """Historical proxy status helper (read-only). Direct proxy invoke remains blocked."""
    import httpx

    try:
        r = httpx.get(f"{config.CHEAP_PROXY_URL}/healthz", timeout=3)
        st = {"status": "running", "url": config.CHEAP_PROXY_URL} if r.text == "ok" else {"status": "error"}
    except Exception as e:
        st = {
            "status": "offline",
            "error": str(e),
            "fix": "Run: cd ~/SaathiAI && ./anthropic-proxy .proxy.env",
        }
    st["direct_proxy_invoke"] = "blocked_m21_2"
    st["cheap_ask_path"] = "compat_or_legacy_generate_only"
    return st
