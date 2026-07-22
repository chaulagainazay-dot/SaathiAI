"""M29 — Explicit connector capability classes.

Distinct from operation names (get/post/health). Capabilities declare the
class of power a connector may exercise; trust ceilings bound them.
"""
from __future__ import annotations

from enum import Enum
from typing import Iterable


class ConnectorCapability(str, Enum):
    READ = "READ"
    WRITE = "WRITE"
    EXECUTE = "EXECUTE"
    COMMUNICATE = "COMMUNICATE"
    FILESYSTEM = "FILESYSTEM"
    BROWSER = "BROWSER"
    MCP = "MCP"
    HTTP = "HTTP"
    LOCAL_TOOL = "LOCAL_TOOL"
    ACCOUNT = "ACCOUNT"
    FINANCIAL = "FINANCIAL"


# Kind → default capability classes (when manifest omits capability_classes)
_KIND_DEFAULTS: dict[str, tuple[ConnectorCapability, ...]] = {
    "http": (ConnectorCapability.HTTP, ConnectorCapability.READ, ConnectorCapability.WRITE),
    "mcp": (ConnectorCapability.MCP, ConnectorCapability.READ),
    "browser": (ConnectorCapability.BROWSER, ConnectorCapability.READ),
    "local_tool": (ConnectorCapability.LOCAL_TOOL, ConnectorCapability.EXECUTE, ConnectorCapability.READ),
    "filesystem": (ConnectorCapability.FILESYSTEM, ConnectorCapability.READ, ConnectorCapability.WRITE),
    "cli": (ConnectorCapability.LOCAL_TOOL, ConnectorCapability.EXECUTE),
    "saas": (ConnectorCapability.HTTP, ConnectorCapability.ACCOUNT, ConnectorCapability.READ, ConnectorCapability.WRITE),
}


def parse_capability(value: str | ConnectorCapability) -> ConnectorCapability:
    if isinstance(value, ConnectorCapability):
        return value
    return ConnectorCapability(str(value).strip().upper())


def normalize_capability_classes(
    values: Iterable[str | ConnectorCapability] | None,
    *,
    kind: str = "http",
) -> tuple[ConnectorCapability, ...]:
    """Normalize capability_classes; if empty, derive from adapter kind."""
    if not values:
        return _KIND_DEFAULTS.get((kind or "http").lower(), (ConnectorCapability.READ,))
    out: list[ConnectorCapability] = []
    seen: set[ConnectorCapability] = set()
    for v in values:
        cap = parse_capability(v)
        if cap not in seen:
            seen.add(cap)
            out.append(cap)
    return tuple(out)


def capability_exceeds_trust(capability: str | ConnectorCapability, trust: str) -> bool:
    from saathi.connectors.registry.trust import capabilities_allowed_for_trust, parse_trust_level

    allowed = capabilities_allowed_for_trust(parse_trust_level(trust))
    try:
        cap = parse_capability(capability)
    except ValueError:
        return True
    return cap not in allowed
