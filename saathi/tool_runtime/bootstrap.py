"""Register M49.1 builtins + M49.2 migrated tools into the canonical registry."""
from __future__ import annotations

from saathi.tool_runtime.adapters.builtins import builtin_manifests
from saathi.tool_runtime.adapters.migrated import migrated_manifests
from saathi.tool_runtime.registry import ToolRegistry


def register_builtins(registry: ToolRegistry) -> list[str]:
    keys = []
    for manifest, adapter in list(builtin_manifests()) + list(migrated_manifests()):
        try:
            keys.append(registry.register(manifest, adapter, trusted=True))
        except Exception as exc:
            if "duplicate" not in str(exc).lower():
                raise
    return keys
