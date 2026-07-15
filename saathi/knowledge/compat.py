"""M18.2 / M19.1 compatibility: legacy search shape with optional unified route.

Temporary adapter layer — provenance and truncation must not be lost.
Does not duplicate retrieval; routes through adoption gateway.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from saathi.knowledge.rollout import CALLER_COMPAT_SEARCH, RolloutMode


def search_compatible(
    query: str,
    *,
    project_root: str | Path | None = None,
    top_k: int = 10,
    use_unified: bool = False,
    shadow: bool = False,
    mode: str | RolloutMode | None = None,
    **legacy_kwargs: Any,
) -> dict:
    """Preserve M18.2-style dict response with M19.1 rollout modes.

    Precedence for mode:
      explicit `mode` >
      shadow=True → shadow >
      use_unified=True → unified_with_fallback >
      default resolve (legacy unless env/runtime set)
    """
    from saathi.knowledge.adoption import adopted_codebase_search

    resolved_mode = mode
    if resolved_mode is None:
        if shadow:
            resolved_mode = RolloutMode.SHADOW
        elif use_unified:
            resolved_mode = RolloutMode.UNIFIED_WITH_FALLBACK

    out = adopted_codebase_search(
        query,
        project_root=project_root,
        top_k=top_k,
        mode=resolved_mode,
        caller_id=CALLER_COMPAT_SEARCH,
        **legacy_kwargs,
    )
    # Ensure legacy keys always present
    out.setdefault("hits", [])
    out.setdefault("ok", True)
    out.setdefault("legacy_compatible", True)
    return out
