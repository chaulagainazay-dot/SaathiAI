"""M29 — Connector trust model.

Trust is registry-owned. Callers cannot raise trust, lower approval floors,
or expand rollout eligibility.
"""
from __future__ import annotations

from enum import Enum
from typing import Iterable

from saathi.connectors.registry.capabilities import ConnectorCapability


class TrustLevel(str, Enum):
    INTERNAL = "INTERNAL"
    LOCAL_SYSTEM = "LOCAL_SYSTEM"
    LOCAL_SERVICE = "LOCAL_SERVICE"
    LOCAL_NETWORK = "LOCAL_NETWORK"
    EXTERNAL_SERVICE = "EXTERNAL_SERVICE"
    PRIVILEGED = "PRIVILEGED"
    PROHIBITED = "PROHIBITED"


# Lower index = more constrained / safer surface (except PROHIBITED which is terminal deny).
TRUST_ORDER: tuple[TrustLevel, ...] = (
    TrustLevel.INTERNAL,
    TrustLevel.LOCAL_SYSTEM,
    TrustLevel.LOCAL_SERVICE,
    TrustLevel.LOCAL_NETWORK,
    TrustLevel.EXTERNAL_SERVICE,
    TrustLevel.PRIVILEGED,
    TrustLevel.PROHIBITED,
)

_TRUST_RANK = {t: i for i, t in enumerate(TRUST_ORDER)}

# Maximum capability set per trust level (capabilities cannot exceed trust).
_TRUST_CAPABILITY_CEILING: dict[TrustLevel, frozenset[ConnectorCapability]] = {
    TrustLevel.INTERNAL: frozenset({
        ConnectorCapability.READ,
        ConnectorCapability.WRITE,
        ConnectorCapability.EXECUTE,
        ConnectorCapability.LOCAL_TOOL,
        ConnectorCapability.FILESYSTEM,
        ConnectorCapability.HTTP,  # loopback only — policy still constrains
        ConnectorCapability.MCP,
        ConnectorCapability.BROWSER,
    }),
    TrustLevel.LOCAL_SYSTEM: frozenset({
        ConnectorCapability.READ,
        ConnectorCapability.WRITE,
        ConnectorCapability.EXECUTE,
        ConnectorCapability.LOCAL_TOOL,
        ConnectorCapability.FILESYSTEM,
        ConnectorCapability.HTTP,
    }),
    TrustLevel.LOCAL_SERVICE: frozenset({
        ConnectorCapability.READ,
        ConnectorCapability.WRITE,
        ConnectorCapability.EXECUTE,
        ConnectorCapability.LOCAL_TOOL,
        ConnectorCapability.HTTP,
        ConnectorCapability.MCP,
    }),
    TrustLevel.LOCAL_NETWORK: frozenset({
        ConnectorCapability.READ,
        ConnectorCapability.WRITE,
        ConnectorCapability.HTTP,
        ConnectorCapability.MCP,
        ConnectorCapability.BROWSER,
        ConnectorCapability.COMMUNICATE,
    }),
    TrustLevel.EXTERNAL_SERVICE: frozenset({
        ConnectorCapability.READ,
        ConnectorCapability.WRITE,
        ConnectorCapability.HTTP,
        ConnectorCapability.MCP,
        ConnectorCapability.BROWSER,
        ConnectorCapability.COMMUNICATE,
        ConnectorCapability.ACCOUNT,
    }),
    TrustLevel.PRIVILEGED: frozenset(set(ConnectorCapability)),  # all, still policy-gated
    TrustLevel.PROHIBITED: frozenset(),  # none allowed
}

# Approval floor labels (maps to ExecutionGateway / runtime expectations)
_APPROVAL_FLOOR: dict[TrustLevel, str] = {
    TrustLevel.INTERNAL: "L1",
    TrustLevel.LOCAL_SYSTEM: "L1",
    TrustLevel.LOCAL_SERVICE: "L1",
    TrustLevel.LOCAL_NETWORK: "L2",
    TrustLevel.EXTERNAL_SERVICE: "L2",
    TrustLevel.PRIVILEGED: "L4",
    TrustLevel.PROHIBITED: "DENIED",
}

# Rollout modes the trust level may ever enter (still requires mode set + cert for ACTIVE)
_ROLLOUT_ELIGIBILITY: dict[TrustLevel, frozenset[str]] = {
    TrustLevel.INTERNAL: frozenset({"OFF", "SHADOW", "CANARY", "ACTIVE", "DRAINING"}),
    TrustLevel.LOCAL_SYSTEM: frozenset({"OFF", "SHADOW", "CANARY", "ACTIVE", "DRAINING"}),
    TrustLevel.LOCAL_SERVICE: frozenset({"OFF", "SHADOW", "CANARY", "ACTIVE", "DRAINING"}),
    TrustLevel.LOCAL_NETWORK: frozenset({"OFF", "SHADOW", "CANARY", "ACTIVE", "DRAINING"}),
    TrustLevel.EXTERNAL_SERVICE: frozenset({"OFF", "SHADOW", "CANARY", "ACTIVE", "DRAINING"}),
    TrustLevel.PRIVILEGED: frozenset({"OFF", "SHADOW", "CANARY", "DRAINING"}),  # no ACTIVE without reclass
    TrustLevel.PROHIBITED: frozenset({"OFF"}),
}


def parse_trust_level(value: str | TrustLevel | None) -> TrustLevel:
    if value is None or value == "":
        return TrustLevel.INTERNAL
    if isinstance(value, TrustLevel):
        return value
    try:
        return TrustLevel(str(value).strip().upper())
    except ValueError as e:
        raise ValueError(f"invalid_trust_level:{value}") from e


def trust_rank(level: TrustLevel | str) -> int:
    t = parse_trust_level(level)
    return _TRUST_RANK[t]


def capabilities_allowed_for_trust(level: TrustLevel | str) -> frozenset[ConnectorCapability]:
    t = parse_trust_level(level)
    return _TRUST_CAPABILITY_CEILING[t]


def approval_floor_for_trust(level: TrustLevel | str) -> str:
    t = parse_trust_level(level)
    return _APPROVAL_FLOOR[t]


def rollout_eligible_for_trust(level: TrustLevel | str) -> frozenset[str]:
    t = parse_trust_level(level)
    return _ROLLOUT_ELIGIBILITY[t]


def enforce_capabilities_for_trust(
    level: TrustLevel | str,
    capabilities: Iterable[str | ConnectorCapability],
) -> list[str]:
    """Return list of capability names that exceed the trust ceiling (empty = ok)."""
    allowed = capabilities_allowed_for_trust(level)
    violations: list[str] = []
    for c in capabilities:
        try:
            cap = c if isinstance(c, ConnectorCapability) else ConnectorCapability(str(c).upper())
        except ValueError:
            violations.append(str(c))
            continue
        if cap not in allowed:
            violations.append(cap.value)
    return violations


def trust_summary() -> dict[str, dict]:
    return {
        t.value: {
            "approval_floor": _APPROVAL_FLOOR[t],
            "rollout_eligible": sorted(_ROLLOUT_ELIGIBILITY[t]),
            "capability_ceiling": sorted(c.value for c in _TRUST_CAPABILITY_CEILING[t]),
        }
        for t in TrustLevel
    }
