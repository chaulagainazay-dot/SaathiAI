"""M32 — Canonical provider-adapter contract.

Every provider adapter implements this interface. The contract is deliberately
narrow: the adapter prepares, validates, executes, normalizes, classifies errors,
reports health, declares capabilities, and closes. It NEVER decides execution
authority, activates rollout, retrieves undeclared credentials, mutates connector
certification, or mutates provider verification.
"""
from __future__ import annotations

import abc
from typing import Any

from saathi.connectors.providers.config import ProviderConfig
from saathi.connectors.providers.models import (
    ProviderAdapterResult,
    ProviderExecutionContext,
    ProviderIdentity,
)

# Methods every conforming adapter must implement
REQUIRED_CONTRACT_METHODS: tuple[str, ...] = (
    "prepare",
    "validate_request",
    "execute",
    "normalize_response",
    "classify_error",
    "health",
    "capabilities",
    "close",
)

CONTRACT_VERSION = "m32.provider_contract.v1"


class ProviderAdapter(abc.ABC):
    """Bounded provider-adapter boundary. Authority lives outside the adapter."""

    #: canonical adapter version — verification fingerprint includes it
    adapter_version: str = "1.0.0"
    #: provider identity this adapter serves
    identity: ProviderIdentity

    @abc.abstractmethod
    def prepare(self, config: ProviderConfig) -> None:
        """Bind validated config. Must not fetch secrets or open live sessions."""

    @abc.abstractmethod
    def validate_request(self, ctx: ProviderExecutionContext) -> None:
        """Validate a normalized request; raise on injection/unsupported/oversize."""

    @abc.abstractmethod
    def execute(self, ctx: ProviderExecutionContext) -> ProviderAdapterResult:
        """Execute a bounded provider call and return a normalized result."""

    @abc.abstractmethod
    def normalize_response(self, raw: Any) -> dict[str, Any]:
        """Turn a raw provider response into safe, provider-neutral data."""

    @abc.abstractmethod
    def classify_error(self, exc: BaseException) -> str:
        """Map a raw error to a canonical ProviderErrorCode value."""

    @abc.abstractmethod
    def health(self) -> str:
        """Return a ProviderHealthState value (local probe; no authority)."""

    @abc.abstractmethod
    def capabilities(self) -> tuple[str, ...]:
        """Return the operations this adapter supports."""

    @abc.abstractmethod
    def close(self) -> None:
        """Release any adapter-local resources."""

    # ── Authority guards (final; adapters may not override) ──────────────────
    def determines_authority(self) -> bool:
        return False

    def can_activate_rollout(self) -> bool:
        return False


def adapter_satisfies_contract(adapter: Any) -> tuple[bool, list[str]]:
    """Return (ok, missing_methods). A conforming adapter implements every method."""
    missing: list[str] = []
    for name in REQUIRED_CONTRACT_METHODS:
        attr = getattr(adapter, name, None)
        if attr is None or not callable(attr):
            missing.append(name)
    return (len(missing) == 0, missing)
