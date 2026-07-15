"""M18.3/M18.4 — Governed InsForge provider pilot.

InsForge is an optional **product-backend data plane**. It must never act as
SaathiOS control plane, memory authority, scheduler, model router, or
Trading Guardian peer.

Disabled by default. Writes require SAATHI_INSFORGE_WRITES_ENABLED + approval
and ExecutionGateway (M18.4 migration pilot only).
Raw InsForge MCP is not exposed.
"""
from __future__ import annotations

from saathi.providers.insforge.config import InsForgeConfig, load_config
from saathi.providers.insforge.errors import InsForgeError, InsForgeErrorCategory
from saathi.providers.insforge.migration import MigrationService
from saathi.providers.insforge.provider import InsForgeProvider, default_provider

__all__ = [
    "InsForgeConfig",
    "InsForgeError",
    "InsForgeErrorCategory",
    "InsForgeProvider",
    "MigrationService",
    "default_provider",
    "load_config",
]
