"""M347 — Durable mission artifacts.

Chat transcripts are not evidence: they are unaddressable, unversioned and
unreviewable. Every claim a development agent makes lands here instead, as a
schema-validated document bound to a mission, an author, a repository SHA and —
when code is involved — a worktree and a branch.

The seventeen kinds are a closed vocabulary — sixteen from M347 plus
``documentation_update``, added in M354 because the Documentation Agent held a
capability with no artifact it could write. Every artifact carries the same
fifteen envelope fields, so a reviewer, a gate and the final synthesis all read
the same shape regardless of who wrote it.

Claims are separable by epistemic status. A ``fact`` requires an evidence
reference and is refused without one; an ``inference`` must name the facts it
rests on; an ``assumption`` must state what would falsify it. This is what
makes "separate fact from inference" checkable rather than aspirational.

``INSUFFICIENT_EVIDENCE`` is a first-class value. An agent that cannot answer
records it; an agent that omits the question instead is caught by the
completeness check in :func:`validate_artifact`.
"""
from __future__ import annotations

import json
import os
import re
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Iterable

from saathi.agentdev.roles import get_role

INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"

_SHA_RE = re.compile(r"^[0-9a-f]{7,40}$")
_MISSION_RE = re.compile(r"^dm[a-z0-9]{2,24}$")


class ArtifactKind(str, Enum):
    MISSION_INTAKE = "mission_intake"
    TASK_ASSIGNMENT = "task_assignment"
    RESEARCH_FINDINGS = "research_findings"
    PROPOSAL = "proposal"
    CHALLENGE = "challenge"
    RESPONSE = "response"
    ARCHITECTURE_DECISION = "architecture_decision"
    SECURITY_REVIEW = "security_review"
    MEETING_AGENDA = "meeting_agenda"
    MEETING_MINUTES = "meeting_minutes"
    IMPLEMENTATION_HANDOFF = "implementation_handoff"
    CODE_REVIEW = "code_review"
    VERIFICATION_REPORT = "verification_report"
    EXECUTIVE_DECISION = "executive_decision"
    OWNER_APPROVAL = "owner_approval"
    FINAL_SYNTHESIS = "final_synthesis"
    # M354. The Documentation Agent held ``author_documentation`` with no kind
    # it could write; every other capability had one. Adding the kind was the
    # smaller correction — the alternative was letting documentation masquerade
    # as research findings.
    DOCUMENTATION_UPDATE = "documentation_update"


