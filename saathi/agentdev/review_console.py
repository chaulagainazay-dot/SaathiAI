"""M358 — Human review and evidence console.

The owner-facing surface. It assembles everything needed to judge one mission
into a single packet, and it records the owner's decision as an entry in an
append-only, hash-chained ledger.

**Four actions, and no fifth.** ``approve``, ``reject``, ``request_changes``,
``needs_research``. There is no merge, no push, no deploy and no provider verb
in this module — those words are not implemented here, and a test asserts the
names are absent.

**Immutable by construction, not by promise.** Every decision appends one line
to ``owner_review.jsonl``. Each line carries the hash of the line before it, so
editing or deleting any earlier decision breaks the chain and
:meth:`OwnerDecisionLedger.verify_chain` says exactly where. There is no update
method and no delete method.

**Only the owner decides.** An action recorded by any other actor is refused.
The ``owner_approval`` gate was owner-only from M349; this milestone gives the
owner the means to satisfy it without giving anyone else the means.

**No invented confidence.** The packet reports confidence *signals* — counts a
reader can check — and states plainly that no scalar score is computed. A
number nobody can derive is worse than no number.
"""
from __future__ import annotations

import hashlib
import html
import json
import os
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from saathi.agentdev.artifacts import (
    ArtifactKind,
    ArtifactStore,
    make_artifact,
)
from saathi.agentdev.gates import GateEngine, GateError
from saathi.agentdev.missions import DevMissionStore, Gate, MissionError
from saathi.agentdev.resources import ceiling_report
from saathi.agentdev.settings import AgentDevSettings, load_settings

REVIEW_VERSION = "agentdev.review_console.v1"
OWNER = "owner"
LEDGER_FILENAME = "owner_review.jsonl"

#: Verbs this surface does not have. Named so the absence is checkable.
ABSENT_VERBS = ("merge", "push", "deploy", "release", "publish", "rollout")


