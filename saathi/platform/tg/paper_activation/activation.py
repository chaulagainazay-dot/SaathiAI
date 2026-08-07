"""Strategy paper activation gate.

PAPER_ACTIVE requires:
  PAPER_ELIGIBLE + accepted dataset + WF + stress + MC + RoR OK + owner approval
"""
from __future__ import annotations

import time
from typing import Any

from saathi.platform.tg.data_contract import is_authoritative, NON_AUTHORITATIVE, DataClassification
from saathi.platform.tg.domain import StrategyEvaluationVerdict
from saathi.platform.tg.paper_activation.approvals import ActivationApprovalCenter, ApprovalError
from saathi.platform.tg.paper_activation.models import (
    ActivationApprovalStatus,
    PaperActivationState,
    StrategyActivationRecord,
    fingerprint,
)


class ActivationError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


REQUIRED_GATES = (
    "non_fixture_authoritative_dataset",
    "accepted_data_quality",
    "walk_forward_completed",
    "stress_completed",
    "monte_carlo_completed",
    "acceptable_risk_of_ruin",
    "realistic_fees",
    "realistic_slippage",
    "owner_approval",
)


class PaperActivationService:
    def __init__(self, approvals: ActivationApprovalCenter | None = None):
        self.approvals = approvals or ActivationApprovalCenter()
        self._records: dict[str, StrategyActivationRecord] = {}  # key strategy_slug+org

    def _key(self, slug: str, org_id: str, workspace_id: str) -> str:
        return f"{org_id}:{workspace_id}:{slug}"

    def get_record(
        self, strategy_slug: str, *, org_id: str = "local", workspace_id: str = "local"
    ) -> StrategyActivationRecord | None:
        return self._records.get(self._key(strategy_slug, org_id, workspace_id))

    def list_records(self, *, org_id: str = "", workspace_id: str = "") -> list[StrategyActivationRecord]:
        out = []
        for r in self._records.values():
            if org_id and r.org_id != org_id:
                continue
            if workspace_id and r.workspace_id != workspace_id:
                continue
            out.append(r)
        return out

    def evaluate_eligibility(
        self,
        *,
        strategy_slug: str,
        qualification: dict[str, Any],
    ) -> dict[str, Any]:
        """Check whether qualification package may enter approval pipeline."""
        verdict = str(qualification.get("verdict") or "")
        gates = qualification.get("gates") or {}
        cls = str(qualification.get("data_classification") or "")
        authoritative = bool(qualification.get("authoritative")) or is_authoritative(cls)

        checks = {
            "verdict_paper_eligible": verdict == StrategyEvaluationVerdict.PAPER_ELIGIBLE.value,
            "authoritative_dataset": authoritative and cls not in {c.value for c in NON_AUTHORITATIVE},
            "walk_forward": bool(gates.get("walk_forward_completed")),
            "stress": bool(gates.get("stress_completed")),
            "monte_carlo": bool(gates.get("monte_carlo_completed")),
            "risk_of_ruin": bool(gates.get("acceptable_risk_of_ruin")),
            "fees": bool(gates.get("realistic_fees")),
            "slippage": bool(gates.get("realistic_slippage")),
            "no_live_verdict": verdict not in ("LIVE_APPROVED", "PRODUCTION_READY"),
        }
        ok = all(checks.values())
        return {
            "eligible_for_approval": ok,
            "checks": checks,
            "verdict": verdict,
            "data_classification": cls,
            "paper_only": True,
            "next": "request_owner_approval" if ok else "remain_research_only",
        }

    def request_activation_approval(
        self,
        *,
        strategy_slug: str,
        qualification: dict[str, Any],
        reason: str,
        operator_id: str,
        operator_identity: str,
        strategy_version: str = "1.0.0",
        dataset_id: str = "",
        dataset_fingerprint: str = "",
        org_id: str = "local",
        workspace_id: str = "local",
    ) -> dict[str, Any]:
        elig = self.evaluate_eligibility(strategy_slug=strategy_slug, qualification=qualification)
        if not elig["eligible_for_approval"]:
            raise ActivationError(
                "NOT_PAPER_ELIGIBLE",
                f"strategy not eligible for paper activation: {elig['checks']}",
            )
        qfp = fingerprint(qualification)
        try:
            ap = self.approvals.request(
                strategy_slug=strategy_slug,
                strategy_version=strategy_version,
                dataset_id=dataset_id,
                dataset_fingerprint=dataset_fingerprint,
                qualification_fingerprint=qfp,
                qualification_verdict=str(qualification.get("verdict") or ""),
                reason=reason,
                operator_id=operator_id,
                operator_identity=operator_identity,
                org_id=org_id,
                workspace_id=workspace_id,
                evidence={"eligibility": elig},
            )
        except ApprovalError as e:
            raise ActivationError(e.code, e.message) from e

        rec = self._records.get(self._key(strategy_slug, org_id, workspace_id))
        if rec is None:
            rec = StrategyActivationRecord(
                strategy_slug=strategy_slug,
                strategy_version=strategy_version,
                org_id=org_id,
                workspace_id=workspace_id,
            )
            self._records[self._key(strategy_slug, org_id, workspace_id)] = rec
        rec.state = PaperActivationState.APPROVAL_PENDING
        rec.qualification_verdict = str(qualification.get("verdict") or "")
        rec.qualification_fingerprint = qfp
        rec.dataset_id = dataset_id
        rec.dataset_fingerprint = dataset_fingerprint
        rec.approval_id = ap.id
        rec.record("approval_requested", approval_id=ap.id)
        return {"approval": ap.to_public(), "activation": rec.to_public(), "paper_only": True}

    def decide_approval(
        self,
        approval_id: str,
        *,
        decision: str,
        operator_id: str,
        operator_identity: str,
        notes: str = "",
        reason: str = "",
    ) -> dict[str, Any]:
        try:
            ap = self.approvals.decide(
                approval_id,
                decision=decision,
                operator_id=operator_id,
                operator_identity=operator_identity,
                notes=notes,
                reason=reason,
            )
        except ApprovalError as e:
            raise ActivationError(e.code, e.message) from e

        rec = None
        for r in self._records.values():
            if r.approval_id == approval_id:
                rec = r
                break
        if rec:
            if ap.status == ActivationApprovalStatus.APPROVED:
                rec.state = PaperActivationState.PAPER_APPROVED
                rec.record("approved", by=operator_identity)
            elif ap.status == ActivationApprovalStatus.REJECTED:
                rec.state = PaperActivationState.REJECTED
                rec.record("rejected", by=operator_identity, reason=reason or notes)
        return {
            "approval": ap.to_public(),
            "activation": rec.to_public() if rec else None,
            "paper_only": True,
            "live_authorized": False,
        }

    def activate(
        self,
        strategy_slug: str,
        *,
        approval_id: str,
        portfolio_id: str,
        operator_identity: str,
        org_id: str = "local",
        workspace_id: str = "local",
    ) -> StrategyActivationRecord:
        from saathi.platform.tg.paper_activation.approvals import _assert_human_operator
        try:
            _assert_human_operator(operator_identity)
        except ApprovalError as e:
            raise ActivationError(e.code, e.message) from e

        rec = self._records.get(self._key(strategy_slug, org_id, workspace_id))
        if not rec:
            raise ActivationError("NOT_FOUND", "activation record not found — request approval first")
        if rec.state not in (PaperActivationState.PAPER_APPROVED, PaperActivationState.APPROVAL_PENDING):
            # allow if approval is approved even if state lagging
            pass
        try:
            ap = self.approvals.consume(approval_id)
        except ApprovalError as e:
            raise ActivationError(e.code, e.message) from e
        if ap.strategy_slug != strategy_slug:
            raise ActivationError("STRATEGY_MISMATCH", "approval strategy mismatch")
        if rec.state == PaperActivationState.PAPER_ACTIVE and rec.portfolio_id == portfolio_id:
            return rec  # idempotent

        rec.state = PaperActivationState.PAPER_ACTIVE
        rec.approval_id = approval_id
        rec.portfolio_id = portfolio_id
        rec.activated_at = time.time()
        rec.halted_at = None
        rec.halt_reason = ""
        rec.record("activated", portfolio_id=portfolio_id, approval_id=approval_id, by=operator_identity)
        return rec

    def halt(
        self,
        strategy_slug: str,
        *,
        reason: str,
        org_id: str = "local",
        workspace_id: str = "local",
    ) -> StrategyActivationRecord:
        rec = self._records.get(self._key(strategy_slug, org_id, workspace_id))
        if not rec:
            raise ActivationError("NOT_FOUND", "activation record not found")
        if rec.state != PaperActivationState.PAPER_ACTIVE:
            raise ActivationError("NOT_ACTIVE", f"state is {rec.state.value}")
        rec.state = PaperActivationState.PAPER_HALTED
        rec.halted_at = time.time()
        rec.halt_reason = reason
        rec.record("halted", reason=reason)
        return rec

    def resume(
        self,
        strategy_slug: str,
        *,
        operator_identity: str,
        org_id: str = "local",
        workspace_id: str = "local",
    ) -> StrategyActivationRecord:
        from saathi.platform.tg.paper_activation.approvals import _assert_human_operator
        try:
            _assert_human_operator(operator_identity)
        except ApprovalError as e:
            raise ActivationError(e.code, e.message) from e
        rec = self._records.get(self._key(strategy_slug, org_id, workspace_id))
        if not rec:
            raise ActivationError("NOT_FOUND", "activation record not found")
        if rec.state != PaperActivationState.PAPER_HALTED:
            raise ActivationError("NOT_HALTED", f"state is {rec.state.value}")
        rec.state = PaperActivationState.PAPER_ACTIVE
        rec.halted_at = None
        rec.halt_reason = ""
        rec.record("resumed", by=operator_identity)
        return rec

    def is_paper_active(
        self, strategy_slug: str, *, org_id: str = "local", workspace_id: str = "local"
    ) -> bool:
        rec = self.get_record(strategy_slug, org_id=org_id, workspace_id=workspace_id)
        return bool(rec and rec.state == PaperActivationState.PAPER_ACTIVE)