class ArtifactStatus(str, Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"
    BLOCKED = "blocked"


ARTIFACT_TRANSITIONS: dict[ArtifactStatus, frozenset[ArtifactStatus]] = {
    ArtifactStatus.DRAFT: frozenset({ArtifactStatus.SUBMITTED, ArtifactStatus.SUPERSEDED}),
    ArtifactStatus.SUBMITTED: frozenset({
        ArtifactStatus.UNDER_REVIEW, ArtifactStatus.BLOCKED, ArtifactStatus.SUPERSEDED,
    }),
    ArtifactStatus.UNDER_REVIEW: frozenset({
        ArtifactStatus.ACCEPTED, ArtifactStatus.REJECTED, ArtifactStatus.BLOCKED,
    }),
    ArtifactStatus.REJECTED: frozenset({ArtifactStatus.DRAFT, ArtifactStatus.SUPERSEDED}),
    ArtifactStatus.BLOCKED: frozenset({
        ArtifactStatus.UNDER_REVIEW, ArtifactStatus.DRAFT, ArtifactStatus.SUPERSEDED,
    }),
    ArtifactStatus.ACCEPTED: frozenset({ArtifactStatus.SUPERSEDED}),
    ArtifactStatus.SUPERSEDED: frozenset(),
}


class ClaimKind(str, Enum):
    FACT = "fact"
    INFERENCE = "inference"
    ASSUMPTION = "assumption"


class Severity(str, Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TerminalVerdict(str, Enum):
    APPROVED_FOR_IMPLEMENTATION = "APPROVED_FOR_IMPLEMENTATION"
    APPROVED_WITH_LIMITATIONS = "APPROVED_WITH_LIMITATIONS"
    RESEARCH_REQUIRED = "RESEARCH_REQUIRED"
    REWORK_REQUIRED = "REWORK_REQUIRED"
    REJECTED = "REJECTED"
    OWNER_DECISION_REQUIRED = "OWNER_DECISION_REQUIRED"


#: Capability an author must hold to write each kind. A role writing a kind it
#: has no capability for is refused — this is how the role contract and the
#: artifact protocol stay in agreement.
KIND_CAPABILITY: dict[ArtifactKind, str] = {
    ArtifactKind.MISSION_INTAKE: "synthesize_decision",
    ArtifactKind.TASK_ASSIGNMENT: "assign_task",
    ArtifactKind.RESEARCH_FINDINGS: "write_artifact",
    ArtifactKind.PROPOSAL: "create_proposal",
    ArtifactKind.CHALLENGE: "create_challenge",
    ArtifactKind.RESPONSE: "respond_to_challenge",
    ArtifactKind.ARCHITECTURE_DECISION: "create_proposal",
    ArtifactKind.SECURITY_REVIEW: "review_security",
    ArtifactKind.MEETING_AGENDA: "chair_meeting",
    ArtifactKind.MEETING_MINUTES: "chair_meeting",
    ArtifactKind.IMPLEMENTATION_HANDOFF: "assign_task",
    ArtifactKind.CODE_REVIEW: "review_code",
    ArtifactKind.VERIFICATION_REPORT: "run_tests",
    ArtifactKind.EXECUTIVE_DECISION: "synthesize_decision",
    ArtifactKind.FINAL_SYNTHESIS: "synthesize_decision",
    ArtifactKind.DOCUMENTATION_UPDATE: "author_documentation",
    # OWNER_APPROVAL has no agent capability: only the owner may author it.
}

OWNER_AUTHOR = "owner"

#: Kinds that must carry a worktree and branch, because they describe code.
CODE_BOUND_KINDS = frozenset({
    ArtifactKind.IMPLEMENTATION_HANDOFF,
    ArtifactKind.CODE_REVIEW,
    ArtifactKind.VERIFICATION_REPORT,
})


class ArtifactError(ValueError):
    def __init__(self, code: str, detail: str = ""):
        self.code = code
        self.detail = detail
        super().__init__(f"{code}" + (f" ({detail})" if detail else ""))


def new_artifact_id(kind: ArtifactKind | str) -> str:
    prefix = (kind.value if isinstance(kind, ArtifactKind) else str(kind))[:4]
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


@dataclass
class Claim:
    """One assertion, with its epistemic status made explicit.

    ``fact`` requires ``evidence_ref``. ``inference`` requires ``rests_on``
    naming the claim ids it derives from. ``assumption`` requires
    ``falsified_by``. A claim whose statement is ``INSUFFICIENT_EVIDENCE`` is
    always acceptable and needs none of these.
    """

    claim_id: str
    statement: str
    kind: str = ClaimKind.INFERENCE.value
    evidence_ref: str = ""
    rests_on: list[str] = field(default_factory=list)
    falsified_by: str = ""
    severity: str = Severity.INFO.value
    # Fields a high or critical finding must carry (M349 review rule).
    source_location: str = ""
    failure_mode: str = ""
    trigger_condition: str = ""
    caller_or_dataflow_evidence: str = ""
    severity_rationale: str = ""
    recommended_remediation: str = ""

    @property
    def is_insufficient_evidence(self) -> bool:
        return self.statement.strip() == INSUFFICIENT_EVIDENCE

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Claim":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in d.items() if k in known})


@dataclass
class Artifact:
    """The common envelope. Every kind carries all fifteen fields."""

    artifact_id: str
    mission_id: str
    kind: str
    authoring_agent: str
    repository_sha: str
    title: str = ""
    body: str = ""
    worktree: str = ""
    branch: str = ""
    status: str = ArtifactStatus.DRAFT.value
    claims: list[Claim] = field(default_factory=list)
    evidence_references: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    unresolved_questions: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    required_next_action: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    supersedes: str = ""

    # ---- derived ------------------------------------------------------------

    @property
    def artifact_kind(self) -> ArtifactKind:
        return ArtifactKind(self.kind)

    def claims_of(self, kind: ClaimKind | str) -> list[Claim]:
        value = kind.value if isinstance(kind, ClaimKind) else kind
        return [c for c in self.claims if c.kind == value]

    @property
    def has_insufficient_evidence(self) -> bool:
        return any(c.is_insufficient_evidence for c in self.claims)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["claims"] = [c.to_dict() if isinstance(c, Claim) else c for c in self.claims]
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Artifact":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        payload = {k: v for k, v in d.items() if k in known}
        payload["claims"] = [
            c if isinstance(c, Claim) else Claim.from_dict(c)
            for c in (d.get("claims") or [])
        ]
        return cls(**payload)


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------


def validate_claim(claim: Claim, *, known_claim_ids: Iterable[str] = ()) -> None:
    if not claim.claim_id.strip():
        raise ArtifactError("claim_missing_id")
    if not claim.statement.strip():
        raise ArtifactError("claim_missing_statement", claim.claim_id)
    try:
        kind = ClaimKind(claim.kind)
    except ValueError as exc:
        raise ArtifactError("claim_invalid_kind", f"{claim.claim_id}:{claim.kind}") from exc
    try:
        severity = Severity(claim.severity)
    except ValueError as exc:
        raise ArtifactError(
            "claim_invalid_severity", f"{claim.claim_id}:{claim.severity}"
        ) from exc

    if claim.is_insufficient_evidence:
        return  # An honest non-answer needs no supporting apparatus.

    if kind is ClaimKind.FACT and not claim.evidence_ref.strip():
        raise ArtifactError("fact_without_evidence", claim.claim_id)
    if kind is ClaimKind.INFERENCE and not claim.rests_on:
        raise ArtifactError("inference_without_basis", claim.claim_id)
    if kind is ClaimKind.ASSUMPTION and not claim.falsified_by.strip():
        raise ArtifactError("assumption_without_falsifier", claim.claim_id)

    if kind is ClaimKind.INFERENCE:
        known = set(known_claim_ids)
        missing = [c for c in claim.rests_on if c not in known]
        if missing:
            raise ArtifactError(
                "inference_basis_not_found", f"{claim.claim_id}:{','.join(missing)}"
            )

    if severity in (Severity.HIGH, Severity.CRITICAL):
        required = {
            "source_location": claim.source_location,
            "failure_mode": claim.failure_mode,
            "trigger_condition": claim.trigger_condition,
            "caller_or_dataflow_evidence": claim.caller_or_dataflow_evidence,
            "severity_rationale": claim.severity_rationale,
        }
        missing = sorted(k for k, v in required.items() if not str(v).strip())
        if missing:
            raise ArtifactError(
                "high_severity_without_evidence", f"{claim.claim_id}:{','.join(missing)}"
            )


def validate_artifact(artifact: Artifact) -> None:
    """Refuse a malformed artifact. Raises on the first violation."""
    if not artifact.artifact_id.strip():
        raise ArtifactError("missing_artifact_id")
    if not _MISSION_RE.match(artifact.mission_id or ""):
        raise ArtifactError("invalid_mission_id", artifact.mission_id)
    try:
        kind = ArtifactKind(artifact.kind)
    except ValueError as exc:
        raise ArtifactError("unknown_artifact_kind", artifact.kind) from exc
    try:
        ArtifactStatus(artifact.status)
    except ValueError as exc:
        raise ArtifactError("unknown_artifact_status", artifact.status) from exc
    if not _SHA_RE.match(artifact.repository_sha or ""):
        raise ArtifactError("invalid_repository_sha", artifact.repository_sha)
    if not artifact.title.strip():
        raise ArtifactError("missing_title", artifact.artifact_id)
    if not artifact.required_next_action.strip():
        raise ArtifactError("missing_required_next_action", artifact.artifact_id)

    # Authorship.
    if kind is ArtifactKind.OWNER_APPROVAL:
        if artifact.authoring_agent != OWNER_AUTHOR:
            raise ArtifactError(
                "owner_approval_not_authored_by_owner", artifact.authoring_agent
            )
    else:
        if artifact.authoring_agent == OWNER_AUTHOR:
            raise ArtifactError("owner_may_only_author_owner_approval", artifact.kind)
        role = get_role(artifact.authoring_agent)
        if role is None:
            raise ArtifactError("unknown_authoring_agent", artifact.authoring_agent)
        capability = KIND_CAPABILITY.get(kind)
        if capability and not role.has_capability(capability):
            raise ArtifactError(
                "author_lacks_capability",
                f"{artifact.authoring_agent}:{capability}:{kind.value}",
            )

    # Code-bound kinds must say which worktree and branch they describe.
    if kind in CODE_BOUND_KINDS:
        if not artifact.worktree.strip():
            raise ArtifactError("code_artifact_without_worktree", artifact.artifact_id)
        if not artifact.branch.strip():
            raise ArtifactError("code_artifact_without_branch", artifact.artifact_id)

    # Claims.
    ids = [c.claim_id for c in artifact.claims]
    duplicates = {i for i in ids if ids.count(i) > 1}
    if duplicates:
        raise ArtifactError("duplicate_claim_id", ",".join(sorted(duplicates)))
    for claim in artifact.claims:
        validate_claim(claim, known_claim_ids=ids)

    _validate_kind_specific(artifact, kind)


def _validate_kind_specific(artifact: Artifact, kind: ArtifactKind) -> None:
    payload = artifact.payload or {}

    if kind is ArtifactKind.RESEARCH_FINDINGS:
        if not artifact.claims:
            raise ArtifactError("research_without_claims", artifact.artifact_id)
        if "not_investigated" not in payload:
            raise ArtifactError("research_without_not_investigated", artifact.artifact_id)

    elif kind is ArtifactKind.CHALLENGE:
        required = (
            "claim", "evidence", "counterargument", "failure_mode", "risk",
            "alternative", "decision_required",
        )
        missing = [f for f in required if not str(payload.get(f, "")).strip()]
        if missing:
            raise ArtifactError(
                "challenge_incomplete", f"{artifact.artifact_id}:{','.join(missing)}"
            )
        if not artifact.dependencies:
            raise ArtifactError("challenge_without_target", artifact.artifact_id)

    elif kind is ArtifactKind.RESPONSE:
        if not artifact.dependencies:
            raise ArtifactError("response_without_challenge", artifact.artifact_id)
        if not str(payload.get("position", "")).strip():
            raise ArtifactError("response_without_position", artifact.artifact_id)

    elif kind is ArtifactKind.ARCHITECTURE_DECISION:
        for required_key in ("reuse_table", "new_components", "rollback_path"):
            if required_key not in payload:
                raise ArtifactError(
                    "architecture_decision_incomplete",
                    f"{artifact.artifact_id}:{required_key}",
                )
        for entry in payload.get("new_components") or []:
            if not str((entry or {}).get("why_no_existing_component", "")).strip():
                raise ArtifactError(
                    "new_component_without_justification",
                    str((entry or {}).get("name", "?")),
                )

    elif kind is ArtifactKind.SECURITY_REVIEW:
        if "verdict" not in payload:
            raise ArtifactError("security_review_without_verdict", artifact.artifact_id)
        if "trading_guardian_impact" not in payload:
            raise ArtifactError(
                "security_review_without_trading_guardian_statement",
                artifact.artifact_id,
            )
        if "global_config_impact" not in payload:
            raise ArtifactError(
                "security_review_without_global_config_statement", artifact.artifact_id
            )

    elif kind is ArtifactKind.MEETING_AGENDA:
        if not payload.get("participants"):
            raise ArtifactError("agenda_without_participants", artifact.artifact_id)
        if not payload.get("questions"):
            raise ArtifactError("agenda_without_questions", artifact.artifact_id)

    elif kind is ArtifactKind.MEETING_MINUTES:
        for required_key in ("agreements", "disagreements", "outcome"):
            if required_key not in payload:
                raise ArtifactError(
                    "minutes_incomplete", f"{artifact.artifact_id}:{required_key}"
                )

    elif kind is ArtifactKind.IMPLEMENTATION_HANDOFF:
        for required_key in ("scope", "out_of_scope", "importers", "data_shapes"):
            if required_key not in payload:
                raise ArtifactError(
                    "handoff_incomplete", f"{artifact.artifact_id}:{required_key}"
                )

    elif kind is ArtifactKind.CODE_REVIEW:
        if "reviewed_author" not in payload:
            raise ArtifactError("code_review_without_author", artifact.artifact_id)
        if payload.get("reviewed_author") == artifact.authoring_agent:
            raise ArtifactError("code_review_of_own_work", artifact.authoring_agent)

    elif kind is ArtifactKind.VERIFICATION_REPORT:
        results = payload.get("results")
        if not results:
            raise ArtifactError("verification_without_results", artifact.artifact_id)
        for entry in results:
            if not str((entry or {}).get("command", "")).strip():
                raise ArtifactError(
                    "verification_result_without_command", artifact.artifact_id
                )
        if "not_run" not in payload:
            raise ArtifactError("verification_without_not_run_list", artifact.artifact_id)

    elif kind in (ArtifactKind.EXECUTIVE_DECISION, ArtifactKind.FINAL_SYNTHESIS):
        verdict = payload.get("verdict")
        try:
            TerminalVerdict(str(verdict))
        except ValueError as exc:
            raise ArtifactError("invalid_terminal_verdict", str(verdict)) from exc
        if "unresolved_risks" not in payload:
            raise ArtifactError("decision_without_unresolved_risks", artifact.artifact_id)

    elif kind is ArtifactKind.OWNER_APPROVAL:
        if payload.get("approved") is None:
            raise ArtifactError("owner_approval_without_decision", artifact.artifact_id)


def can_transition(current: str | ArtifactStatus, new: str | ArtifactStatus) -> bool:
    cur = ArtifactStatus(current) if not isinstance(current, ArtifactStatus) else current
    nxt = ArtifactStatus(new) if not isinstance(new, ArtifactStatus) else new
    if cur == nxt:
        return True
    return nxt in ARTIFACT_TRANSITIONS.get(cur, frozenset())


# --------------------------------------------------------------------------
# Store
# --------------------------------------------------------------------------


class ArtifactStore:
    """One JSON file per artifact under ``<root>/<mission_id>/artifacts/``.

    Durability primitives copied from ``saathi.engineering.store``: write to a
    temp file, keep a ``.bak`` of the previous content, then ``os.replace``.
    """

    def __init__(self, root: Path | str):
        self.root = Path(root)

    def mission_dir(self, mission_id: str) -> Path:
        if not _MISSION_RE.match(mission_id or ""):
            raise ArtifactError("invalid_mission_id", mission_id)
        return self.root / mission_id / "artifacts"

    def _path(self, artifact: Artifact) -> Path:
        return self.mission_dir(artifact.mission_id) / f"{artifact.artifact_id}.json"

    def put(self, artifact: Artifact) -> Artifact:
        validate_artifact(artifact)
        existing = self.get(artifact.mission_id, artifact.artifact_id)
        if existing is not None and existing.status != artifact.status:
            if not can_transition(existing.status, artifact.status):
                raise ArtifactError(
                    "invalid_status_transition",
                    f"{existing.status}->{artifact.status}",
                )
        artifact.updated_at = time.time()
        path = self._path(artifact)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.stat().st_size > 0:
            path.with_suffix(".json.bak").write_bytes(path.read_bytes())
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(artifact.to_dict(), indent=2, default=str), encoding="utf-8"
        )
        os.replace(tmp, path)
        return artifact

    def get(self, mission_id: str, artifact_id: str) -> Artifact | None:
        path = self.mission_dir(mission_id) / f"{artifact_id}.json"
        if not path.exists():
            return None
        try:
            return Artifact.from_dict(json.loads(path.read_text(encoding="utf-8")))
        except json.JSONDecodeError as exc:
            raise ArtifactError("artifact_corrupt", str(path)) from exc

    def list(
        self,
        mission_id: str,
        *,
        kind: ArtifactKind | str | None = None,
        author: str | None = None,
        status: ArtifactStatus | str | None = None,
    ) -> list[Artifact]:
        directory = self.mission_dir(mission_id)
        if not directory.exists():
            return []
        out: list[Artifact] = []
        for path in sorted(directory.glob("*.json")):
            if path.name.endswith(".bak.json"):
                continue
            try:
                out.append(
                    Artifact.from_dict(json.loads(path.read_text(encoding="utf-8")))
                )
            except json.JSONDecodeError:
                continue
        if kind is not None:
            value = kind.value if isinstance(kind, ArtifactKind) else str(kind)
            out = [a for a in out if a.kind == value]
        if author is not None:
            out = [a for a in out if a.authoring_agent == author]
        if status is not None:
            value = status.value if isinstance(status, ArtifactStatus) else str(status)
            out = [a for a in out if a.status == value]
        return sorted(out, key=lambda a: a.created_at)

    def set_status(
        self, mission_id: str, artifact_id: str, status: ArtifactStatus | str
    ) -> Artifact:
        artifact = self.get(mission_id, artifact_id)
        if artifact is None:
            raise ArtifactError("unknown_artifact", artifact_id)
        value = status.value if isinstance(status, ArtifactStatus) else str(status)
        if not can_transition(artifact.status, value):
            raise ArtifactError(
                "invalid_status_transition", f"{artifact.status}->{value}"
            )
        artifact.status = value
        return self.put(artifact)


def make_artifact(
    *,
    mission_id: str,
    kind: ArtifactKind | str,
    authoring_agent: str,
    repository_sha: str,
    title: str,
    required_next_action: str,
    **extra: Any,
) -> Artifact:
    """Construct and validate in one step. Never returns an invalid artifact."""
    kind_value = kind.value if isinstance(kind, ArtifactKind) else str(kind)
    artifact = Artifact(
        artifact_id=extra.pop("artifact_id", None) or new_artifact_id(kind_value),
        mission_id=mission_id,
        kind=kind_value,
        authoring_agent=authoring_agent,
        repository_sha=repository_sha,
        title=title,
        required_next_action=required_next_action,
        **extra,
    )
    validate_artifact(artifact)
    return artifact
