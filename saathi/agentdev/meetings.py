"""M348 — Structured meetings and the disagreement protocol.

A meeting here is not a multi-agent chat. It is a five-phase state machine over
durable artifacts:

    agenda -> collecting -> challenging -> responding -> synthesizing -> finalized

Each phase accepts exactly one class of artifact and refuses the others, so the
transcript cannot drift into an unbounded conversation. The properties that
matter are structural, not stylistic:

* **Bounded submissions.** Each participant may submit at most
  ``max_submissions_per_participant`` artifacts, and only kinds their role
  contract lets them author.
* **Every challenge is targeted.** A challenge must name a submission made in
  this meeting, and must carry the full seven-field disagreement structure.
* **No fabricated consensus.** :meth:`MeetingRunner.finalize` refuses to record
  an agreement on a point that still carries an unanswered challenge, and
  refuses to drop an unanswered challenge silently — it becomes a preserved
  disagreement on the mission.
* **Honest non-answers.** A meeting whose questions cannot be answered
  finalizes with outcome ``insufficient_evidence``, which is a legitimate
  result rather than a failure.
"""
from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Iterable

from saathi.agentdev.artifacts import (
    INSUFFICIENT_EVIDENCE,
    Artifact,
    ArtifactKind,
    ArtifactStore,
    make_artifact,
)
from saathi.agentdev.missions import DevMissionStore
from saathi.agentdev.roles import get_role, require_role

DEFAULT_MAX_SUBMISSIONS = 3


class MeetingType(str, Enum):
    RESEARCH_REVIEW = "research_review"
    ARCHITECTURE_COUNCIL = "architecture_council"
    IMPLEMENTATION_PLANNING = "implementation_planning"
    RED_TEAM_REVIEW = "red_team_review"
    EXECUTIVE_DECISION = "executive_decision"


#: Roles that must attend. A meeting missing one of these cannot be created —
#: a red-team review without security, or an architecture council without
#: testing, is theatre.
REQUIRED_PARTICIPANTS: dict[MeetingType, tuple[str, ...]] = {
    MeetingType.RESEARCH_REVIEW: (
        "research", "product-strategy", "architecture", "security-governance",
        "program-manager",
    ),
    MeetingType.ARCHITECTURE_COUNCIL: (
        "architecture", "backend-engineering", "frontend-engineering",
        "ai-model-systems", "security-governance", "testing-verification",
    ),
    MeetingType.IMPLEMENTATION_PLANNING: (
        "program-manager", "architecture", "testing-verification", "documentation",
    ),
    MeetingType.RED_TEAM_REVIEW: (
        "security-governance", "testing-verification", "code-review", "architecture",
    ),
    MeetingType.EXECUTIVE_DECISION: (
        "ceo", "program-manager", "product-strategy", "architecture",
        "security-governance", "testing-verification",
    ),
}

#: Implementation planning additionally requires the engineering agents actually
#: assigned to the mission; the caller supplies them.
ACCEPTS_ADDITIONAL_ENGINEERS = frozenset({MeetingType.IMPLEMENTATION_PLANNING})


class MeetingPhase(str, Enum):
    AGENDA = "agenda"
    COLLECTING = "collecting"
    CHALLENGING = "challenging"
    RESPONDING = "responding"
    SYNTHESIZING = "synthesizing"
    FINALIZED = "finalized"
    BLOCKED = "blocked"


PHASE_ORDER = (
    MeetingPhase.AGENDA,
    MeetingPhase.COLLECTING,
    MeetingPhase.CHALLENGING,
    MeetingPhase.RESPONDING,
    MeetingPhase.SYNTHESIZING,
    MeetingPhase.FINALIZED,
)

#: The one artifact kind each phase accepts.
PHASE_ACCEPTS: dict[MeetingPhase, frozenset[ArtifactKind]] = {
    MeetingPhase.AGENDA: frozenset(),
    MeetingPhase.COLLECTING: frozenset({
        ArtifactKind.RESEARCH_FINDINGS,
        ArtifactKind.PROPOSAL,
        ArtifactKind.ARCHITECTURE_DECISION,
        ArtifactKind.SECURITY_REVIEW,
        ArtifactKind.VERIFICATION_REPORT,
        ArtifactKind.CODE_REVIEW,
    }),
    MeetingPhase.CHALLENGING: frozenset({ArtifactKind.CHALLENGE}),
    MeetingPhase.RESPONDING: frozenset({ArtifactKind.RESPONSE}),
    MeetingPhase.SYNTHESIZING: frozenset(),
    MeetingPhase.FINALIZED: frozenset(),
    MeetingPhase.BLOCKED: frozenset(),
}


