"""Register M49.1 builtin tools into the canonical registry."""
from __future__ import annotations

from saathi.tool_runtime.adapters.builtins import builtin_manifests
from saathi.tool_runtime.registry import ToolRegistry


def register_builtins(registry: ToolRegistry) -> list[str]:
    keys = []
    for manifest, adapter in builtin_manifests():
        # financial prohibited tool is intentionally registered for fail-closed tests
        try:
            keys.append(registry.register(manifest, adapter, trusted=True))
        except Exception as exc:
            if "duplicate" not in str(exc).lower():
                raise
    return keys
