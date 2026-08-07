"""Owner approval workflow for paper strategy activation.

Single-use, reason-required, operator-identity recorded, immutable after decision.
LLM / strategy identities cannot approve.
"""
from __future__ import annotations

import time
from typing import Any

from saathi.platform.tg.paper_activation.models import (
    ActivationApproval,
    ActivationApprovalStatus,
    fingerprint,
)


FORBIDDEN_APPROVER_PREFIXES = ("llm:", "strategy:", "agent:", "model:", "bot:")


class ApprovalError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _assert_human_operator(identity: str) -> None:
    low = (identity or "").strip().lower()
    if not low:
        raise ApprovalError("OPERATOR_REQUIRED", "operator identity required")
    for p in FORBIDDEN_APPROVER_PREFIXES:
        if low.startswith(p):
            raise ApprovalError("SELF_APPROVAL_FORBIDDEN", f"identity {identity} cannot approve")


class ActivationApprovalCenter:
    """In-process approval store for paper activation (composes with platform AC)."""

    def __init__(self) -> None:
        self._by_id: dict[str, ActivationApproval] = {}

    def request(
        self,
        *,
        strategy_slug: str,
        strategy_version: str = "1.0.0",
        dataset_id: str = "",
        dataset_fingerprint: str = "",
        qualification_fingerprint: str = "",
        qualification_verdict: str = "",
        reason: str,
        operator_id: str,
        operator_identity: str,
        org_id: str = "local",
        workspace_id: str = "local",
        expires_in_sec: float = 7 * 86400,
        evidence: dict[str, Any] | None = None,
        single_use: bool = True,
    ) -> ActivationApproval:
        if not (reason or "").strip():
            raise ApprovalError("REASON_REQUIRED", "approval request requires a reason")
        _assert_human_operator(operator_identity)
        ap = ActivationApproval(
            strategy_slug=strategy_slug,
            strategy_version=strategy_version,
            dataset_id=dataset_id,
            dataset_fingerprint=dataset_fingerprint,
            qualification_fingerprint=qualification_fingerprint,
            status=ActivationApprovalStatus.PENDING,
            reason=reason.strip(),
            operator_id=operator_id,
            operator_identity=operator_identity,
            expires_at=time.time() + expires_in_sec,
            single_use=single_use,
            evidence={
                "qualification_verdict": qualification_verdict,
                **(evidence or {}),
                "request_fingerprint": fingerprint({
                    "strategy_slug": strategy_slug,
                    "strategy_version": strategy_version,
                    "dataset_fingerprint": dataset_fingerprint,
                    "qualification_fingerprint": qualification_fingerprint,
                    "reason": reason,
                }),
            },
            org_id=org_id,
            workspace_id=workspace_id,
        )
        self._by_id[ap.id] = ap
        return ap

    def decide(
        self,
        approval_id: str,
        *,
        decision: str,
        operator_id: str,
        operator_identity: str,
        notes: str = "",
        reason: str = "",
    ) -> ActivationApproval:
        _assert_human_operator(operator_identity)
        ap = self._by_id.get(approval_id)
        if not ap:
            raise ApprovalError("NOT_FOUND", f"approval {approval_id} not found")
        self._expire_if_needed(ap)
        if ap.status != ActivationApprovalStatus.PENDING:
            raise ApprovalError("NOT_PENDING", f"approval is {ap.status.value}")
        if ap.immutable:
            raise ApprovalError("IMMUTABLE", "approval already finalized")
        if not (reason or notes or ap.reason):
            raise ApprovalError("REASON_REQUIRED", "decision requires reason or notes")

        d = decision.strip().lower()
        if d == "approve":
            ap.status = ActivationApprovalStatus.APPROVED
        elif d == "reject":
            ap.status = ActivationApprovalStatus.REJECTED
            ap.rejection_reason = reason or notes
        else:
            raise ApprovalError("INVALID_DECISION", f"unknown decision {decision}")
        ap.decided_at = time.time()
        ap.operator_id = operator_id
        ap.operator_identity = operator_identity
        ap.notes = notes
        ap.freeze()
        return ap

    def revoke(
        self,
        approval_id: str,
        *,
        operator_identity: str,
        reason: str,
    ) -> ActivationApproval:
        _assert_human_operator(operator_identity)
        if not reason.strip():
            raise ApprovalError("REASON_REQUIRED", "revoke requires reason")
        ap = self._by_id.get(approval_id)
        if not ap:
            raise ApprovalError("NOT_FOUND", f"approval {approval_id} not found")
        if ap.status == ActivationApprovalStatus.CONSUMED:
            raise ApprovalError("ALREADY_CONSUMED", "cannot revoke consumed single-use approval")
        ap.status = ActivationApprovalStatus.REVOKED
        ap.rejection_reason = reason
        ap.decided_at = time.time()
        ap.operator_identity = operator_identity
        ap.freeze()
        return ap

    def consume(self, approval_id: str) -> ActivationApproval:
        ap = self._by_id.get(approval_id)
        if not ap:
            raise ApprovalError("NOT_FOUND", f"approval {approval_id} not found")
        self._expire_if_needed(ap)
        if ap.status != ActivationApprovalStatus.APPROVED:
            raise ApprovalError("NOT_APPROVED", f"approval is {ap.status.value}")
        if ap.single_use:
            ap.status = ActivationApprovalStatus.CONSUMED
            ap.consumed_at = time.time()
        return ap

    def get(self, approval_id: str) -> ActivationApproval | None:
        ap = self._by_id.get(approval_id)
        if ap:
            self._expire_if_needed(ap)
        return ap

    def list(
        self,
        *,
        org_id: str = "",
        workspace_id: str = "",
        strategy_slug: str = "",
        status: str = "",
    ) -> list[ActivationApproval]:
        out = []
        for ap in self._by_id.values():
            self._expire_if_needed(ap)
            if org_id and ap.org_id != org_id:
                continue
            if workspace_id and ap.workspace_id != workspace_id:
                continue
            if strategy_slug and ap.strategy_slug != strategy_slug:
                continue
            if status and ap.status.value != status:
                continue
            out.append(ap)
        return sorted(out, key=lambda a: a.created_at, reverse=True)

    def _expire_if_needed(self, ap: ActivationApproval) -> None:
        if ap.status == ActivationApprovalStatus.PENDING and ap.expires_at and time.time() > ap.expires_at:
            ap.status = ActivationApprovalStatus.EXPIRED
            ap.decided_at = time.time()
            ap.freeze()
