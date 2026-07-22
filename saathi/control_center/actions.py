"""M16 unified action model — one frontend-safe action descriptor.

Describes what an action IS and which canonical API executes it. The Control
Center never executes; it renders descriptors and calls the canonical subsystem
API (which enforces auth/approval/gateway). Descriptors carry the risk, approval
requirement, and the exact canonical endpoint so no component reimplements
behavior.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ActionClass(str, Enum):
    NAV = "read_only_navigation"
    SAFE_LOCAL = "safe_local_action"
    APPROVAL_GATED = "approval_gated_mutation"
    EXTERNAL_SIDE_EFFECT = "external_side_effect"
    MANUAL_ONLY = "manual_only_action"


@dataclass
class ActionDescriptor:
    action_id: str
    subsystem: str
    operation: str
    label: str
    action_class: ActionClass
    canonical_api: str               # the ONLY path that executes it
    required_permission: str = "owner"
    risk: int = 0
    requires_approval: bool = False
    requires_confirmation: bool = False
    available: bool = True
    disabled_reason: str = ""

    def to_dict(self) -> dict:
        d = {k: getattr(self, k) for k in self.__dataclass_fields__}
        d["action_class"] = self.action_class.value
        return d


# canonical action catalog. The Control Center UI renders these; execution ALWAYS
# posts to canonical_api (never a Control Center mutation endpoint).
CATALOG: dict[str, ActionDescriptor] = {
    "approval.approve": ActionDescriptor(
        "approval.approve", "connectors", "resolve_approval", "Approve exact action",
        ActionClass.APPROVAL_GATED, "/api/v1/connectors/approvals/{aid}/decide?approved=true",
        risk=3, requires_confirmation=True),
    "approval.deny": ActionDescriptor(
        "approval.deny", "connectors", "resolve_approval", "Deny",
        ActionClass.SAFE_LOCAL, "/api/v1/connectors/approvals/{aid}/decide?approved=false"),
    "connector.execute": ActionDescriptor(
        "connector.execute", "connectors", "execute", "Run connector operation",
        ActionClass.APPROVAL_GATED, "/api/v1/connectors/executions", risk=3,
        requires_approval=True),
    "redteam.run": ActionDescriptor(
        "redteam.run", "security", "run", "Run deterministic red-team suite",
        ActionClass.SAFE_LOCAL, "/api/v1/security/redteam/run"),
    "connector.disconnect": ActionDescriptor(
        "connector.disconnect", "connectors", "disconnect", "Disconnect account",
        ActionClass.SAFE_LOCAL, "/api/v1/connectors/accounts/{aid}",
        requires_confirmation=True),
}


def catalog() -> list[dict]:
    return [a.to_dict() for a in CATALOG.values()]


def descriptor(action_id: str) -> dict | None:
    a = CATALOG.get(action_id)
    return a.to_dict() if a else None
