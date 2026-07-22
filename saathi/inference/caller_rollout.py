"""M20.3 — Opt-in rollout modes for selected LLM callers.

Reuses SaathiOS env conventions (same pattern as Knowledge Service rollout).
Default for every caller remains ``legacy`` — no global chat migration.
"""
from __future__ import annotations

import os
import threading
from enum import Enum
from typing import Optional


class InfRolloutMode(str, Enum):
    LEGACY = "legacy"
    SHADOW = "shadow"
    GOVERNED_LOCAL_WITH_FALLBACK = "governed_local_with_fallback"
    GOVERNED_LOCAL_ONLY = "governed_local_only"


VALID_MODES = frozenset(m.value for m in InfRolloutMode)

ENV_GLOBAL = "SAATHI_INF_ROLLOUT"
ENV_CALLER_PREFIX = "SAATHI_INF_ROLLOUT_"

# Selected M20.3 callers (≤2)
CALLER_CHEAP_ASK = "cheap_ask"
CALLER_PROSE_CLEAN = "prose_clean"

SELECTED_CALLERS = frozenset({CALLER_CHEAP_ASK, CALLER_PROSE_CLEAN})

# Must never be auto-promoted
PROMOTION_FORBIDDEN = frozenset({
    "chat_default",
    "chat_ltm",
    "voice_turn",
    "trading_guardian",
    "payment",
    "auth_decision",
    "kill_switch",
    "deployment_authorization",
    "browser_dispatch",
    "ielts_stream",
    "ask_llm_hub",
})

# Soft errors: may fall back under governed_local_with_fallback
FALLBACK_ALLOWED = frozenset({
    "engine_unavailable",
    "model_unavailable",
    "timeout",
    "provider_unavailable",
    "malformed_provider_response",
    "concurrency_limit",
    "no_suitable_model",
    "hardware_policy_denied",  # operational on 8GB — treat as soft for pilot
    "router_failed",
    "internal_inference_error",
    "inference_disabled",  # when trying governed path but flags off → soft for with_fallback
    "gateway_path_disabled",
})

# Hard denials: never fall back
FALLBACK_DENIED = frozenset({
    "capability_denied",
    "security_policy_denied",
    "prompt_too_large",
    "output_limit_invalid",
    "streaming_unsupported",
    "cloud_fallback_denied",
    "invalid_request",
    "sensitivity_restriction",
})

_lock = threading.RLock()
_runtime_overrides: dict[str, InfRolloutMode] = {}
_global_override: InfRolloutMode | None = None


def _parse_mode(raw: str | None) -> InfRolloutMode | None:
    if raw is None:
        return None
    v = str(raw).strip().lower()
    if not v:
        return None
    if v not in VALID_MODES:
        return None
    return InfRolloutMode(v)


def set_runtime_mode(caller: str, mode: InfRolloutMode | str | None) -> None:
    """Test/operator override (process-local)."""
    with _lock:
        if mode is None:
            _runtime_overrides.pop(caller, None)
            return
        m = mode if isinstance(mode, InfRolloutMode) else _parse_mode(str(mode))
        if m is None:
            raise ValueError(f"invalid_mode:{mode}")
        if caller in PROMOTION_FORBIDDEN:
            raise ValueError(f"promotion_forbidden:{caller}")
        _runtime_overrides[caller] = m


def set_global_runtime_mode(mode: InfRolloutMode | str | None) -> None:
    global _global_override
    with _lock:
        if mode is None:
            _global_override = None
            return
        m = mode if isinstance(mode, InfRolloutMode) else _parse_mode(str(mode))
        if m is None:
            raise ValueError(f"invalid_mode:{mode}")
        _global_override = m


def clear_runtime_overrides() -> None:
    global _global_override
    with _lock:
        _runtime_overrides.clear()
        _global_override = None


def resolve_mode(caller: str) -> InfRolloutMode:
    """Resolve rollout mode. Default always legacy for unknown and selected callers."""
    if caller in PROMOTION_FORBIDDEN:
        return InfRolloutMode.LEGACY

    with _lock:
        if caller in _runtime_overrides:
            return _runtime_overrides[caller]
        if _global_override is not None and caller in SELECTED_CALLERS:
            return _global_override

    env_caller = os.getenv(f"{ENV_CALLER_PREFIX}{caller.upper()}")
    m = _parse_mode(env_caller)
    if m is not None:
        return m

    m = _parse_mode(os.getenv(ENV_GLOBAL))
    if m is not None and caller in SELECTED_CALLERS:
        return m

    return InfRolloutMode.LEGACY


def can_fallback(error_category: str | None) -> bool:
    if not error_category:
        return False
    cat = str(error_category).strip().lower()
    if cat in FALLBACK_DENIED:
        return False
    if cat in FALLBACK_ALLOWED:
        return True
    # unknown → fail closed (no fallback)
    return False


def rollout_snapshot() -> dict:
    return {
        "global_env": ENV_GLOBAL,
        "caller_prefix": ENV_CALLER_PREFIX,
        "selected_callers": sorted(SELECTED_CALLERS),
        "default_mode": InfRolloutMode.LEGACY.value,
        "modes": sorted(VALID_MODES),
        "forbidden": sorted(PROMOTION_FORBIDDEN),
        "resolved": {c: resolve_mode(c).value for c in sorted(SELECTED_CALLERS)},
    }
