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
    BrowserConnector, YouTubeConnector, FilesystemConnector, HumanPublishConnector,
)
from . import diagnostics

# Drivers registered by default. Filesystem/Browser need no external creds; the
# rest self-report AUTH_REQUIRED until their env keys are set.
_DEFAULT_DRIVER_CLASSES = (
    TelegramConnector, GitHubConnector, N8nConnector,
    BrowserConnector, YouTubeConnector, FilesystemConnector, HumanPublishConnector,
)


def install_defaults(reg: ConnectorRegistry | None = None, *, bus=None) -> ConnectorRegistry:
    """Register the built-in reference connectors (env-configured)."""
    reg = reg or registry
    if bus is not None:
        reg._bus = bus
    for cls in _DEFAULT_DRIVER_CLASSES:
        reg.register(cls())
    return reg


_default_ready = False


def default_registry() -> ConnectorRegistry:
    """The process-wide registry with default drivers installed once (lazy).
    Department code calls this: `default_registry().execute(capability=..., ...)`."""
    global _default_ready
    if not _default_ready:
        # wire the Event Fabric so connector events reach the platform
        try:
            from saathi.events import bus as _fabric
        except Exception:
            _fabric = None
        install_defaults(registry, bus=_fabric)
        _default_ready = True
    return registry


__all__ = [
    "Connector", "Manifest", "ConnectorMetadata", "Health", "Status", "ConnectorEvent",
    "ConnectorError", "AuthRequired", "RateLimited", "CapabilityUnsupported",
    "ConnectorRegistry", "registry", "diagnostics", "install_defaults", "default_registry",
    "TelegramConnector", "GitHubConnector", "N8nConnector",
    "BrowserConnector", "YouTubeConnector", "FilesystemConnector", "HumanPublishConnector",
]
