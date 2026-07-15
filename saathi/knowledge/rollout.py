"""M19.1 — Knowledge Service adoption rollout modes and configuration.

Reuses existing SAATHI_* environment conventions. Does not introduce a new
feature-flag platform.

Modes:
  legacy                 — M18.2 / legacy path only (global default)
  shadow                 — legacy authoritative; KS runs for metrics only
  unified_with_fallback  — KS first; governed fallback to legacy on soft errors
  unified_only           — KS only (no legacy fallback)
"""
from __future__ import annotations

import os
import threading
from enum import Enum
from typing import Optional


class RolloutMode(str, Enum):
    LEGACY = "legacy"
    SHADOW = "shadow"
    UNIFIED_WITH_FALLBACK = "unified_with_fallback"
    UNIFIED_ONLY = "unified_only"


VALID_MODES = frozenset(m.value for m in RolloutMode)

# Global default remains conservative for M19.1
ENV_GLOBAL = "SAATHI_KS_ROLLOUT"
# Per-caller: SAATHI_KS_ROLLOUT_CODEBASE_MEMORY_SEARCH=shadow
ENV_CALLER_PREFIX = "SAATHI_KS_ROLLOUT_"

# Known first-wave caller keys
CALLER_CODEBASE_MEMORY_SEARCH = "codebase_memory_search"
CALLER_CODEBASE_MEMORY_SYMBOL = "codebase_memory_symbol"
CALLER_CODEBASE_MEMORY_DOCUMENT = "codebase_memory_document"
CALLER_CODEBASE_MEMORY_EXPLAIN = "codebase_memory_explain"
CALLER_COMPAT_SEARCH = "compat_search"
CALLER_MISSION_CONTEXT = "mission_context_prepare"
CALLER_AUDIT_EVIDENCE = "audit_evidence_lookup"

FIRST_WAVE_CALLERS = frozenset({
    CALLER_CODEBASE_MEMORY_SEARCH,
    CALLER_CODEBASE_MEMORY_SYMBOL,
    CALLER_CODEBASE_MEMORY_DOCUMENT,
    CALLER_CODEBASE_MEMORY_EXPLAIN,
    CALLER_COMPAT_SEARCH,
    CALLER_MISSION_CONTEXT,
    CALLER_AUDIT_EVIDENCE,
})

_lock = threading.RLock()
_runtime_overrides: dict[str, RolloutMode] = {}
_global_override: RolloutMode | None = None


def _parse_mode(raw: str | None) -> RolloutMode | None:
    if raw is None:
        return None
    v = str(raw).strip().lower()
    if not v:
        return None
    if v in VALID_MODES:
        return RolloutMode(v)
    return None


def set_global_mode(mode: RolloutMode | str | None) -> None:
    """Runtime override (tests / Control Center). None clears override."""
    global _global_override
    with _lock:
        if mode is None:
            _global_override = None
        else:
            m = mode if isinstance(mode, RolloutMode) else _parse_mode(str(mode))
            if m is None:
                raise ValueError(f"invalid_rollout_mode:{mode}")
            _global_override = m


def set_caller_mode(caller_id: str, mode: RolloutMode | str | None) -> None:
    """Per-caller runtime override. None clears that caller override."""
    key = (caller_id or "").strip().lower()
    with _lock:
        if mode is None:
            _runtime_overrides.pop(key, None)
            return
        m = mode if isinstance(mode, RolloutMode) else _parse_mode(str(mode))
        if m is None:
            raise ValueError(f"invalid_rollout_mode:{mode}")
        _runtime_overrides[key] = m


def reset_rollout_state() -> None:
    """Test helper: clear all runtime overrides."""
    global _global_override
    with _lock:
        _runtime_overrides.clear()
        _global_override = None


def resolve_mode(caller_id: str, *, explicit: RolloutMode | str | None = None) -> RolloutMode:
    """Resolve rollout mode: explicit > runtime caller > env caller > runtime global > env global > legacy."""
    if explicit is not None:
        m = explicit if isinstance(explicit, RolloutMode) else _parse_mode(str(explicit))
        if m is not None:
            return m

    key = (caller_id or "").strip().lower()
    with _lock:
        if key in _runtime_overrides:
            return _runtime_overrides[key]
        if _global_override is not None:
            # env per-caller still wins over global runtime if set
            pass

    env_key = ENV_CALLER_PREFIX + key.upper().replace("-", "_")
    m = _parse_mode(os.getenv(env_key))
    if m is not None:
        return m

    with _lock:
        if _global_override is not None:
            return _global_override

    m = _parse_mode(os.getenv(ENV_GLOBAL))
    if m is not None:
        return m
    return RolloutMode.LEGACY


def rollout_snapshot() -> dict:
    """Non-sensitive snapshot for health / disable docs."""
    with _lock:
        overrides = {k: v.value for k, v in _runtime_overrides.items()}
        g = _global_override.value if _global_override else None
    return {
        "env_global": os.getenv(ENV_GLOBAL) or "",
        "runtime_global": g,
        "runtime_callers": overrides,
        "default": RolloutMode.LEGACY.value,
        "first_wave": sorted(FIRST_WAVE_CALLERS),
        "valid_modes": sorted(VALID_MODES),
    }
