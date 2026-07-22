"""M32 — Provider identity registry (canonical resolution; fail closed).

Provider identity extends the M29 manifest/registry model: a provider is bound to
a canonical connector_id. Authority is never derived from a display name. Unknown
provider identity fails closed. Aliases resolve through ONE canonical mapping.
Financial/trading providers can never be registered or resolved.
"""
from __future__ import annotations

import threading
from typing import Optional

from saathi.connectors.providers.models import (
    DataClassification,
    ProviderIdentity,
    ProviderSideEffectClass,
    M32_PERMITTED_SIDE_EFFECTS,
    provider_is_prohibited,
)


class ProviderRegistryError(ValueError):
    pass


# Canonical alias → provider_id (single source of truth)
_CANONICAL_ALIASES: dict[str, str] = {
    "echo": "saathi.echo.v1",
    "saathi.echo": "saathi.echo.v1",
    "simulator": "saathi.echo.v1",
}


def _builtin_identities() -> dict[str, ProviderIdentity]:
    return {
        "saathi.echo.v1": ProviderIdentity(
            provider_id="saathi.echo.v1",
            provider_version="1.0.0",
            adapter_version="1.0.0",
            connector_id="gov.http",
            transport="local_simulator",
            base_endpoint_class="inprocess",
            environment="test",
            auth_profile="none",
            capabilities=("echo", "read_item", "list_items", "health"),
            side_effect_class=ProviderSideEffectClass.READ_ONLY.value,
            rate_limit_profile="default",
            data_classification=DataClassification.PUBLIC.value,
            display_name="Saathi Echo (deterministic simulator)",
        ),
    }


class ProviderRegistry:
    """Resolve-only provider identity registry. No runtime authority."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._identities: dict[str, ProviderIdentity] = _builtin_identities()
        self._aliases: dict[str, str] = dict(_CANONICAL_ALIASES)

    def register(self, identity: ProviderIdentity) -> None:
        """Register a provider identity. Rejects prohibited providers fail-closed."""
        reason = provider_is_prohibited(identity.provider_id, capabilities=identity.capabilities)
        if reason:
            raise ProviderRegistryError(f"prohibited_provider:{reason}")
        try:
            sec = ProviderSideEffectClass(identity.side_effect_class)
        except ValueError:
            raise ProviderRegistryError(f"unknown_side_effect_class:{identity.side_effect_class}")
        if sec not in M32_PERMITTED_SIDE_EFFECTS:
            raise ProviderRegistryError(f"side_effect_not_permitted:{sec.value}")
        if not identity.connector_id:
            raise ProviderRegistryError("provider_missing_connector_id")
        with self._lock:
            self._identities[identity.provider_id] = identity

    def resolve(self, provider_ref: str) -> ProviderIdentity:
        """Resolve an id or alias to a canonical identity. Unknown → fail closed."""
        ref = (provider_ref or "").strip()
        if not ref:
            raise ProviderRegistryError("empty_provider_ref")
        # prohibited check applies even before lookup (defense in depth)
        reason = provider_is_prohibited(ref)
        if reason:
            raise ProviderRegistryError(f"prohibited_provider:{reason}")
        with self._lock:
            pid = self._aliases.get(ref.lower(), ref)
            ident = self._identities.get(pid)
        if ident is None:
            raise ProviderRegistryError(f"unknown_provider:{ref}")
        return ident

    def get(self, provider_id: str) -> Optional[ProviderIdentity]:
        with self._lock:
            return self._identities.get(provider_id)

    def list_ids(self) -> list[str]:
        with self._lock:
            return sorted(self._identities)

    def is_m32_safe(self, provider_ref: str) -> bool:
        """True only for explicitly M32-safe pilots (local/simulation, read-only)."""
        try:
            ident = self.resolve(provider_ref)
        except ProviderRegistryError:
            return False
        try:
            sec = ProviderSideEffectClass(ident.side_effect_class)
        except ValueError:
            return False
        return (
            sec in M32_PERMITTED_SIDE_EFFECTS
            and ident.transport in ("local_simulator", "inprocess")
            and ident.environment in ("test", "sandbox", "local", "dev")
            and ident.auth_profile in ("none", "public", "sandbox_none")
        )


_GLOBAL: Optional[ProviderRegistry] = None
_GLOBAL_LOCK = threading.Lock()


def get_provider_registry() -> ProviderRegistry:
    global _GLOBAL
    with _GLOBAL_LOCK:
        if _GLOBAL is None:
            _GLOBAL = ProviderRegistry()
        return _GLOBAL


def reset_provider_registry() -> None:
    global _GLOBAL
    with _GLOBAL_LOCK:
        _GLOBAL = None