class OwnerAction(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"
    REQUEST_CHANGES = "request_changes"
    NEEDS_RESEARCH = "needs_research"


#: What each action means for the mission, stated once so the console, the CLI
#: and the docs cannot drift apart.
ACTION_EFFECT: dict[OwnerAction, str] = {
    OwnerAction.APPROVE: (
        "Records an owner_approval artifact and passes the owner-only gate. "
        "Nothing is merged, pushed or deployed."
    ),
    OwnerAction.REJECT: (
        "Records a failed owner_approval gate with the owner's reason. The "
        "mission cannot close on this path."
    ),
    OwnerAction.REQUEST_CHANGES: (
        "Records the request. No gate changes; the mission returns to its "
        "authors with the owner's reason on the record."
    ),
    OwnerAction.NEEDS_RESEARCH: (
        "Records that the evidence is insufficient to decide. No gate changes."
    ),
}


class ReviewError(ValueError):
    def __init__(self, code: str, detail: str = ""):
        self.code = code
        self.detail = detail
        super().__init__(f"{code}" + (f" ({detail})" if detail else ""))


# --------------------------------------------------------------------------
# The ledger
# --------------------------------------------------------------------------


@dataclass
class OwnerDecision:
    """One immutable decision. ``entry_hash`` covers every other field."""

    seq: int
    at: float
    action: str
    dev_mission_id: str
    actor: str
    rationale: str
    reviewed_artifact_ids: list[str] = field(default_factory=list)
    remaining_risks_acknowledged: list[str] = field(default_factory=list)
    prev_hash: str = ""
    entry_hash: str = ""

    def payload(self) -> dict[str, Any]:
        """Everything the hash covers, in a stable order."""
        return {
            "seq": self.seq,
            "at": self.at,
            "action": self.action,
            "dev_mission_id": self.dev_mission_id,
            "actor": self.actor,
            "rationale": self.rationale,
            "reviewed_artifact_ids": list(self.reviewed_artifact_ids),
            "remaining_risks_acknowledged": list(self.remaining_risks_acknowledged),
            "prev_hash": self.prev_hash,
        }

    def compute_hash(self) -> str:
        return hashlib.sha256(
            json.dumps(self.payload(), sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "OwnerDecision":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in d.items() if k in known})


class OwnerDecisionLedger:
    """Append-only, hash-chained. No update method, no delete method."""

    def __init__(self, root: Path | str, dev_mission_id: str):
        self.root = Path(root)
        self.dev_mission_id = dev_mission_id

    @property
    def path(self) -> Path:
        return self.root / self.dev_mission_id / LEDGER_FILENAME

    def entries(self) -> list[OwnerDecision]:
        if not self.path.exists():
            return []
        out: list[OwnerDecision] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                out.append(OwnerDecision.from_dict(json.loads(line)))
            except (json.JSONDecodeError, TypeError) as exc:
                raise ReviewError("ledger_corrupt", f"{self.path}: {exc}") from exc
        return out

    def append(self, decision: OwnerDecision) -> OwnerDecision:
        """Append one line. The only write this class performs."""
        existing = self.entries()
        decision.seq = len(existing) + 1
        decision.prev_hash = existing[-1].entry_hash if existing else ""
        decision.entry_hash = decision.compute_hash()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Append mode with an explicit flush: a partial write must not silently
        # truncate the decisions already on record.
        with open(self.path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(decision.to_dict(), sort_keys=True, default=str) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        return decision

    def verify_chain(self) -> dict[str, Any]:
        """Recompute every hash and every link. Names the first break."""
        entries = self.entries()
        previous = ""
        for index, entry in enumerate(entries, start=1):
            if entry.seq != index:
                return {
                    "intact": False, "entries": len(entries),
                    "broken_at": index, "reason": f"sequence jumped to {entry.seq}",
                }
            if entry.prev_hash != previous:
                return {
                    "intact": False, "entries": len(entries),
                    "broken_at": index, "reason": "prev_hash does not match the entry before it",
                }
            if entry.compute_hash() != entry.entry_hash:
                return {
                    "intact": False, "entries": len(entries),
                    "broken_at": index, "reason": "entry content does not match its hash",
                }
            previous = entry.entry_hash
        return {
            "intact": True, "entries": len(entries),
            "head": previous or None,
            "note": "Each entry hashes the one before it; editing any line breaks the chain.",
        }


# --------------------------------------------------------------------------
# Recording a decision
# --------------------------------------------------------------------------


def record_owner_action(
    settings: AgentDevSettings,
    dev_mission_id: str,
    action: OwnerAction | str,
    *,
    actor: str,
    rationale: str,
    reviewed_artifact_ids: list[str] | None = None,
    acknowledged_risks: list[str] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Record one owner decision. Fail-closed on every precondition."""
    try:
        owner_action = OwnerAction(action)
    except ValueError as exc:
        raise ReviewError("unknown_action", str(action)) from exc
    if actor != OWNER:
        raise ReviewError("action_not_by_owner", actor)
    if not rationale.strip():
        raise ReviewError("action_without_rationale", owner_action.value)

    root = settings.store_path()
    missions = DevMissionStore(root)
    artifacts = ArtifactStore(root)
    mission = missions.require(dev_mission_id)

    reviewed = list(reviewed_artifact_ids or [])
    for artifact_id in reviewed:
        if artifacts.get(dev_mission_id, artifact_id) is None:
            raise ReviewError("reviewed_artifact_not_found", artifact_id)

    risks = list(acknowledged_risks or [])
    outstanding = list(mission.unresolved_disagreements) + list(mission.open_vetoes)
    if owner_action is OwnerAction.APPROVE:
        if mission.open_vetoes:
            raise ReviewError("approval_with_open_veto", ",".join(mission.open_vetoes))
        unacknowledged = [r for r in outstanding if r not in risks]
        if unacknowledged:
            raise ReviewError(
                "unacknowledged_remaining_risks", ",".join(unacknowledged)
            )

    if dry_run:
        return {
            "dry_run": True,
            "would_record": owner_action.value,
            "effect": ACTION_EFFECT[owner_action],
            "dev_mission_id": dev_mission_id,
            "outstanding_risks": outstanding,
        }

    gate_outcome: dict[str, Any] = {"changed": False}
    if owner_action is OwnerAction.APPROVE:
        gate_outcome = _pass_owner_gate(artifacts, missions, mission, rationale, risks)
    elif owner_action is OwnerAction.REJECT:
        gate_outcome = _fail_owner_gate(artifacts, missions, mission, rationale)

    ledger = OwnerDecisionLedger(root, dev_mission_id)
    decision = ledger.append(OwnerDecision(
        seq=0, at=time.time(), action=owner_action.value,
        dev_mission_id=dev_mission_id, actor=actor, rationale=rationale,
        reviewed_artifact_ids=reviewed, remaining_risks_acknowledged=risks,
    ))
    return {
        "recorded": decision.to_dict(),
        "effect": ACTION_EFFECT[owner_action],
        "gate": gate_outcome,
        "chain": ledger.verify_chain(),
    }


def _owner_subject(mission: Any) -> str:
    """Whose work the owner is judging. The CEO authors the synthesis."""
    record = mission.gate(Gate.EXECUTIVE_SYNTHESIS)
    return record.subject_author or "ceo"


def _pass_owner_gate(
    artifacts: ArtifactStore, missions: DevMissionStore, mission: Any,
    rationale: str, risks: list[str],
) -> dict[str, Any]:
    approval = make_artifact(
        mission_id=mission.dev_mission_id,
        kind=ArtifactKind.OWNER_APPROVAL,
        authoring_agent=OWNER,
        repository_sha=mission.starting_sha,
        title="Owner approval",
        required_next_action="the owner decides what happens outside this system",
        body=rationale,
        payload={
            "approved": True,
            "rationale": rationale,
            "remaining_risks_acknowledged": risks,
        },
    )
    artifacts.put(approval)
    try:
        _, decision = GateEngine(artifacts, missions).pass_gate(
            mission.dev_mission_id,
            Gate.OWNER_APPROVAL,
            approver=OWNER,
            subject_author=_owner_subject(mission),
            evidence_artifact_ids=[approval.artifact_id],
            reason=rationale,
        )
    except GateError as exc:
        return {
            "changed": False, "gate": Gate.OWNER_APPROVAL.value,
            "refused": f"{exc.code}: {exc.detail}",
            "artifact_id": approval.artifact_id,
        }
    return {
        "changed": True, "gate": Gate.OWNER_APPROVAL.value, "status": "passed",
        "artifact_id": approval.artifact_id, "warnings": decision.warnings,
    }


def _fail_owner_gate(
    artifacts: ArtifactStore, missions: DevMissionStore, mission: Any, rationale: str
) -> dict[str, Any]:
    try:
        GateEngine(artifacts, missions).fail_gate(
            mission.dev_mission_id,
            Gate.OWNER_APPROVAL,
            approver=OWNER,
            subject_author=_owner_subject(mission),
            reason=rationale,
        )
    except (GateError, MissionError) as exc:
        return {
            "changed": False, "gate": Gate.OWNER_APPROVAL.value,
            "refused": f"{getattr(exc, 'code', exc)}",
        }
    return {"changed": True, "gate": Gate.OWNER_APPROVAL.value, "status": "failed"}


# --------------------------------------------------------------------------
# The review packet
# --------------------------------------------------------------------------


def _evidence_file(repo_root: Path, name: str) -> dict[str, Any] | None:
    path = repo_root / "docs" / "evidence" / "m352_m359" / name
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def build_review_packet(
    dev_mission_id: str, settings: AgentDevSettings | None = None
) -> dict[str, Any]:
    """Everything the owner needs to judge one mission. Pure read."""
    settings = settings or load_settings()
    root = settings.store_path()
    repo_root = Path(settings.repo_root)
    missions = DevMissionStore(root)
    artifacts = ArtifactStore(root)
    mission = missions.require(dev_mission_id)
    rows = artifacts.list(dev_mission_id)

    outputs = [
        {
            "artifact_id": a.artifact_id,
            "kind": a.kind,
            "author": a.authoring_agent,
            "title": a.title,
            "status": a.status,
            "required_next_action": a.required_next_action,
            "claims": len(a.claims),
            "limitations": list(a.limitations),
            "unresolved_questions": list(a.unresolved_questions),
            "produced_by_model": bool((a.payload or {}).get("produced_by") == "model"),
            "substituted": (a.payload or {}).get("substituted"),
            "created_at": a.created_at,
        }
        for a in rows
    ]

    review_kinds = (
        ArtifactKind.CHALLENGE, ArtifactKind.RESPONSE, ArtifactKind.CODE_REVIEW,
        ArtifactKind.SECURITY_REVIEW, ArtifactKind.MEETING_MINUTES,
    )
    comments = [
        {
            "artifact_id": a.artifact_id,
            "kind": a.kind,
            "author": a.authoring_agent,
            "title": a.title,
            "decision_required": (a.payload or {}).get("decision_required", ""),
            "targets": list(a.dependencies),
        }
        for a in rows if a.artifact_kind in review_kinds
    ]

    ledger = OwnerDecisionLedger(root, dev_mission_id)
    decisions = ledger.entries()

    lineage = [
        {"from": dep, "to": a.artifact_id, "kind": a.kind}
        for a in rows for dep in a.dependencies
    ]

    verification = [
        {
            "artifact_id": a.artifact_id,
            "results": (a.payload or {}).get("results", []),
            "negative_paths": (a.payload or {}).get("negative_paths", []),
            "not_run": (a.payload or {}).get("not_run", []),
        }
        for a in rows if a.artifact_kind is ArtifactKind.VERIFICATION_REPORT
    ]

    decision_artifacts = [
        a for a in rows
        if a.artifact_kind in (ArtifactKind.EXECUTIVE_DECISION, ArtifactKind.FINAL_SYNTHESIS)
    ]
    carried_risks: list[str] = []
    limitations: list[str] = []
    for artifact in decision_artifacts:
        carried_risks.extend((artifact.payload or {}).get("unresolved_risks") or [])
        limitations.extend((artifact.payload or {}).get("limitations") or [])
    for artifact in rows:
        limitations.extend(artifact.limitations)

    model_artifacts = [a for a in rows if (a.payload or {}).get("produced_by") == "model"]
    substitutions = [
        {"artifact_id": a.artifact_id, "substituted": (a.payload or {}).get("substituted")}
        for a in model_artifacts if (a.payload or {}).get("substituted")
    ]

    gate_report = GateEngine(artifacts, missions).report(dev_mission_id)
    gates_passed = [g for g in gate_report["gates"] if g["status"] in ("passed", "waived_by_owner")]

    remaining_risks = {
        "open_vetoes": list(mission.open_vetoes),
        "unresolved_disagreements": list(mission.unresolved_disagreements),
        "carried_into_decision": carried_risks,
        "unanswered_challenges": [
            c["artifact_id"] for c in comments
            if c["kind"] == ArtifactKind.CHALLENGE.value
            and not any(
                c["artifact_id"] in r["targets"] for r in comments
                if r["kind"] == ArtifactKind.RESPONSE.value
            )
        ],
        "model_substitutions": substitutions,
    }

    return {
        "console": REVIEW_VERSION,
        "generated_at": time.time(),
        "read_only_display": True,
        "mission": missions.status(dev_mission_id),
        "agent_outputs": outputs,
        "review_comments": comments,
        "approval_history": {
            "gates": gate_report["gates"],
            "owner_decisions": [d.to_dict() for d in decisions],
            "chain": ledger.verify_chain(),
        },
        "artifact_lineage": lineage,
        "tests": verification,
        "behaviour_evaluation": _evidence_file(repo_root, "MODEL_EVALUATION.json"),
        "adversarial_evaluation": _evidence_file(repo_root, "ADVERSARIAL_EVALUATION.json"),
        "resource_usage": ceiling_report(settings),
        "limitations": sorted(set(limitations)),
        "confidence_signals": {
            "gates_passed": len(gates_passed),
            "gates_total": len(gate_report["gates"]),
            "self_approved_gates": sum(
                1 for g in gate_report["gates"]
                if g["approver"] and g["approver"] == g["subject_author"]
            ),
            "artifacts": len(rows),
            "artifacts_produced_by_model": len(model_artifacts),
            "model_substitutions": len(substitutions),
            "unresolved_disagreements": len(mission.unresolved_disagreements),
            "open_vetoes": len(mission.open_vetoes),
            "verification_reports": len(verification),
            "checks_not_run": sum(len(v["not_run"]) for v in verification),
            "note": (
                "Signals only. No scalar confidence score is computed, because "
                "a number nobody can derive is worse than no number. Each count "
                "above is checkable against the artifacts in this packet."
            ),
        },
        "remaining_risks": remaining_risks,
        "owner_actions": [
            {"action": a.value, "effect": ACTION_EFFECT[a]} for a in OwnerAction
        ],
        "capabilities": {
            "merges": False,
            "deploys": False,
            "pushes": False,
            "contacts_provider": False,
            "records_owner_decisions": True,
        },
        "limitation": (
            "A packet is a snapshot. The owner's decision is recorded in an "
            "append-only hash-chained ledger; nothing here merges, pushes, "
            "deploys or contacts a provider."
        ),
    }


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------

_CSS = """
:root{color-scheme:light dark;--bg:#0f1115;--fg:#e6e8ee;--muted:#9aa3b2;--card:#161a21;
--line:#242a35;--ok:#4ade80;--warn:#fbbf24;--bad:#f87171;--accent:#60a5fa}
@media (prefers-color-scheme:light){:root{--bg:#f7f8fa;--fg:#12151a;--muted:#5b6472;
--card:#fff;--line:#e2e5ea;--ok:#15803d;--warn:#b45309;--bad:#b91c1c;--accent:#1d4ed8}}
*{box-sizing:border-box}
body{margin:0;padding:24px;background:var(--bg);color:var(--fg);
font:14px/1.55 ui-sans-serif,-apple-system,"SF Pro Text",Segoe UI,sans-serif}
h1{font-size:20px;margin:0 0 4px}h2{font-size:13px;margin:0 0 12px;letter-spacing:.05em;
text-transform:uppercase;color:var(--muted)}
.sub{color:var(--muted);font-size:13px;margin-bottom:20px}
.banner{border:1px solid var(--line);border-left:3px solid var(--accent);background:var(--card);
padding:10px 14px;border-radius:6px;margin-bottom:20px;font-size:13px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(330px,1fr));gap:16px;
align-items:start}
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:16px;
min-width:0;overflow:auto;max-height:560px}
.card.wide{grid-column:1/-1}
table{border-collapse:collapse;width:100%;font-size:13px}
th,td{text-align:left;padding:6px 10px 6px 0;border-bottom:1px solid var(--line);
vertical-align:top;white-space:nowrap}
th{color:var(--muted);font-weight:500;font-size:12px}
td.wrap,th.wrap{white-space:normal;min-width:220px}
.kv{display:flex;justify-content:space-between;gap:16px;padding:5px 0;border-bottom:1px solid var(--line)}
.kv:last-child{border-bottom:0}.kv span:first-child{color:var(--muted)}
.ok{color:var(--ok)}.warn{color:var(--warn)}.bad{color:var(--bad)}
.empty{color:var(--muted);font-style:italic}
code,pre{font:12px ui-monospace,SFMono-Regular,Menlo,monospace}
pre{background:var(--bg);border:1px solid var(--line);border-radius:6px;padding:10px;
overflow-x:auto;margin:6px 0}
footer{margin-top:24px;color:var(--muted);font-size:12px}
"""


def _e(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def _table(headers: list[str], rows: list[list[Any]], *, wrap: int = -1) -> str:
    if not rows:
        return '<p class="empty">Nothing recorded.</p>'
    head = "".join(
        f'<th class="wrap">{_e(h)}</th>' if i == wrap else f"<th>{_e(h)}</th>"
        for i, h in enumerate(headers)
    )
    body = "".join(
        "<tr>" + "".join(
            f'<td class="wrap">{_e(c)}</td>' if i == wrap else f"<td>{_e(c)}</td>"
            for i, c in enumerate(row)
        ) + "</tr>"
        for row in rows
    )
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def _kv(pairs: list[tuple[str, Any]]) -> str:
    return "".join(
        f'<div class="kv"><span>{_e(k)}</span><span>{_e(v)}</span></div>' for k, v in pairs
    )


def _card(title: str, body: str, *, wide: bool = False) -> str:
    return f'<section class="{"card wide" if wide else "card"}"><h2>{_e(title)}</h2>{body}</section>'


def render_review_html(packet: dict[str, Any]) -> str:
    """Render the packet. The page displays; it never acts."""
    mission = packet["mission"]
    risks = packet["remaining_risks"]
    signals = packet["confidence_signals"]
    stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(packet["generated_at"]))
    mission_id = mission["dev_mission_id"]

    commands = "\n".join(
        f"python -m saathi.agentdev review {a['action'].replace('_', '-')} "
        f"{mission_id} --actor owner --rationale \"...\""
        for a in packet["owner_actions"]
    )

    chain = packet["approval_history"]["chain"]
    chain_state = (
        f'<span class="ok">intact</span>, {chain["entries"]} entr(y/ies)'
        if chain["intact"]
        else f'<span class="bad">BROKEN at entry {chain.get("broken_at")}</span> — '
             f'{_e(chain.get("reason"))}'
    )

    behaviour = packet.get("behaviour_evaluation") or {}
    suite = behaviour.get("suite") if isinstance(behaviour, dict) else None
    behaviour_body = (
        _kv([
            ("model", suite.get("model")),
            ("scenarios passed", f'{suite.get("passed")} / {suite.get("total")}'),
            ("evaluated agent", suite.get("evaluated_agent")),
            ("everything else", suite.get("everything_else")),
        ])
        if isinstance(suite, dict)
        else '<p class="empty">No behaviour evaluation recorded for this commit.</p>'
    )

    adversarial = packet.get("adversarial_evaluation") or {}
    adversarial_body = (
        _kv([
            ("model", adversarial.get("model")),
            ("system held", f'{adversarial.get("system_held")} / {adversarial.get("total")}'),
            ("model complied with", f'{adversarial.get("model_complied_with_attack")} attacks'),
            ("silently continued", len(adversarial.get("silently_continued") or [])),
        ])
        if adversarial
        else '<p class="empty">No adversarial evaluation recorded for this commit.</p>'
    )

    host = packet["resource_usage"]["host"]
    cards = [
        _card("Mission", _kv([
            ("id", mission_id),
            ("title", mission["title"]),
            ("state", mission["state"]),
            ("terminal verdict", mission["terminal_verdict"] or "—"),
            ("starting sha", (mission["starting_sha"] or "")[:12]),
            ("participants", ", ".join(mission["participants"]) or "—"),
        ]), wide=True),
        _card("Agent outputs", _table(
            ["artifact", "kind", "author", "title", "status", "model", "substituted"],
            [
                [o["artifact_id"], o["kind"], o["author"], o["title"], o["status"],
                 "yes" if o["produced_by_model"] else "", o["substituted"] or ""]
                for o in packet["agent_outputs"]
            ], wrap=3,
        ), wide=True),
        _card("Review comments", _table(
            ["artifact", "kind", "author", "decision required"],
            [
                [c["artifact_id"], c["kind"], c["author"], c["decision_required"] or "—"]
                for c in packet["review_comments"]
            ], wrap=3,
        ), wide=True),
        _card("Approval history — gates", _table(
            ["gate", "status", "approver", "subject"],
            [
                [g["gate"], g["status"], g["approver"] or "—", g["subject_author"] or "—"]
                for g in packet["approval_history"]["gates"]
            ],
        )),
        _card("Approval history — owner decisions",
              f'<p>Chain: {chain_state}</p>' + _table(
                  ["seq", "action", "rationale", "hash"],
                  [
                      [d["seq"], d["action"], d["rationale"], d["entry_hash"][:12]]
                      for d in packet["approval_history"]["owner_decisions"]
                  ], wrap=2,
              )),
        _card("Artifact lineage", _table(
            ["from", "to", "kind"],
            [[l["from"], l["to"], l["kind"]] for l in packet["artifact_lineage"]],
        )),
        _card("Tests", _table(
            ["artifact", "results", "negative paths", "not run"],
            [
                [t["artifact_id"], len(t["results"]), len(t["negative_paths"]),
                 len(t["not_run"])]
                for t in packet["tests"]
            ],
        )),
        _card("Behaviour evaluation", behaviour_body),
        _card("Adversarial evaluation", adversarial_body),
        _card("Resource usage", _kv([
            ("host", f'{host["system"]} {host["machine"]}, {host["cpu_count"]} CPU'),
            ("memory", f'{host["total_memory_gib"]} GiB'),
            ("free disk", f'{host["disk_free_gib"]} GiB'),
            ("ceiling enforcement", packet["resource_usage"]["enforcement"]),
        ])),
        _card("Confidence signals", _kv([
            ("gates passed", f'{signals["gates_passed"]} / {signals["gates_total"]}'),
            ("self-approved gates", signals["self_approved_gates"]),
            ("artifacts", signals["artifacts"]),
            ("produced by a model", signals["artifacts_produced_by_model"]),
            ("model substitutions", signals["model_substitutions"]),
            ("unresolved disagreements", signals["unresolved_disagreements"]),
            ("open vetoes", signals["open_vetoes"]),
            ("checks not run", signals["checks_not_run"]),
        ]) + f'<p class="empty">{_e(signals["note"])}</p>'),
        _card("Remaining risks", _kv([
            ("open vetoes", ", ".join(risks["open_vetoes"]) or "none"),
            ("unresolved disagreements", ", ".join(risks["unresolved_disagreements"]) or "none"),
            ("unanswered challenges", ", ".join(risks["unanswered_challenges"]) or "none"),
            ("carried into the decision", "; ".join(risks["carried_into_decision"]) or "none"),
            ("model substitutions", len(risks["model_substitutions"])),
        ])),
        _card("Limitations", (
            "<ul>" + "".join(f"<li>{_e(l)}</li>" for l in packet["limitations"]) + "</ul>"
            if packet["limitations"] else '<p class="empty">None recorded.</p>'
        ), wide=True),
        _card("Owner actions", _table(
            ["action", "effect"],
            [[a["action"], a["effect"]] for a in packet["owner_actions"]], wrap=1,
        ) + "<p>Each action is recorded by running the matching command. This page "
            "cannot act.</p><pre>" + _e(commands) + "</pre>", wide=True),
    ]

    return (
        "<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>Owner Review — {_e(mission_id)}</title>"
        f"<style>{_CSS}</style></head><body>"
        f"<h1>Owner Review — {_e(mission['title'])}</h1>"
        f'<p class="sub">Packet {_e(stamp)} · mission <code>{_e(mission_id)}</code> · '
        f'state {_e(mission["state"])}</p>'
        '<div class="banner"><strong>This page displays. It does not act.</strong> '
        "Four owner actions exist — approve, reject, request changes, needs research "
        "— and each is recorded by running the command shown at the bottom. There is "
        "no merge, push, deploy or provider control anywhere in this surface.</div>"
        f'<div class="grid">{"".join(cards)}</div>'
        f"<footer>{_e(packet['console'])} · {_e(packet['limitation'])}</footer>"
        "</body></html>\n"
    )
