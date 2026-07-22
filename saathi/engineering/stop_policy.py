"""M20.0 — Stop policy for engineering agent sessions."""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any

from saathi.engineering.models import StopMode

STOP_REASONS = frozenset({
    "policy_violation",
    "secret_detected",
    "merge_attempt",
    "deploy_attempt",
    "force_push_attempt",
    "destructive_action",
    "repository_identity_change",
    "another_writer",
    "disk_space_unsafe",
    "usage_quota_exhausted",
    "three_repair_attempts_failed",
    "human_approval_required",
    "critical_security_validation_failed",
    "task_scope_expanded",
    "unrelated_work",
    "stall_threshold",
    "live_trading_attempt",
    "operator_stop",
})

# Map detections → stop mode
_MODE_MAP = {
    "secret_detected": StopMode.TERMINATE,
    "secret_file_creation": StopMode.TERMINATE,
    "force_push_attempt": StopMode.TERMINATE,
    "merge_attempt": StopMode.TERMINATE,
    "deploy_attempt": StopMode.TERMINATE,
    "live_trading_attempt": StopMode.TERMINATE,
    "destructive_action": StopMode.TERMINATE,
    "policy_violation": StopMode.TERMINATE,
    "critical_security_validation_failed": StopMode.TERMINATE,
    "repository_identity_change": StopMode.TERMINATE,
    "disk_space_unsafe": StopMode.TERMINATE,
    "usage_quota_exhausted": StopMode.MARK_BLOCKED,
    "human_approval_required": StopMode.PAUSE_APPROVAL,
    "stall_threshold": StopMode.GRACEFUL,
    "stalled_session": StopMode.GRACEFUL,
    "three_repair_attempts_failed": StopMode.MARK_FAILED,
    "another_writer": StopMode.MARK_BLOCKED,
    "task_scope_expanded": StopMode.PAUSE_APPROVAL,
    "unrelated_work": StopMode.PAUSE_APPROVAL,
    "crashed_process": StopMode.MARK_FAILED,
    "operator_stop": StopMode.GRACEFUL,
}


@dataclass
class StopDecision:
    should_stop: bool
    reason: str
    mode: str
    force: bool = False
    audit: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class StopPolicy:
    def __init__(self, repair_failure_limit: int = 3):
        self.repair_failure_limit = repair_failure_limit
        self._audit_log: list[dict[str, Any]] = []

    def evaluate(
        self,
        *,
        detections: list[str] | None = None,
        secret_detected: bool = False,
        repair_failures: int = 0,
        human_approval_required: bool = False,
        operator_stop: bool = False,
    ) -> StopDecision:
        detections = list(detections or [])
        if secret_detected and "secret_detected" not in detections:
            detections.append("secret_detected")
        if repair_failures >= self.repair_failure_limit:
            detections.append("three_repair_attempts_failed")
        if human_approval_required:
            detections.append("human_approval_required")
        if operator_stop:
            detections.append("operator_stop")

        if not detections:
            return StopDecision(
                should_stop=False,
                reason="",
                mode="",
            )

        # Highest severity first
        priority = [
            "live_trading_attempt",
            "secret_detected",
            "secret_file_creation",
            "force_push_attempt",
            "merge_attempt",
            "deploy_attempt",
            "destructive_action",
            "policy_violation",
            "critical_security_validation_failed",
            "repository_identity_change",
            "disk_space_unsafe",
            "three_repair_attempts_failed",
            "crashed_process",
            "another_writer",
            "usage_quota_exhausted",
            "task_scope_expanded",
            "unrelated_work",
            "human_approval_required",
            "stalled_session",
            "stall_threshold",
            "operator_stop",
        ]
        reason = next((p for p in priority if p in detections), detections[0])
        mode = _MODE_MAP.get(reason, StopMode.GRACEFUL)
        force = mode == StopMode.TERMINATE and reason in (
            "live_trading_attempt",
            "secret_detected",
            "force_push_attempt",
            "merge_attempt",
            "deploy_attempt",
        )
        decision = StopDecision(
            should_stop=True,
            reason=reason,
            mode=mode.value if isinstance(mode, StopMode) else str(mode),
            force=force,
            audit={
                "detections": detections,
                "ts": time.time(),
            },
        )
        self._audit_log.append(decision.to_dict())
        return decision

    def audit_log(self) -> list[dict[str, Any]]:
        return list(self._audit_log)

    def record_forced_termination(self, session_id: str, reason: str) -> dict[str, Any]:
        entry = {
            "event": "forced_termination",
            "session_id": session_id,
            "reason": reason,
            "ts": time.time(),
        }
        self._audit_log.append(entry)
        return entry