class MeetingOutcome(str, Enum):
    DECIDED = "decided"
    BLOCKED = "blocked"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class MeetingError(ValueError):
    def __init__(self, code: str, detail: str = ""):
        self.code = code
        self.detail = detail
        super().__init__(f"{code}" + (f" ({detail})" if detail else ""))


def new_meeting_id() -> str:
    return f"mtg_{uuid.uuid4().hex[:10]}"


@dataclass
class Meeting:
    meeting_id: str
    dev_mission_id: str
    meeting_type: str
    chair: str
    participants: list[str]
    questions: list[str]
    phase: str = MeetingPhase.AGENDA.value
    agenda_artifact_id: str = ""
    minutes_artifact_id: str = ""
    submissions: dict[str, list[str]] = field(default_factory=dict)
    challenges: list[str] = field(default_factory=list)
    responses: dict[str, str] = field(default_factory=dict)  # challenge id -> response id
    agreements: list[str] = field(default_factory=list)
    preserved_disagreements: list[dict[str, Any]] = field(default_factory=list)
    outcome: str = ""
    max_submissions_per_participant: int = DEFAULT_MAX_SUBMISSIONS
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    @property
    def meeting_phase(self) -> MeetingPhase:
        return MeetingPhase(self.phase)

    @property
    def all_submission_ids(self) -> list[str]:
        return [a for ids in self.submissions.values() for a in ids]

    @property
    def unanswered_challenges(self) -> list[str]:
        return [c for c in self.challenges if c not in self.responses]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Meeting":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in d.items() if k in known})


