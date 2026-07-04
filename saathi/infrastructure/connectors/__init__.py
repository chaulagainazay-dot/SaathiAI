"""Connector Registry — external services as uniform, provider-agnostic drivers.

Departments call `registry.execute(capability=..., **payload)`; they never import
an SDK. Reference connectors: Telegram, GitHub (more via the same contract).
"""
from .base import (
    Connector, ConnectorMetadata, Health, Status, ConnectorEvent,
    ConnectorError, AuthRequired, RateLimited, CapabilityUnsupported,
)
from .registry import ConnectorRegistry, registry
from .telegram import TelegramConnector
from .github import GitHubConnector
from . import diagnostics


def install_defaults(reg: ConnectorRegistry | None = None, *, bus=None) -> ConnectorRegistry:
    """Register the built-in reference connectors (env-configured)."""
    reg = reg or registry
    if bus is not None:
        reg._bus = bus
    reg.register(TelegramConnector())
    reg.register(GitHubConnector())
    return reg


__all__ = [
    "Connector", "ConnectorMetadata", "Health", "Status", "ConnectorEvent",
    "ConnectorError", "AuthRequired", "RateLimited", "CapabilityUnsupported",
    "ConnectorRegistry", "registry", "TelegramConnector", "GitHubConnector",
    "diagnostics", "install_defaults",
]
