"""M349 — Lifecycle gates, independent review and evidence requirements.

One rule shapes this module: **no agent may approve its own output.** Every
other check exists to stop that rule being evaded — by an undeclared reviewer,
by a gate passed with no evidence, by a "pass" recorded over an unresolved
critical finding, or by an agent claiming the owner's approval on the owner's
behalf.

The SaathiOS-authored review standard applied here:

> A finding is not accepted merely because it sounds plausible. It must
> demonstrate a concrete, relevant failure mode.

Operationally, a ``high`` or ``critical`` claim must carry source location,
failure mode, trigger condition, caller or data-flow evidence and severity
rationale — enforced in :mod:`saathi.agentdev.artifacts`. This module adds the
gate-level consequence: a gate cannot pass while an unresolved critical finding
stands against its subject.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Iterable

from saathi.agentdev.artifacts import (
    Artifact,
    ArtifactKind,
    ArtifactStatus,
    ArtifactStore,
    Severity,
)
from saathi.agentdev.missions import DevMission, DevMissionStore, Gate, GateRecord
from saathi.agentdev.roles import can_review, get_role

OWNER = "owner"

#: The artifact kind each gate must point at as evidence.
GATE_EVIDENCE_KIND: dict[Gate, ArtifactKind] = {
    Gate.RESEARCH_COMPLETENESS: ArtifactKind.RESEARCH_FINDINGS,
    Gate.ARCHITECTURE_APPROVAL: ArtifactKind.ARCHITECTURE_DECISION,
    Gate.SECURITY_APPROVAL: ArtifactKind.SECURITY_REVIEW,
    Gate.IMPLEMENTATION_READINESS: ArtifactKind.IMPLEMENTATION_HANDOFF,
    Gate.CODE_REVIEW: ArtifactKind.CODE_REVIEW,
    Gate.AUTOMATED_TESTING: ArtifactKind.VERIFICATION_REPORT,
    Gate.NEGATIVE_PATH_TESTING: ArtifactKind.VERIFICATION_REPORT,
    Gate.RED_TEAM_REVIEW: ArtifactKind.MEETING_MINUTES,
    Gate.EXECUTIVE_SYNTHESIS: ArtifactKind.EXECUTIVE_DECISION,
    Gate.OWNER_APPROVAL: ArtifactKind.OWNER_APPROVAL,
    Gate.INTEGRATION_CANDIDACY: ArtifactKind.FINAL_SYNTHESIS,
}

#: Gates only the owner may pass. Automation can never satisfy these.
OWNER_ONLY_GATES = frozenset({Gate.OWNER_APPROVAL})

#: Gates the security role must approve, whoever else reviews the subject.
SECURITY_OWNED_GATES = frozenset({Gate.SECURITY_APPROVAL, Gate.RED_TEAM_REVIEW})


class GateError(ValueError):
    def __init__(self, code: str, detail: str = ""):
        self.code = code
        self.detail = detail
        super().__init__(f"{code}" + (f" ({detail})" if detail else ""))


@dataclass
class GateDecision:
    """The outcome of evaluating one gate, before it is recorded."""

    gate: str
    approver: str
    subject_author: str
    evidence_artifact_ids: list[str] = field(default_factory=list)
    refusals: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    decided_at: float = field(default_factory=time.time)

    @property
    def allowed(self) -> bool:
        return not self.refusals

    def to_dict(self) -> dict[str, Any]:
        return {
            "gate": self.gate,
            "approver": self.approver,
            "subject_author": self.subject_author,
            "evidence_artifact_ids": list(self.evidence_artifact_ids),
            "refusals": list(self.refusals),
            "warnings": list(self.warnings),
            "allowed": self.allowed,
            "decided_at": self.decided_at,
        }


def unresolved_critical_findings(artifacts: Iterable[Artifact]) -> list[str]:
    """Claim ids at ``critical`` severity on artifacts that are not accepted.

    A critical finding on an artifact that has since been accepted has been
    dealt with by definition; one on a draft, submitted, under-review, rejected
    or blocked artifact has not.
    """
    out: list[str] = []
    for artifact in artifacts:
        if artifact.status == ArtifactStatus.ACCEPTED.value:
            continue
        for claim in artifact.claims:
            if claim.severity == Severity.CRITICAL.value and not claim.is_insufficient_evidence:
                out.append(f"{artifact.artifact_id}:{claim.claim_id}")
    return out


class GateEngine:
    """Evaluates and records lifecycle gates."""

    def __init__(self, artifacts: ArtifactStore, missions: DevMissionStore):
        self.artifacts = artifacts
        self.missions = missions

    # ---- evaluation ---------------------------------------------------------

    def evaluate(
        self,
        dev_mission_id: str,
        gate: Gate | str,
        *,
        approver: str,
        subject_author: str,
        evidence_artifact_ids: list[str],
    ) -> GateDecision:
        """Collect every reason this gate may not pass. Performs no writes."""
        try:
            gate_enum = Gate(gate)
        except ValueError as exc:
            raise GateError("unknown_gate", str(gate)) from exc

        mission = self.missions.require(dev_mission_id)
        decision = GateDecision(
            gate=gate_enum.value,
            approver=approver,
            subject_author=subject_author,
            evidence_artifact_ids=list(evidence_artifact_ids),
        )
        refusals = decision.refusals

        # 1. No self-approval — the rule everything else protects.
        if approver == subject_author:
            refusals.append("self_approval_forbidden")

        # 2. Owner-only gates.
        if gate_enum in OWNER_ONLY_GATES:
            if approver != OWNER:
                refusals.append(f"owner_only_gate:{gate_enum.value}")
        else:
            if approver == OWNER:
                refusals.append("owner_may_only_pass_owner_gates")
            elif subject_author != OWNER:
                ok, reason = can_review(approver, subject_author)
                if not ok:
                    refusals.append(reason)

        # 3. Security-owned gates need the security role's approval.
        if gate_enum in SECURITY_OWNED_GATES and approver not in (
            "security-governance", OWNER
        ):
            refusals.append(f"security_gate_requires_security_role:{approver}")

        # 4. Evidence must exist, belong to this mission and be the right kind.
        if not evidence_artifact_ids:
            refusals.append("gate_without_evidence")
        expected = GATE_EVIDENCE_KIND[gate_enum]
        resolved: list[Artifact] = []
        for artifact_id in evidence_artifact_ids:
            artifact = self.artifacts.get(dev_mission_id, artifact_id)
            if artifact is None:
                refusals.append(f"evidence_not_found:{artifact_id}")
                continue
            resolved.append(artifact)
            if artifact.kind != expected.value:
                refusals.append(
                    f"evidence_wrong_kind:{artifact_id}:"
                    f"expected={expected.value}:actual={artifact.kind}"
                )

        # 5. The evidence must actually be the subject's work.
        if resolved and gate_enum not in OWNER_ONLY_GATES:
            authors = {a.authoring_agent for a in resolved}
            if subject_author not in authors:
                refusals.append(
                    f"evidence_not_authored_by_subject:{subject_author}"
                )

        # 6. An unresolved critical finding blocks the gate.
        blocking = unresolved_critical_findings(resolved)
        if blocking:
            refusals.append("unresolved_critical_findings:" + ",".join(blocking))

        # 7. An open security veto blocks every gate except its own withdrawal.
        if mission.open_vetoes and gate_enum is not Gate.SECURITY_APPROVAL:
            refusals.append("security_veto_open:" + ",".join(mission.open_vetoes))

        # 8. Negative-path testing needs a report that actually ran negative paths.
        if gate_enum is Gate.NEGATIVE_PATH_TESTING:
            if not any(
                (a.payload or {}).get("negative_paths") for a in resolved
            ):
                refusals.append("no_negative_path_results")

        # 9. Automated testing must not silently omit unrun checks.
        if gate_enum is Gate.AUTOMATED_TESTING:
            for artifact in resolved:
                if "not_run" not in (artifact.payload or {}):
                    refusals.append(
                        f"verification_without_not_run_list:{artifact.artifact_id}"
                    )

        if mission.unresolved_disagreements and gate_enum in (
            Gate.EXECUTIVE_SYNTHESIS,
            Gate.INTEGRATION_CANDIDACY,
        ):
            decision.warnings.append(
                "unresolved_disagreements_carried_into_decision:"
                + ",".join(mission.unresolved_disagreements)
            )

        return decision

    # ---- recording ----------------------------------------------------------

    def pass_gate(
        self,
        dev_mission_id: str,
        gate: Gate | str,
        *,
        approver: str,
        subject_author: str,
        evidence_artifact_ids: list[str],
        reason: str = "",
    ) -> tuple[DevMission, GateDecision]:
        """Record a passing gate. Fail-closed: any refusal aborts."""
        decision = self.evaluate(
            dev_mission_id,
            gate,
            approver=approver,
            subject_author=subject_author,
            evidence_artifact_ids=evidence_artifact_ids,
        )
        if not decision.allowed:
            raise GateError("gate_refused", "; ".join(decision.refusals))

        record = GateRecord(
            gate=decision.gate,
            status="passed",
            approver=approver,
            subject_author=subject_author,
            evidence_artifact_ids=list(evidence_artifact_ids),
            reason=reason or "; ".join(decision.warnings),
            decided_at=time.time(),
        )
        mission = self.missions.record_gate(dev_mission_id, record)
        return mission, decision

    def fail_gate(
        self,
        dev_mission_id: str,
        gate: Gate | str,
        *,
        approver: str,
        subject_author: str,
        reason: str,
        evidence_artifact_ids: list[str] | None = None,
    ) -> DevMission:
        """Record a failing gate. A failure still may not be self-recorded."""
        try:
            gate_enum = Gate(gate)
        except ValueError as exc:
            raise GateError("unknown_gate", str(gate)) from exc
        if approver == subject_author:
            raise GateError("self_approval_forbidden", approver)
        if not reason.strip():
            raise GateError("failure_without_reason", gate_enum.value)
        record = GateRecord(
            gate=gate_enum.value,
            status="failed",
            approver=approver,
            subject_author=subject_author,
            evidence_artifact_ids=list(evidence_artifact_ids or []),
            reason=reason,
            decided_at=time.time(),
        )
        return self.missions.record_gate(dev_mission_id, record)

    def report(self, dev_mission_id: str) -> dict[str, Any]:
        mission = self.missions.require(dev_mission_id)
        rows = []
        for gate in Gate:
            record = mission.gate(gate)
            rows.append({
                "gate": gate.value,
                "status": record.status,
                "approver": record.approver or None,
                "subject_author": record.subject_author or None,
                "evidence": record.evidence_artifact_ids,
                "required_evidence_kind": GATE_EVIDENCE_KIND[gate].value,
                "owner_only": gate in OWNER_ONLY_GATES,
                "security_owned": gate in SECURITY_OWNED_GATES,
            })
        return {
            "dev_mission_id": dev_mission_id,
            "state": mission.state,
            "gates": rows,
            "open_vetoes": mission.open_vetoes,
            "unresolved_disagreements": mission.unresolved_disagreements,
        }


def review_finding_requirements() -> dict[str, str]:
    """The SaathiOS-authored review standard, as data for docs and the CLI."""
    return {
        "principle": (
            "A finding is not accepted merely because it sounds plausible. "
            "It must demonstrate a concrete, relevant failure mode."
        ),
        "source_location": "Exact file and line of the affected source.",
        "failure_mode": "What goes wrong, stated as an outcome.",
        "trigger_condition": "The input or state that causes it.",
        "caller_or_dataflow_evidence": "Who calls this, or where the data comes from.",
        "severity_rationale": "Why this severity and not one lower.",
        "recommended_remediation": "What to change.",
        "applies_to": "Any claim at severity high or critical.",
    }
