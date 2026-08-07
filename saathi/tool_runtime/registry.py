"""M49.1 canonical tool registry — code-owned, fail-closed registration."""
from __future__ import annotations

import threading
from typing import Optional

from saathi.tool_runtime.contracts import (
    ToolAdapterFn,
    ToolAvailability,
    ToolManifest,
    validate_manifest,
)


class ToolRegistryError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class ToolRegistry:
    """In-process registry. User input cannot register tools."""

    def __init__(self, *, allow_dynamic: bool = False):
        self._lock = threading.RLock()
        self._manifests: dict[str, ToolManifest] = {}  # tool_id@version
        self._by_id: dict[str, str] = {}  # tool_id → latest key
        self._adapters: dict[str, ToolAdapterFn] = {}
        self.allow_dynamic = allow_dynamic
        self._sealed = False

    def seal(self) -> None:
        """Prevent further registration (production default after bootstrap)."""
        with self._lock:
            self._sealed = True

    def register(
        self,
        manifest: ToolManifest,
        adapter: ToolAdapterFn,
        *,
        trusted: bool = True,
    ) -> str:
        if not trusted and not self.allow_dynamic:
            raise ToolRegistryError(
                "TOOL_REGISTRY_ERROR",
                "dynamic/plugin registration disabled by default",
            )
        with self._lock:
            if self._sealed and not trusted:
                raise ToolRegistryError(
                    "TOOL_REGISTRY_ERROR", "registry sealed"
                )
            errs = validate_manifest(manifest)
            if errs:
                raise ToolRegistryError(
                    "TOOL_MANIFEST_INVALID", "; ".join(errs)
                )
            if adapter is None or not callable(adapter):
                raise ToolRegistryError(
                    "TOOL_REGISTRY_ERROR", "adapter required"
                )
            key = manifest.key()
            if key in self._manifests:
                raise ToolRegistryError(
                    "TOOL_REGISTRY_ERROR",
                    f"duplicate registration: {key}",
                )
            self._manifests[key] = manifest
            # latest version pointer
            self._by_id[manifest.tool_id] = key
            self._adapters[key] = adapter
            return key

    def resolve(
        self, tool_id: str, version: str = ""
    ) -> tuple[ToolManifest, ToolAdapterFn] | None:
        with self._lock:
            if version:
                key = f"{tool_id}@{version}"
            else:
                key = self._by_id.get(tool_id)
            if not key:
                return None
            m = self._manifests.get(key)
            a = self._adapters.get(key)
            if not m or not a:
                return None
            return m, a

    def get_manifest(self, tool_id: str, version: str = "") -> ToolManifest | None:
        r = self.resolve(tool_id, version)
        return r[0] if r else None

    def list_manifests(self, *, include_disabled: bool = False) -> list[ToolManifest]:
        with self._lock:
            out = []
            for m in self._manifests.values():
                if not include_disabled and (
                    not m.enabled or m.availability == ToolAvailability.DISABLED
                ):
                    continue
                out.append(m)
            return sorted(out, key=lambda x: x.tool_id)

    def capability_matrix(self) -> list[dict]:
        return [
            {
                "tool_id": m.tool_id,
                "version": m.version,
                "capabilities": list(m.capabilities),
                "authority_class": m.authority_class.value,
                "side_effect_class": m.side_effect_class.value,
                "approval": m.approval_requirement.value,
                "cancellation": m.cancellation_support.value,
                "enabled": m.enabled,
            }
            for m in self.list_manifests(include_disabled=True)
        ]

    def validate_all(self) -> dict:
        with self._lock:
            issues = []
            for key, m in self._manifests.items():
                errs = validate_manifest(m)
                if errs:
                    issues.append({"key": key, "errors": errs})
                if key not in self._adapters:
                    issues.append({"key": key, "errors": ["missing adapter"]})
            return {
                "ok": not issues,
                "count": len(self._manifests),
                "issues": issues,
            }


_DEFAULT: ToolRegistry | None = None
_BOOTSTRAPPED = False


def default_registry() -> ToolRegistry:
    global _DEFAULT, _BOOTSTRAPPED
    if _DEFAULT is None:
        _DEFAULT = ToolRegistry(allow_dynamic=False)
    if not _BOOTSTRAPPED:
        from saathi.tool_runtime.bootstrap import register_builtins

        register_builtins(_DEFAULT)
        _BOOTSTRAPPED = True
    return _DEFAULT


def reset_registry_for_tests() -> ToolRegistry:
    """Test-only: clear and re-bootstrap."""
    global _DEFAULT, _BOOTSTRAPPED
    _DEFAULT = ToolRegistry(allow_dynamic=False)
    _BOOTSTRAPPED = False
    return default_registry()
