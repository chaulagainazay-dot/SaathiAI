"""Connector Registry — external services as uniform, provider-agnostic drivers.

Departments call `registry.execute(capability=..., **payload)`; they never import
an SDK. Drivers (the only SDK-aware code) live in `drivers/`.

See HOW_TO_ADD_A_CONNECTOR.md to add a new integration in one place.
"""
from .base import (
    Connector, Health, Status, ConnectorEvent,
    ConnectorError, AuthRequired, RateLimited, CapabilityUnsupported,
)
from .manifest import Manifest, ConnectorMetadata
from .registry import ConnectorRegistry, registry
from .drivers import (
    TelegramConnector, GitHubConnector, N8nConnector,
    BrowserConnector, YouTubeConnector, FilesystemConnector,
)
from . import diagnostics

# Drivers registered by default. Filesystem/Browser need no external creds; the
# rest self-report AUTH_REQUIRED until their env keys are set.
_DEFAULT_DRIVER_CLASSES = (
    TelegramConnector, GitHubConnector, N8nConnector,
    BrowserConnector, YouTubeConnector, FilesystemConnector,
)


def install_defaults(reg: ConnectorRegistry | None = None, *, bus=None) -> ConnectorRegistry:
    """Register the built-in reference connectors (env-configured)."""
    reg = reg or registry
    if bus is not None:
        reg._bus = bus
    for cls in _DEFAULT_DRIVER_CLASSES:
        reg.register(cls())
    return reg


__all__ = [
    "Connector", "Manifest", "ConnectorMetadata", "Health", "Status", "ConnectorEvent",
    "ConnectorError", "AuthRequired", "RateLimited", "CapabilityUnsupported",
    "ConnectorRegistry", "registry", "diagnostics", "install_defaults",
    "TelegramConnector", "GitHubConnector", "N8nConnector",
    "BrowserConnector", "YouTubeConnector", "FilesystemConnector",
]