class MeetingRunner:
    """Drives one meeting through its phases over the artifact store."""

    def __init__(
        self,
        artifacts: ArtifactStore,
        missions: DevMissionStore,
        root: Path | str | None = None,
    ):
        self.artifacts = artifacts
        self.missions = missions
        self.root = Path(root) if root else Path(artifacts.root)

    # ---- persistence --------------------------------------------------------

    def _path(self, dev_mission_id: str, meeting_id: str) -> Path:
        return self.root / dev_mission_id / "meetings" / f"{meeting_id}.json"

    def _put(self, meeting: Meeting) -> Meeting:
        meeting.updated_at = time.time()
        path = self._path(meeting.dev_mission_id, meeting.meeting_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.stat().st_size > 0:
            path.with_suffix(".json.bak").write_bytes(path.read_bytes())
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(meeting.to_dict(), indent=2, default=str), encoding="utf-8"
        )
        os.replace(tmp, path)
        return meeting

    def get(self, dev_mission_id: str, meeting_id: str) -> Meeting | None:
        path = self._path(dev_mission_id, meeting_id)
        if not path.exists():
            return None
        return Meeting.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def require(self, dev_mission_id: str, meeting_id: str) -> Meeting:
        meeting = self.get(dev_mission_id, meeting_id)
        if meeting is None:
            raise MeetingError("unknown_meeting", meeting_id)
        return meeting

    def list(self, dev_mission_id: str) -> list[Meeting]:
        directory = self.root / dev_mission_id / "meetings"
        if not directory.exists():
            return []
        out = []
        for path in sorted(directory.glob("*.json")):
            try:
                out.append(
                    Meeting.from_dict(json.loads(path.read_text(encoding="utf-8")))
                )
            except json.JSONDecodeError:
                continue
        return sorted(out, key=lambda m: m.created_at)

    # ---- phase 1: agenda ----------------------------------------------------

    def create(
        self,
        *,
        dev_mission_id: str,
        meeting_type: MeetingType | str,
        chair: str,
        questions: list[str],
        repository_sha: str,
        extra_participants: Iterable[str] = (),
        max_submissions_per_participant: int = DEFAULT_MAX_SUBMISSIONS,
    ) -> Meeting:
        mission = self.missions.require(dev_mission_id)
        try:
            kind = MeetingType(meeting_type)
        except ValueError as exc:
            raise MeetingError("unknown_meeting_type", str(meeting_type)) from exc

        if not questions or any(not q.strip() for q in questions):
            raise MeetingError("agenda_without_questions", dev_mission_id)

        chair_role = get_role(chair)
        if chair_role is None:
            raise MeetingError("unknown_chair", chair)
        if not chair_role.has_capability("chair_meeting"):
            raise MeetingError("chair_cannot_chair", chair)

        required = REQUIRED_PARTICIPANTS[kind]
        extra = [p for p in extra_participants]
        for participant in extra:
            if get_role(participant) is None:
                raise MeetingError("unknown_participant", participant)
        if extra and kind not in ACCEPTS_ADDITIONAL_ENGINEERS:
            unexpected = [p for p in extra if p not in required]
            if unexpected:
                raise MeetingError(
                    "unexpected_participants", ",".join(sorted(unexpected))
                )
        participants = list(dict.fromkeys([*required, *extra]))

        if chair not in participants:
            raise MeetingError("chair_not_a_participant", chair)

        missing = [p for p in required if p not in participants]
        if missing:
            raise MeetingError("missing_required_participants", ",".join(missing))

        if max_submissions_per_participant < 1:
            raise MeetingError(
                "invalid_submission_bound", str(max_submissions_per_participant)
            )

        meeting = Meeting(
            meeting_id=new_meeting_id(),
            dev_mission_id=dev_mission_id,
            meeting_type=kind.value,
            chair=chair,
            participants=participants,
            questions=list(questions),
            max_submissions_per_participant=max_submissions_per_participant,
        )

        agenda = make_artifact(
            mission_id=dev_mission_id,
            kind=ArtifactKind.MEETING_AGENDA,
            authoring_agent=chair,
            repository_sha=repository_sha or mission.starting_sha,
            title=f"{kind.value} agenda",
            required_next_action="participants submit bounded evidence",
            payload={
                "meeting_id": meeting.meeting_id,
                "meeting_type": kind.value,
                "participants": participants,
                "questions": list(questions),
                "max_submissions_per_participant": max_submissions_per_participant,
            },
        )
        self.artifacts.put(agenda)
        meeting.agenda_artifact_id = agenda.artifact_id
        return self._put(meeting)

    # ---- phase transitions --------------------------------------------------

    def open_phase(
        self, dev_mission_id: str, meeting_id: str, phase: MeetingPhase | str, *, actor: str
    ) -> Meeting:
        meeting = self.require(dev_mission_id, meeting_id)
        if actor != meeting.chair:
            raise MeetingError("phase_change_by_non_chair", actor)
        target = MeetingPhase(phase) if not isinstance(phase, MeetingPhase) else phase
        current = meeting.meeting_phase
        if current in (MeetingPhase.FINALIZED, MeetingPhase.BLOCKED):
            raise MeetingError("meeting_already_closed", current.value)
        if target is MeetingPhase.BLOCKED:
            meeting.phase = target.value
            return self._put(meeting)
        if target not in PHASE_ORDER:
            raise MeetingError("invalid_phase", target.value)
        if PHASE_ORDER.index(target) != PHASE_ORDER.index(current) + 1:
            raise MeetingError(
                "phase_out_of_order", f"{current.value}->{target.value}"
            )
        if target is MeetingPhase.CHALLENGING and not meeting.all_submission_ids:
            raise MeetingError("no_submissions_collected", meeting_id)
        meeting.phase = target.value
        return self._put(meeting)

    # ---- phase 2: bounded submissions --------------------------------------

    def submit(
        self, dev_mission_id: str, meeting_id: str, artifact: Artifact
    ) -> Meeting:
        meeting = self.require(dev_mission_id, meeting_id)
        if meeting.meeting_phase is not MeetingPhase.COLLECTING:
            raise MeetingError("not_collecting", meeting.phase)
        author = artifact.authoring_agent
        if author not in meeting.participants:
            raise MeetingError("submission_from_non_participant", author)
        if artifact.mission_id != dev_mission_id:
            raise MeetingError("submission_for_other_mission", artifact.mission_id)
        if artifact.artifact_kind not in PHASE_ACCEPTS[MeetingPhase.COLLECTING]:
            raise MeetingError("kind_not_accepted_in_phase", artifact.kind)

        existing = meeting.submissions.setdefault(author, [])
        if len(existing) >= meeting.max_submissions_per_participant:
            raise MeetingError(
                "submission_bound_exceeded",
                f"{author}:{meeting.max_submissions_per_participant}",
            )
        self.artifacts.put(artifact)
        existing.append(artifact.artifact_id)
        return self._put(meeting)

    # ---- phase 3: challenges ------------------------------------------------

    def challenge(
        self, dev_mission_id: str, meeting_id: str, artifact: Artifact
    ) -> Meeting:
        meeting = self.require(dev_mission_id, meeting_id)
        if meeting.meeting_phase is not MeetingPhase.CHALLENGING:
            raise MeetingError("not_challenging", meeting.phase)
        if artifact.artifact_kind is not ArtifactKind.CHALLENGE:
            raise MeetingError("kind_not_accepted_in_phase", artifact.kind)
        if artifact.authoring_agent not in meeting.participants:
            raise MeetingError(
                "challenge_from_non_participant", artifact.authoring_agent
            )
        targets = [d for d in artifact.dependencies if d in meeting.all_submission_ids]
        if not targets:
            raise MeetingError("challenge_target_not_in_meeting", artifact.artifact_id)
        target_authors = {
            (self.artifacts.get(dev_mission_id, t) or artifact).authoring_agent
            for t in targets
        }
        if target_authors == {artifact.authoring_agent}:
            raise MeetingError("self_challenge", artifact.authoring_agent)
        self.artifacts.put(artifact)
        meeting.challenges.append(artifact.artifact_id)
        return self._put(meeting)

    # ---- phase 4: responses -------------------------------------------------

    def respond(
        self, dev_mission_id: str, meeting_id: str, artifact: Artifact
    ) -> Meeting:
        meeting = self.require(dev_mission_id, meeting_id)
        if meeting.meeting_phase is not MeetingPhase.RESPONDING:
            raise MeetingError("not_responding", meeting.phase)
        if artifact.artifact_kind is not ArtifactKind.RESPONSE:
            raise MeetingError("kind_not_accepted_in_phase", artifact.kind)
        if artifact.authoring_agent not in meeting.participants:
            raise MeetingError(
                "response_from_non_participant", artifact.authoring_agent
            )
        targets = [d for d in artifact.dependencies if d in meeting.challenges]
        if not targets:
            raise MeetingError("response_target_not_a_challenge", artifact.artifact_id)
        for target in targets:
            if target in meeting.responses:
                raise MeetingError("challenge_already_answered", target)
        self.artifacts.put(artifact)
        for target in targets:
            meeting.responses[target] = artifact.artifact_id
        return self._put(meeting)

    # ---- phase 5: minutes ---------------------------------------------------

    def finalize(
        self,
        dev_mission_id: str,
        meeting_id: str,
        *,
        actor: str,
        agreements: list[str],
        outcome: MeetingOutcome | str,
        repository_sha: str,
        contested_points: dict[str, str] | None = None,
    ) -> tuple[Meeting, Artifact]:
        """Produce minutes and either a decision or a blocked status.

        ``contested_points`` maps an agreement text to the challenge id that
        contests it. Any agreement so mapped whose challenge is unanswered is
        refused: consensus is not recorded over an open objection.
        """
        meeting = self.require(dev_mission_id, meeting_id)
        if meeting.meeting_phase is not MeetingPhase.SYNTHESIZING:
            raise MeetingError("not_synthesizing", meeting.phase)
        if actor != meeting.chair:
            raise MeetingError("finalize_by_non_chair", actor)
        try:
            result = MeetingOutcome(outcome)
        except ValueError as exc:
            raise MeetingError("unknown_outcome", str(outcome)) from exc

        contested = dict(contested_points or {})
        unanswered = set(meeting.unanswered_challenges)

        for agreement in agreements:
            challenge_id = contested.get(agreement)
            if challenge_id and challenge_id in unanswered:
                raise MeetingError(
                    "agreement_over_unanswered_challenge",
                    f"{challenge_id}",
                )

        # Unanswered challenges are never dropped. They become preserved
        # disagreements on the meeting and on the mission.
        preserved: list[dict[str, Any]] = []
        for challenge_id in meeting.unanswered_challenges:
            challenge = self.artifacts.get(dev_mission_id, challenge_id)
            payload = (challenge.payload if challenge else {}) or {}
            preserved.append({
                "challenge_id": challenge_id,
                "raised_by": challenge.authoring_agent if challenge else "",
                "claim": payload.get("claim", ""),
                "failure_mode": payload.get("failure_mode", ""),
                "risk": payload.get("risk", ""),
                "decision_required": payload.get("decision_required", ""),
                "status": "unanswered",
            })

        if result is MeetingOutcome.DECIDED and preserved:
            raise MeetingError(
                "decided_with_unanswered_challenges",
                ",".join(p["challenge_id"] for p in preserved),
            )

        if result is MeetingOutcome.INSUFFICIENT_EVIDENCE and agreements:
            raise MeetingError("insufficient_evidence_with_agreements", meeting_id)

        minutes = make_artifact(
            mission_id=dev_mission_id,
            kind=ArtifactKind.MEETING_MINUTES,
            authoring_agent=actor,
            repository_sha=repository_sha,
            title=f"{meeting.meeting_type} minutes",
            required_next_action=(
                "mission advances" if result is MeetingOutcome.DECIDED
                else "unresolved points return to the mission"
            ),
            dependencies=[meeting.agenda_artifact_id, *meeting.all_submission_ids],
            unresolved_questions=[
                p["decision_required"] for p in preserved if p["decision_required"]
            ],
            payload={
                "meeting_id": meeting_id,
                "meeting_type": meeting.meeting_type,
                "participants": meeting.participants,
                "questions": meeting.questions,
                "submissions": meeting.submissions,
                "agreements": list(agreements),
                "disagreements": preserved,
                "answered_challenges": dict(meeting.responses),
                "outcome": result.value,
            },
        )
        self.artifacts.put(minutes)

        meeting.agreements = list(agreements)
        meeting.preserved_disagreements = preserved
        meeting.outcome = result.value
        meeting.minutes_artifact_id = minutes.artifact_id
        meeting.phase = (
            MeetingPhase.FINALIZED.value if result is not MeetingOutcome.BLOCKED
            else MeetingPhase.BLOCKED.value
        )
        self._put(meeting)

        # Link the result back onto the mission.
        mission = self.missions.require(dev_mission_id)
        for entry in preserved:
            if entry["challenge_id"] not in mission.unresolved_disagreements:
                mission.unresolved_disagreements.append(entry["challenge_id"])
        mission.history.append({
            "at": time.time(),
            "event": "meeting_finalized",
            "meeting_id": meeting_id,
            "meeting_type": meeting.meeting_type,
            "outcome": result.value,
            "minutes": minutes.artifact_id,
            "preserved_disagreements": len(preserved),
        })
        self.missions.put(mission)

        return meeting, minutes

    # ---- reporting ----------------------------------------------------------

    def status(self, dev_mission_id: str, meeting_id: str) -> dict[str, Any]:
        meeting = self.require(dev_mission_id, meeting_id)
        return {
            "meeting_id": meeting.meeting_id,
            "dev_mission_id": meeting.dev_mission_id,
            "meeting_type": meeting.meeting_type,
            "phase": meeting.phase,
            "chair": meeting.chair,
            "participants": meeting.participants,
            "questions": meeting.questions,
            "submission_counts": {
                agent: len(ids) for agent, ids in meeting.submissions.items()
            },
            "submission_bound": meeting.max_submissions_per_participant,
            "challenges": meeting.challenges,
            "unanswered_challenges": meeting.unanswered_challenges,
            "agreements": meeting.agreements,
            "preserved_disagreements": meeting.preserved_disagreements,
            "outcome": meeting.outcome or None,
            "minutes_artifact_id": meeting.minutes_artifact_id or None,
        }


def disagreement_template() -> dict[str, str]:
    """The seven fields a challenge must carry, in the mandated order."""
    return {
        "claim": "",
        "evidence": "",
        "counterargument": "",
        "failure_mode": "",
        "risk": "",
        "alternative": "",
        "decision_required": "",
    }


def insufficient_evidence_marker() -> str:
    return INSUFFICIENT_EVIDENCE


def required_participants(meeting_type: MeetingType | str) -> tuple[str, ...]:
    kind = MeetingType(meeting_type)
    for role_id in REQUIRED_PARTICIPANTS[kind]:
        require_role(role_id)  # fail loudly if the registry drifts
    return REQUIRED_PARTICIPANTS[kind]
