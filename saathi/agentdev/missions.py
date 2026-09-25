"""M347 — Development missions.

A *development mission* is not a product mission. ``saathi/missions/`` and
``saathi/platform/mission_runtime/`` own a user's goal being executed by the
OS; this owns a question being answered by a council of development agents.
The identifier is therefore ``dev_mission_id``, never ``mission_id``, and the
records live in their own store — duplicate-source-of-truth rule 4 from ADR-012.

The lifecycle is explicit and total: every transition is declared, and
:meth:`DevMissionStore.advance` refuses one that is not. Skipping a gate is not
possible by advancing twice, because each state names the gates that must have
passed to leave it.
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
from typing import Any

_MISSION_RE = re.compile(r"^dm[a-z0-9]{2,24}$")
_SHA_RE = re.compile(r"^[0-9a-f]{7,40}$")


class MissionState(str, Enum):
    INTAKE = "intake"
    DECOMPOSED = "decomposed"
    RESEARCH = "research"
    DESIGN = "design"
    SECURITY_REVIEW = "security_review"
    IMPLEMENTATION_READY = "implementation_ready"
    IN_IMPLEMENTATION = "in_implementation"
    VERIFICATION = "verification"
    EXECUTIVE_DECISION = "executive_decision"
    OWNER_APPROVAL = "owner_approval"
    CLOSED = "closed"
    BLOCKED = "blocked"
    ABANDONED = "abandoned"


TERMINAL_STATES = frozenset({MissionState.CLOSED, MissionState.ABANDONED})


class Gate(str, Enum):
    RESEARCH_COMPLETENESS = "research_completeness"
    ARCHITECTURE_APPROVAL = "architecture_approval"
    SECURITY_APPROVAL = "security_approval"
    IMPLEMENTATION_READINESS = "implementation_readiness"
    CODE_REVIEW = "code_review"
    AUTOMATED_TESTING = "automated_testing"
    NEGATIVE_PATH_TESTING = "negative_path_testing"
    RED_TEAM_REVIEW = "red_team_review"
    EXECUTIVE_SYNTHESIS = "executive_synthesis"
    OWNER_APPROVAL = "owner_approval"
    INTEGRATION_CANDIDACY = "integration_candidacy"


#: The gates that must have passed before a mission may *leave* each state.
#: A mission cannot skip a gate by advancing twice: the target state's own
#: prerequisites are checked on every hop.
STATE_EXIT_GATES: dict[MissionState, tuple[Gate, ...]] = {
    MissionState.INTAKE: (),
    MissionState.DECOMPOSED: (),
    MissionState.RESEARCH: (Gate.RESEARCH_COMPLETENESS,),
    MissionState.DESIGN: (Gate.ARCHITECTURE_APPROVAL,),
    MissionState.SECURITY_REVIEW: (Gate.SECURITY_APPROVAL,),
    MissionState.IMPLEMENTATION_READY: (Gate.IMPLEMENTATION_READINESS,),
    MissionState.IN_IMPLEMENTATION: (Gate.CODE_REVIEW,),
    MissionState.VERIFICATION: (
        Gate.AUTOMATED_TESTING,
        Gate.NEGATIVE_PATH_TESTING,
        Gate.RED_TEAM_REVIEW,
    ),
    MissionState.EXECUTIVE_DECISION: (Gate.EXECUTIVE_SYNTHESIS,),
    MissionState.OWNER_APPROVAL: (Gate.OWNER_APPROVAL,),
    MissionState.CLOSED: (),
    MissionState.BLOCKED: (),
    MissionState.ABANDONED: (),
}

ALLOWED_TRANSITIONS: dict[MissionState, frozenset[MissionState]] = {
    MissionState.INTAKE: frozenset({
        MissionState.DECOMPOSED, MissionState.BLOCKED, MissionState.ABANDONED,
    }),
    MissionState.DECOMPOSED: frozenset({
        MissionState.RESEARCH, MissionState.BLOCKED, MissionState.ABANDONED,
    }),
    MissionState.RESEARCH: frozenset({
        MissionState.DESIGN, MissionState.BLOCKED, MissionState.ABANDONED,
    }),
    MissionState.DESIGN: frozenset({
        MissionState.SECURITY_REVIEW, MissionState.RESEARCH,
        MissionState.BLOCKED, MissionState.ABANDONED,
    }),
    MissionState.SECURITY_REVIEW: frozenset({
        MissionState.IMPLEMENTATION_READY, MissionState.EXECUTIVE_DECISION,
        MissionState.DESIGN, MissionState.BLOCKED, MissionState.ABANDONED,
    }),
    MissionState.IMPLEMENTATION_READY: frozenset({
        MissionState.IN_IMPLEMENTATION, MissionState.BLOCKED, MissionState.ABANDONED,
    }),
    MissionState.IN_IMPLEMENTATION: frozenset({
        MissionState.VERIFICATION, MissionState.BLOCKED, MissionState.ABANDONED,
    }),
    MissionState.VERIFICATION: frozenset({
        MissionState.EXECUTIVE_DECISION, MissionState.IN_IMPLEMENTATION,
        MissionState.BLOCKED, MissionState.ABANDONED,
    }),
    MissionState.EXECUTIVE_DECISION: frozenset({
        MissionState.OWNER_APPROVAL, MissionState.CLOSED,
        MissionState.BLOCKED, MissionState.ABANDONED,
    }),
    MissionState.OWNER_APPROVAL: frozenset({
        MissionState.CLOSED, MissionState.BLOCKED, MissionState.ABANDONED,
    }),
    MissionState.CLOSED: frozenset(),
    MissionState.BLOCKED: frozenset({
        MissionState.RESEARCH, MissionState.DESIGN, MissionState.SECURITY_REVIEW,
        MissionState.IN_IMPLEMENTATION, MissionState.VERIFICATION,
        MissionState.EXECUTIVE_DECISION, MissionState.ABANDONED,
    }),
    MissionState.ABANDONED: frozenset(),
}


class MissionError(ValueError):
    def __init__(self, code: str, detail: str = ""):
        self.code = code
        self.detail = detail
        super().__init__(f"{code}" + (f" ({detail})" if detail else ""))


def new_mission_id() -> str:
    """``dm`` + 8 hex characters. Deliberately hyphen-free (see worktrees)."""
    return f"dm{uuid.uuid4().hex[:8]}"


@dataclass
class GateRecord:
    """One gate outcome. Written only by :mod:`saathi.agentdev.gates`."""

    gate: str
    status: str = "pending"  # pending | passed | failed | blocked | waived_by_owner
    approver: str = ""
    subject_author: str = ""
    evidence_artifact_ids: list[str] = field(default_factory=list)
    reason: str = ""
    decided_at: float = 0.0

    @property
    def passed(self) -> bool:
        return self.status in ("passed", "waived_by_owner")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "GateRecord":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in d.items() if k in known})


@dataclass
class DevMission:
    dev_mission_id: str
    title: str
    objective: str
    created_by: str = "ceo"
    state: str = MissionState.INTAKE.value
    starting_sha: str = ""
    participants: list[str] = field(default_factory=list)
    gates: dict[str, GateRecord] = field(default_factory=dict)
    open_vetoes: list[str] = field(default_factory=list)
    unresolved_disagreements: list[str] = field(default_factory=list)
    terminal_verdict: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    history: list[dict[str, Any]] = field(default_factory=list)

    @property
    def mission_state(self) -> MissionState:
        return MissionState(self.state)

    def gate(self, gate: Gate | str) -> GateRecord:
        key = gate.value if isinstance(gate, Gate) else str(gate)
        return self.gates.get(key) or GateRecord(gate=key)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["gates"] = {
            k: (v.to_dict() if isinstance(v, GateRecord) else v)
            for k, v in self.gates.items()
        }
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "DevMission":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        payload = {k: v for k, v in d.items() if k in known}
        payload["gates"] = {
            k: (v if isinstance(v, GateRecord) else GateRecord.from_dict(v))
            for k, v in (d.get("gates") or {}).items()
        }
        return cls(**payload)


def can_transition(current: str | MissionState, new: str | MissionState) -> bool:
    cur = MissionState(current) if not isinstance(current, MissionState) else current
    nxt = MissionState(new) if not isinstance(new, MissionState) else new
    if cur == nxt:
        return True
    return nxt in ALLOWED_TRANSITIONS.get(cur, frozenset())


class DevMissionStore:
    """One JSON file per mission under ``<root>/<dev_mission_id>/mission.json``."""

    def __init__(self, root: Path | str):
        self.root = Path(root)

    def mission_dir(self, dev_mission_id: str) -> Path:
        if not _MISSION_RE.match(dev_mission_id or ""):
            raise MissionError("invalid_mission_id", dev_mission_id)
        return self.root / dev_mission_id

    def _path(self, dev_mission_id: str) -> Path:
        return self.mission_dir(dev_mission_id) / "mission.json"

    def create(
        self,
        *,
        title: str,
        objective: str,
        starting_sha: str,
        created_by: str = "ceo",
        participants: list[str] | None = None,
        dev_mission_id: str | None = None,
    ) -> DevMission:
        mission_id = dev_mission_id or new_mission_id()
        if not _MISSION_RE.match(mission_id):
            raise MissionError("invalid_mission_id", mission_id)
        if self._path(mission_id).exists():
            raise MissionError("duplicate_mission_id", mission_id)
        if not title.strip():
            raise MissionError("missing_title")
        if not objective.strip():
            raise MissionError("missing_objective")
        if not _SHA_RE.match(starting_sha or ""):
            raise MissionError("invalid_starting_sha", starting_sha)

        mission = DevMission(
            dev_mission_id=mission_id,
            title=title,
            objective=objective,
            created_by=created_by,
            starting_sha=starting_sha,
            participants=list(participants or []),
        )
        mission.history.append(
            {"at": time.time(), "event": "created", "by": created_by}
        )
        return self.put(mission)

    def put(self, mission: DevMission) -> DevMission:
        mission.updated_at = time.time()
        path = self._path(mission.dev_mission_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.stat().st_size > 0:
            path.with_suffix(".json.bak").write_bytes(path.read_bytes())
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(mission.to_dict(), indent=2, default=str), encoding="utf-8"
        )
        os.replace(tmp, path)
        return mission

    def get(self, dev_mission_id: str) -> DevMission | None:
        path = self._path(dev_mission_id)
        if not path.exists():
            return None
        try:
            return DevMission.from_dict(json.loads(path.read_text(encoding="utf-8")))
        except json.JSONDecodeError as exc:
            raise MissionError("mission_corrupt", str(path)) from exc

    def require(self, dev_mission_id: str) -> DevMission:
        mission = self.get(dev_mission_id)
        if mission is None:
            raise MissionError("unknown_mission", dev_mission_id)
        return mission

    def list(self) -> list[DevMission]:
        if not self.root.exists():
            return []
        out: list[DevMission] = []
        for directory in sorted(self.root.iterdir()):
            path = directory / "mission.json"
            if path.is_file():
                try:
                    out.append(
                        DevMission.from_dict(
                            json.loads(path.read_text(encoding="utf-8"))
                        )
                    )
                except json.JSONDecodeError:
                    continue
        return sorted(out, key=lambda m: m.created_at)

    # ---- lifecycle ----------------------------------------------------------

    def advance(
        self,
        dev_mission_id: str,
        new_state: MissionState | str,
        *,
        actor: str,
        reason: str = "",
    ) -> DevMission:
        """Move a mission forward. Fail-closed on every precondition."""
        mission = self.require(dev_mission_id)
        target = MissionState(new_state) if not isinstance(new_state, MissionState) else new_state
        current = mission.mission_state

        if not can_transition(current, target):
            raise MissionError(
                "invalid_state_transition", f"{current.value}->{target.value}"
            )

        # Leaving a state requires its exit gates, unless the mission is being
        # blocked or abandoned — those are always reachable.
        if target not in (MissionState.BLOCKED, MissionState.ABANDONED):
            unmet = [
                g.value for g in STATE_EXIT_GATES.get(current, ())
                if not mission.gate(g).passed
            ]
            if unmet:
                raise MissionError("gate_not_passed", ",".join(unmet))

            if mission.open_vetoes:
                raise MissionError("security_veto_open", ",".join(mission.open_vetoes))

        if target is MissionState.CLOSED and not mission.terminal_verdict:
            raise MissionError("close_without_terminal_verdict", dev_mission_id)

        mission.state = target.value
        mission.history.append({
            "at": time.time(),
            "event": "state_change",
            "from": current.value,
            "to": target.value,
            "by": actor,
            "reason": reason,
        })
        return self.put(mission)

    def record_gate(self, dev_mission_id: str, record: GateRecord) -> DevMission:
        """Persist a gate outcome. Called only by :mod:`saathi.agentdev.gates`."""
        mission = self.require(dev_mission_id)
        try:
            Gate(record.gate)
        except ValueError as exc:
            raise MissionError("unknown_gate", record.gate) from exc
        mission.gates[record.gate] = record
        mission.history.append({
            "at": time.time(),
            "event": "gate",
            "gate": record.gate,
            "status": record.status,
            "approver": record.approver,
        })
        return self.put(mission)

    def open_veto(self, dev_mission_id: str, veto_id: str, *, actor: str) -> DevMission:
        mission = self.require(dev_mission_id)
        if veto_id not in mission.open_vetoes:
            mission.open_vetoes.append(veto_id)
        mission.history.append(
            {"at": time.time(), "event": "veto_opened", "veto": veto_id, "by": actor}
        )
        return self.put(mission)

    def withdraw_veto(
        self, dev_mission_id: str, veto_id: str, *, actor: str, evidence: str
    ) -> DevMission:
        """Only the veto's author may withdraw it, and only against evidence."""
        mission = self.require(dev_mission_id)
        if veto_id not in mission.open_vetoes:
            raise MissionError("unknown_veto", veto_id)
        if not evidence.strip():
            raise MissionError("veto_withdrawal_without_evidence", veto_id)
        if actor != "security-governance":
            raise MissionError("veto_withdrawal_by_non_author", actor)
        mission.open_vetoes.remove(veto_id)
        mission.history.append({
            "at": time.time(),
            "event": "veto_withdrawn",
            "veto": veto_id,
            "by": actor,
            "evidence": evidence,
        })
        return self.put(mission)

    def set_terminal_verdict(
        self, dev_mission_id: str, verdict: str, *, actor: str
    ) -> DevMission:
        from saathi.agentdev.artifacts import TerminalVerdict

        mission = self.require(dev_mission_id)
        try:
            TerminalVerdict(verdict)
        except ValueError as exc:
            raise MissionError("invalid_terminal_verdict", verdict) from exc
        if actor != "ceo":
            raise MissionError("verdict_not_authored_by_ceo", actor)
        if (
            verdict == TerminalVerdict.APPROVED_FOR_IMPLEMENTATION.value
            and mission.open_vetoes
        ):
            raise MissionError(
                "approval_with_open_veto", ",".join(mission.open_vetoes)
            )
        if (
            verdict == TerminalVerdict.APPROVED_FOR_IMPLEMENTATION.value
            and mission.unresolved_disagreements
        ):
            raise MissionError(
                "approval_with_unresolved_disagreements",
                ",".join(mission.unresolved_disagreements),
            )
        mission.terminal_verdict = verdict
        mission.history.append({
            "at": time.time(), "event": "verdict", "verdict": verdict, "by": actor,
        })
        return self.put(mission)

    def status(self, dev_mission_id: str) -> dict[str, Any]:
        mission = self.require(dev_mission_id)
        current = mission.mission_state
        unmet = [
            g.value for g in STATE_EXIT_GATES.get(current, ())
            if not mission.gate(g).passed
        ]
        return {
            "dev_mission_id": mission.dev_mission_id,
            "title": mission.title,
            "state": mission.state,
            "starting_sha": mission.starting_sha,
            "participants": mission.participants,
            "terminal_verdict": mission.terminal_verdict or None,
            "open_vetoes": mission.open_vetoes,
            "unresolved_disagreements": mission.unresolved_disagreements,
            "gates": {k: v.to_dict() for k, v in mission.gates.items()},
            "unmet_exit_gates": unmet,
            "can_advance": not unmet and not mission.open_vetoes,
            "next_states": sorted(
                s.value for s in ALLOWED_TRANSITIONS.get(current, frozenset())
            ),
        }
