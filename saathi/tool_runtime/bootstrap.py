"""Register M49.1–M49.3 tools into the canonical registry."""
from __future__ import annotations

from saathi.tool_runtime.adapters.builtins import builtin_manifests
from saathi.tool_runtime.adapters.m49_3 import m49_3_manifests
from saathi.tool_runtime.adapters.migrated import migrated_manifests
from saathi.tool_runtime.registry import ToolRegistry


def register_builtins(registry: ToolRegistry) -> list[str]:
    keys = []
    all_pairs = (
        list(builtin_manifests())
        + list(migrated_manifests())
        + list(m49_3_manifests())
    )
    for manifest, adapter in all_pairs:
        try:
            keys.append(registry.register(manifest, adapter, trusted=True))
        except Exception as exc:
            if "duplicate" not in str(exc).lower():
                raise
    return keys
