"""M20.4 — Bound approvals for supervised engineering agent launches.

Smallest compatible approval type; does not replace the platform Approval Engine.
Stores bound evidence in the engineering store under approvals.json.
"""
from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from saathi.engineering.store import EngineeringStore

APPROVAL_TYPE = "engineering_readonly_session"
DEFAULT_TTL_SEC = 3600.0


@dataclass
class EngineeringApproval:
    approval_id: str
    approval_type: str = APPROVAL_TYPE
    repository: str = ""
    branch: str = ""
    starting_commit: str = ""
    backlog_item_id: str = ""
    provider: str = "mock"
    mode: str = "readonly"  # readonly only for M20.4 pilot
    allowed_phases: list[str] = field(default_factory=list)
    timeout_sec: float = 1800.0
    prompt_fingerprint: str = ""
    validation_plan: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    expires_at: float = 0.0
    consumed: bool = False
    actor_id: str = "operator"
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.expires_at:
            self.expires_at = self.created_at + DEFAULT_TTL_SEC

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "EngineeringApproval":
        return cls(**{k: d[k] for k in cls.__dataclass_fields__ if k in d})  # type: ignore[arg-type]


def prompt_fingerprint(text: str) -> str:
    return "sha256:" + hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def create_readonly_approval(
    store: EngineeringStore,
    *,
    repository: str,
    branch: str,
    starting_commit: str,
    backlog_item_id: str,
    provider: str,
    prompt: str,
    validation_plan: Optional[list[str]] = None,
    timeout_sec: float = 1800.0,
    ttl_sec: float = DEFAULT_TTL_SEC,
    actor_id: str = "operator",
    allowed_phases: Optional[list[str]] = None,
) -> EngineeringApproval:
    now = time.time()
    appr = EngineeringApproval(
        approval_id=str(uuid.uuid4()),
        repository=repository,
        branch=branch,
        starting_commit=starting_commit,
        backlog_item_id=backlog_item_id,
        provider=provider,
        mode="readonly",
        allowed_phases=list(
            allowed_phases
            or [
                "intake_complete",
                "architecture_audit_complete",
                "implementation_plan_complete",
                "handoff_updated",
            ]
        ),
        timeout_sec=timeout_sec,
        prompt_fingerprint=prompt_fingerprint(prompt),
        validation_plan=list(validation_plan or ["engineering_tests", "git_diff_check"]),
        created_at=now,
        expires_at=now + ttl_sec,
        actor_id=actor_id,
        notes="M20.4 supervised read-only session",
    )
    store.put_approval(appr.to_dict())
    return appr


def validate_approval(
    store: EngineeringStore,
    approval_id: str,
    *,
    repository: str,
    branch: str,
    starting_commit: str,
    backlog_item_id: str,
    provider: str,
    prompt: str,
    mode: str = "readonly",
    now: Optional[float] = None,
) -> tuple[bool, str, Optional[dict]]:
    """Validate bound approval. Returns (ok, reason, approval_dict)."""
    now = now if now is not None else time.time()
    raw = store.get_approval(approval_id)
    if not raw:
        return False, "approval_not_found", None
    if raw.get("consumed"):
        return False, "approval_consumed", raw
    if float(raw.get("expires_at") or 0) < now:
        return False, "approval_expired", raw
    if raw.get("mode") != mode:
        return False, "mode_mismatch", raw
    if raw.get("repository") != repository:
        return False, "repository_mismatch", raw
    if raw.get("branch") != branch:
        return False, "branch_mismatch", raw
    if raw.get("starting_commit") != starting_commit:
        return False, "commit_mismatch", raw
    if raw.get("backlog_item_id") != backlog_item_id:
        return False, "item_mismatch", raw
    if raw.get("provider") != provider:
        return False, "provider_mismatch", raw
    if raw.get("prompt_fingerprint") != prompt_fingerprint(prompt):
        return False, "prompt_fingerprint_mismatch", raw
    if raw.get("approval_type") != APPROVAL_TYPE:
        return False, "approval_type_mismatch", raw
    return True, "ok", raw


def consume_approval(store: EngineeringStore, approval_id: str) -> None:
    raw = store.get_approval(approval_id)
    if not raw:
        return
    raw["consumed"] = True
    raw["consumed_at"] = time.time()
    store.put_approval(raw)
