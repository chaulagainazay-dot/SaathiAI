"""M353 — Read-only Agent Operations Console.

One place to see the whole development environment. Fifteen panels, assembled
from the stores and from live git, rendered either as JSON or as a single
self-contained HTML file.

**This module writes nothing and decides nothing.** It has no approve, advance,
create, remove or run verb; it never touches a provider; it never spawns a
process other than the allowlisted read-only git commands already governed by
:func:`saathi.agentdev.worktrees.run_read_only_git`. The only file it can
produce is the rendered HTML the operator explicitly asks for with
``--output``, and that lands wherever the operator points it.

No live polling. A view is a snapshot with a timestamp; refreshing means
running the command again. A console that polled would need a daemon, and a
daemon is a running process this milestone has no reason to add.

Panels, in the order the operator reads them:

1. operator notices        6. review queue          11. certification status
2. missions (active)       7. approvals             12. repository state
3. blocked missions        8. disagreements         13. active branches
4. mission lifecycle       9. evidence status       14. integration candidates
5. agent hierarchy        10. worktrees             15. resource usage
"""
from __future__ import annotations

import html
import json
import re
import time
from pathlib import Path
from typing import Any

from saathi.agentdev.artifacts import ArtifactKind, ArtifactStatus, ArtifactStore
from saathi.agentdev.gates import GATE_EVIDENCE_KIND, OWNER_ONLY_GATES
from saathi.agentdev.missions import (
    ALLOWED_TRANSITIONS,
    STATE_EXIT_GATES,
    DevMission,
    DevMissionStore,
    Gate,
    MissionState,
)
from saathi.agentdev.resources import ceiling_report
from saathi.agentdev.roles import OWNER, RoleValidationError, list_roles
from saathi.agentdev.settings import AgentDevSettings, load_settings
from saathi.agentdev.terminology import audit_surface
from saathi.agentdev.worktrees import WorktreeError, WorktreeManager, run_read_only_git

CONSOLE_VERSION = "agentdev.console.v1"

#: Mission states that mean work is in flight.
ACTIVE_STATES = frozenset(
    s for s in MissionState
    if s not in (MissionState.CLOSED, MissionState.ABANDONED, MissionState.BLOCKED)
)

#: Verdicts that make a mission an integration candidate for the owner to weigh.
INTEGRATION_VERDICTS = frozenset({
    "APPROVED_FOR_IMPLEMENTATION",
    "APPROVED_WITH_LIMITATIONS",
})

_VERDICT_RE = re.compile(r"^\*\*Verdict:\*\*\s*`([A-Z_]+)`", re.MULTILINE)


# --------------------------------------------------------------------------
# Panels
# --------------------------------------------------------------------------


def _mission_row(mission: DevMission) -> dict[str, Any]:
    state = mission.mission_state
    unmet = [g.value for g in STATE_EXIT_GATES.get(state, ()) if not mission.gate(g).passed]
    passed = sorted(k for k, v in mission.gates.items() if v.passed)
    failed = sorted(k for k, v in mission.gates.items() if v.status == "failed")
    return {
        "dev_mission_id": mission.dev_mission_id,
        "title": mission.title,
        "state": mission.state,
        "created_by": mission.created_by,
        "participants": list(mission.participants),
        "starting_sha": mission.starting_sha,
        "terminal_verdict": mission.terminal_verdict or None,
        "open_vetoes": list(mission.open_vetoes),
        "unresolved_disagreements": list(mission.unresolved_disagreements),
        "gates_passed": passed,
        "gates_failed": failed,
        "unmet_exit_gates": unmet,
        "next_states": sorted(s.value for s in ALLOWED_TRANSITIONS.get(state, frozenset())),
        "updated_at": mission.updated_at,
        "history_events": len(mission.history),
    }


def panel_missions(missions: list[DevMission]) -> dict[str, Any]:
    """Active missions, plus every mission so a closed one stays visible."""
    active = [m for m in missions if m.mission_state in ACTIVE_STATES]
    return {
        "total": len(missions),
        "active": len(active),
        "rows": [_mission_row(m) for m in active],
        "all_rows": [_mission_row(m) for m in missions],
    }


def panel_blocked_missions(missions: list[DevMission]) -> dict[str, Any]:
    rows = []
    for mission in missions:
        reasons: list[str] = []
        if mission.state == MissionState.BLOCKED.value:
            reasons.append("state_blocked")
        if mission.open_vetoes:
            reasons.append("security_veto_open")
        row = _mission_row(mission)
        if row["unmet_exit_gates"] and mission.mission_state in ACTIVE_STATES:
            reasons.append("unmet_exit_gates")
        if not reasons:
            continue
        row["blocked_because"] = reasons
        rows.append(row)
    return {"count": len(rows), "rows": rows}


def panel_lifecycle(missions: list[DevMission]) -> dict[str, Any]:
    counts = {s.value: 0 for s in MissionState}
    for mission in missions:
        counts[mission.state] = counts.get(mission.state, 0) + 1
    return {
        "states": [
            {
                "state": s.value,
                "missions": counts.get(s.value, 0),
                "exit_gates": [g.value for g in STATE_EXIT_GATES.get(s, ())],
                "terminal": s in (MissionState.CLOSED, MissionState.ABANDONED),
            }
            for s in MissionState
        ],
        "gate_catalogue": [
            {
                "gate": g.value,
                "required_evidence_kind": GATE_EVIDENCE_KIND[g].value,
                "owner_only": g in OWNER_ONLY_GATES,
            }
            for g in Gate
        ],
    }


def panel_agent_hierarchy() -> dict[str, Any]:
    """Escalation edges as a tree, plus each role's review and authority facts."""
    try:
        roles = list_roles()
    except RoleValidationError as exc:
        return {"status": "invalid_registry", "code": exc.code, "detail": exc.detail}

    children: dict[str, list[str]] = {}
    for role in roles:
        children.setdefault(role.escalation_to, []).append(role.agent_id)

    def subtree(node: str, seen: frozenset[str]) -> dict[str, Any]:
        # A registry cycle is already refused at load time; the guard here keeps
        # the console honest if that ever regresses, instead of recursing away.
        if node in seen:
            return {"agent_id": node, "cycle": True, "reports": []}
        return {
            "agent_id": node,
            "reports": [
                subtree(child, seen | {node})
                for child in sorted(children.get(node, []))
            ],
        }

    return {
        "status": "ok",
        "count": len(roles),
        "tree": subtree(OWNER, frozenset()),
        "roles": [
            {
                "agent_id": r.agent_id,
                "role_name": r.role_name,
                "escalates_to": r.escalation_to,
                "reviewed_by": list(r.independent_review_by),
                "max_authority": r.max_authority.name,
                "approves_gates": r.may_approve_gates,
                "writes_code": r.may_write_code,
                "worktree_mode": r.default_worktree_mode,
            }
            for r in roles
        ],
    }


def panel_review_queue(
    artifacts: ArtifactStore, missions: list[DevMission]
) -> dict[str, Any]:
    """Artifacts awaiting a reviewer, oldest first — the operator's work list."""
    waiting_statuses = (
        ArtifactStatus.SUBMITTED.value,
        ArtifactStatus.UNDER_REVIEW.value,
        ArtifactStatus.BLOCKED.value,
    )
    rows: list[dict[str, Any]] = []
    for mission in missions:
        for artifact in artifacts.list(mission.dev_mission_id):
            if artifact.status not in waiting_statuses:
                continue
            rows.append({
                "dev_mission_id": mission.dev_mission_id,
                "artifact_id": artifact.artifact_id,
                "kind": artifact.kind,
                "title": artifact.title,
                "author": artifact.authoring_agent,
                "status": artifact.status,
                "required_next_action": artifact.required_next_action,
                "waiting_since": artifact.updated_at,
            })
    rows.sort(key=lambda r: r["waiting_since"])
    return {"count": len(rows), "rows": rows}


def panel_approvals(missions: list[DevMission]) -> dict[str, Any]:
    """Every recorded gate decision. Self-approval would surface here as a flag."""
    rows: list[dict[str, Any]] = []
    for mission in missions:
        for name, record in sorted(mission.gates.items()):
            rows.append({
                "dev_mission_id": mission.dev_mission_id,
                "gate": name,
                "status": record.status,
                "approver": record.approver or None,
                "subject_author": record.subject_author or None,
                "evidence": list(record.evidence_artifact_ids),
                "reason": record.reason,
                "decided_at": record.decided_at,
                "owner_only": Gate(name) in OWNER_ONLY_GATES if _is_gate(name) else False,
                "self_approved": bool(
                    record.approver and record.approver == record.subject_author
                ),
            })
    rows.sort(key=lambda r: r["decided_at"], reverse=True)
    return {
        "count": len(rows),
        "passed": sum(1 for r in rows if r["status"] in ("passed", "waived_by_owner")),
        "failed": sum(1 for r in rows if r["status"] == "failed"),
        "self_approved": sum(1 for r in rows if r["self_approved"]),
        "rows": rows,
    }


def _is_gate(name: str) -> bool:
    try:
        Gate(name)
    except ValueError:
        return False
    return True


def panel_disagreements(
    artifacts: ArtifactStore, missions: list[DevMission]
) -> dict[str, Any]:
    """Unresolved disagreements and the challenges that were never answered."""
    rows: list[dict[str, Any]] = []
    for mission in missions:
        answered = {
            dep
            for a in artifacts.list(mission.dev_mission_id, kind=ArtifactKind.RESPONSE)
            for dep in a.dependencies
        }
        for challenge in artifacts.list(
            mission.dev_mission_id, kind=ArtifactKind.CHALLENGE
        ):
            rows.append({
                "dev_mission_id": mission.dev_mission_id,
                "artifact_id": challenge.artifact_id,
                "title": challenge.title,
                "raised_by": challenge.authoring_agent,
                "targets": list(challenge.dependencies),
                "answered": challenge.artifact_id in answered,
                "decision_required": (challenge.payload or {}).get("decision_required", ""),
            })
    unresolved = {
        m.dev_mission_id: list(m.unresolved_disagreements)
        for m in missions
        if m.unresolved_disagreements
    }
    return {
        "challenges": len(rows),
        "unanswered": sum(1 for r in rows if not r["answered"]),
        "recorded_unresolved": unresolved,
        "rows": rows,
    }


def panel_evidence(artifacts: ArtifactStore, missions: list[DevMission]) -> dict[str, Any]:
    by_kind: dict[str, int] = {}
    by_status: dict[str, int] = {}
    per_mission: list[dict[str, Any]] = []
    lineage: list[dict[str, Any]] = []
    for mission in missions:
        rows = artifacts.list(mission.dev_mission_id)
        per_mission.append({
            "dev_mission_id": mission.dev_mission_id,
            "artifacts": len(rows),
            "kinds": sorted({a.kind for a in rows}),
        })
        for artifact in rows:
            by_kind[artifact.kind] = by_kind.get(artifact.kind, 0) + 1
            by_status[artifact.status] = by_status.get(artifact.status, 0) + 1
            if artifact.dependencies or artifact.supersedes:
                lineage.append({
                    "dev_mission_id": mission.dev_mission_id,
                    "artifact_id": artifact.artifact_id,
                    "kind": artifact.kind,
                    "depends_on": list(artifact.dependencies),
                    "supersedes": artifact.supersedes or None,
                })
    return {
        "total": sum(by_kind.values()),
        "by_kind": dict(sorted(by_kind.items())),
        "by_status": dict(sorted(by_status.items())),
        "per_mission": per_mission,
        "lineage": lineage,
    }


def panel_worktrees(settings: AgentDevSettings) -> dict[str, Any]:
    try:
        census = WorktreeManager(settings=settings).inspect_environment()
    except (WorktreeError, OSError) as exc:
        return {"status": "unavailable", "detail": str(exc)}
    census["status"] = "ok"
    return census


def panel_certification(repo_root: Path) -> dict[str, Any]:
    """Verdict tokens parsed from every ``docs/evidence/*/CERTIFICATION.md``."""
    rows: list[dict[str, Any]] = []
    base = repo_root / "docs" / "evidence"
    if base.is_dir():
        for path in sorted(base.glob("*/CERTIFICATION.md")):
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            match = _VERDICT_RE.search(text)
            rows.append({
                "milestone": path.parent.name,
                "verdict": match.group(1) if match else None,
                "path": str(path.relative_to(repo_root)),
                "has_machine_readable": (path.parent / "EVIDENCE.json").is_file(),
            })
    return {
        "count": len(rows),
        "rows": rows,
        "note": (
            "certification is documentation_only: an owner-reviewed statement "
            "about one commit. See docs/ai-development/terminology.md."
        ),
    }


def panel_repository(repo_root: Path) -> dict[str, Any]:
    """Live git facts, read through the same allowlist the worktree manager uses."""
    def git(*args: str) -> tuple[int, str]:
        return run_read_only_git(list(args), repo_root, timeout=20)

    code, head = git("rev-parse", "HEAD")
    _, branch = git("rev-parse", "--abbrev-ref", "HEAD")
    status_code, status = git("status", "--porcelain")
    if code != 0:
        return {"status": "unavailable", "detail": head.strip()[:300]}
    dirty = [line for line in status.splitlines() if line.strip()]
    return {
        "status": "ok",
        "path": str(repo_root),
        "head": head.strip(),
        "branch": branch.strip(),
        "clean": status_code == 0 and not dirty,
        "dirty_paths": [line.strip() for line in dirty][:50],
        "dirty_count": len(dirty),
    }


def panel_branches(repo_root: Path) -> dict[str, Any]:
    code, out = run_read_only_git(
        ["branch", "--format=%(refname:short)\t%(objectname:short)\t%(committerdate:iso8601)"],
        repo_root,
        timeout=20,
    )
    if code != 0:
        return {"status": "unavailable", "detail": out.strip()[:300]}
    rows: list[dict[str, Any]] = []
    for line in out.splitlines():
        parts = line.strip().split("\t")
        if len(parts) != 3 or not parts[0]:
            continue
        rows.append({
            "branch": parts[0],
            "head": parts[1],
            "committed_at": parts[2],
            "agent_branch": parts[0].startswith("agent/"),
        })
    return {
        "status": "ok",
        "count": len(rows),
        "agent_branches": sum(1 for r in rows if r["agent_branch"]),
        "rows": rows,
    }


def panel_integration_candidates(
    artifacts: ArtifactStore, missions: list[DevMission]
) -> dict[str, Any]:
    """Missions the owner could weigh for integration, and what still stands."""
    rows: list[dict[str, Any]] = []
    for mission in missions:
        if mission.terminal_verdict not in INTEGRATION_VERDICTS:
            continue
        candidacy = mission.gate(Gate.INTEGRATION_CANDIDACY)
        owner_gate = mission.gate(Gate.OWNER_APPROVAL)
        handoffs = artifacts.list(
            mission.dev_mission_id, kind=ArtifactKind.IMPLEMENTATION_HANDOFF
        )
        rows.append({
            "dev_mission_id": mission.dev_mission_id,
            "title": mission.title,
            "terminal_verdict": mission.terminal_verdict,
            "integration_candidacy_gate": candidacy.status,
            "owner_approval_gate": owner_gate.status,
            "branches": sorted({a.branch for a in handoffs if a.branch}),
            "worktrees": sorted({a.worktree for a in handoffs if a.worktree}),
            "carried_risks": list(mission.unresolved_disagreements),
            "open_vetoes": list(mission.open_vetoes),
        })
    return {
        "count": len(rows),
        "rows": rows,
        "note": (
            "A candidate is a mission the owner may weigh. Nothing here merges, "
            "pushes or deploys; those verbs do not exist in this package."
        ),
    }


def panel_operator_notices(
    settings: AgentDevSettings,
    worktrees: dict[str, Any],
    repository: dict[str, Any],
    missions: list[DevMission],
    terminology: dict[str, Any],
) -> dict[str, Any]:
    """Derived, deterministic notices. Advisory: nothing acts on them."""
    notices: list[dict[str, str]] = []

    def notice(level: str, code: str, detail: str) -> None:
        notices.append({"level": level, "code": code, "detail": detail})

    if not settings.agentdev_enabled:
        notice("info", "agentdev_disabled",
               "The environment is disabled by default. The console still reads.")
    if not settings.worktree_creation_enabled:
        notice("info", "worktree_creation_disabled",
               "No worktree can be created until an approved handoff enables it.")

    findings = (worktrees.get("findings") or {}) if worktrees.get("status") == "ok" else {}
    prunable = findings.get("prunable_stale_worktrees") or []
    if prunable:
        notice("warning", "stale_worktrees",
               f"{len(prunable)} prunable worktrees reported. This console removes nothing.")
    if findings.get("unregistered_agent_worktrees"):
        notice("warning", "unregistered_agent_worktrees",
               ", ".join(findings["unregistered_agent_worktrees"])[:300])
    if findings.get("registered_but_missing_on_disk"):
        notice("warning", "registered_but_missing_on_disk",
               ", ".join(findings["registered_but_missing_on_disk"])[:300])
    if findings.get("duplicate_branch_checkouts"):
        notice("warning", "duplicate_branch_checkouts",
               ", ".join(sorted(findings["duplicate_branch_checkouts"]))[:300])

    if repository.get("status") == "ok" and not repository.get("clean"):
        notice("warning", "repository_dirty",
               f"{repository.get('dirty_count', 0)} uncommitted paths in {repository.get('path')}.")

    for mission in missions:
        if mission.open_vetoes:
            notice("blocker", "security_veto_open",
                   f"{mission.dev_mission_id}: {', '.join(mission.open_vetoes)}")
        if mission.state == MissionState.CLOSED.value and not mission.terminal_verdict:
            notice("blocker", "closed_without_verdict", mission.dev_mission_id)
        if mission.unresolved_disagreements:
            notice("warning", "unresolved_disagreements",
                   f"{mission.dev_mission_id}: {', '.join(mission.unresolved_disagreements)}")

    if not terminology.get("clean", True):
        notice("warning", "terminology_findings",
               f"{len(terminology.get('findings', []))} banned phrases on the reviewed surface.")

    order = {"blocker": 0, "warning": 1, "info": 2}
    notices.sort(key=lambda n: (order.get(n["level"], 3), n["code"]))
    return {
        "count": len(notices),
        "blockers": sum(1 for n in notices if n["level"] == "blocker"),
        "warnings": sum(1 for n in notices if n["level"] == "warning"),
        "rows": notices,
    }


# --------------------------------------------------------------------------
# Assembly
# --------------------------------------------------------------------------


def panel_qualification_summary(repo_root: Path) -> dict[str, Any]:
    """The thirteen M369–M376 panels, read from evidence. Contacts no provider.

    Summarised here and rendered in full by
    ``python -m saathi.agentdev qualification show`` — putting thirteen more
    tables on this page would bury the fifteen that were already here.
    """
    from saathi.agentdev.qualification_console import (
        EVIDENCE_DIRECTORY,
        collect_qualification_state,
    )

    state = collect_qualification_state(repo_root / EVIDENCE_DIRECTORY)
    panels = state["panels"]
    models = panels["installed_models"]
    matrix = panels["role_matrix"]
    routing = panels["routing_policy"]
    return {
        "status": "ok" if models["status"] == "ok" else "missing",
        "evidence_directory": state["evidence_directory"],
        "installed_models": models.get("count", 0),
        "eligible_models": models.get("eligible", 0),
        "excluded_models": models.get("excluded", 0),
        "evaluated_models": panels["evaluation_progress"].get("evaluated", 0),
        "roles": len(matrix.get("roles", [])),
        "qualified_pairs": sum(
            1 for row in (matrix.get("statuses") or {}).values()
            for status in row.values() if status.startswith("QUALIFIED")
        ),
        "roles_routed": routing.get("roles_routed", 0),
        "roles_unrouted": routing.get("roles_unrouted", 0),
        "pending_owner_decisions": panels["owner_decisions"]["pending_count"],
        "certification": panels["certification"].get(
            "verdict", panels["certification"].get("detail", "")
        ),
        "panels_available": sorted(panels),
        "detail_command": "python -m saathi.agentdev qualification show",
    }


def collect_console_state(
    settings: AgentDevSettings | None = None,
) -> dict[str, Any]:
    """Assemble every panel. Pure read: nothing in this call writes."""
    settings = settings or load_settings()
    root = settings.store_path()
    repo_root = Path(settings.repo_root)
    artifacts = ArtifactStore(root)
    mission_store = DevMissionStore(root)
    missions = mission_store.list()

    worktrees = panel_worktrees(settings)
    repository = panel_repository(repo_root)
    terminology = audit_surface(repo_root)

    return {
        "console": CONSOLE_VERSION,
        "generated_at": time.time(),
        "read_only": True,
        "store_path": str(root),
        "panels": {
            "operator_notices": panel_operator_notices(
                settings, worktrees, repository, missions, terminology
            ),
            "missions": panel_missions(missions),
            "blocked_missions": panel_blocked_missions(missions),
            "mission_lifecycle": panel_lifecycle(missions),
            "agent_hierarchy": panel_agent_hierarchy(),
            "review_queue": panel_review_queue(artifacts, missions),
            "approvals": panel_approvals(missions),
            "disagreements": panel_disagreements(artifacts, missions),
            "evidence": panel_evidence(artifacts, missions),
            "worktrees": worktrees,
            "certification": panel_certification(repo_root),
            "repository": repository,
            "branches": panel_branches(repo_root),
            "integration_candidates": panel_integration_candidates(artifacts, missions),
            "resources": ceiling_report(settings),
            "terminology": {
                "clean": terminology["clean"],
                "files_scanned": terminology["files_scanned"],
                "findings": terminology["findings"],
            },
            # M376 — the qualification views. Nested rather than flattened so a
            # reader can see at a glance which panels came from evidence files
            # and which from live stores, and so the fifteen original panels
            # keep their numbering.
            "local_model_qualification": panel_qualification_summary(repo_root),
        },
        "capabilities": {
            "writes": False,
            "approves": False,
            "executes_missions": False,
            "contacts_provider": False,
            "polls": False,
        },
        "limitation": (
            "A snapshot, not a live view. Refreshing means running the command "
            "again. The console has no write, approve, execute or provider verb."
        ),
    }


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------


_CSS = """
:root{color-scheme:light dark;--bg:#0f1115;--fg:#e6e8ee;--muted:#9aa3b2;
--card:#161a21;--line:#242a35;--ok:#4ade80;--warn:#fbbf24;--blocker:#f87171;--accent:#60a5fa}
@media (prefers-color-scheme:light){:root{--bg:#f7f8fa;--fg:#12151a;--muted:#5b6472;
--card:#fff;--line:#e2e5ea;--ok:#15803d;--warn:#b45309;--blocker:#b91c1c;--accent:#1d4ed8}}
*{box-sizing:border-box}
body{margin:0;padding:24px;background:var(--bg);color:var(--fg);
font:14px/1.5 ui-sans-serif,-apple-system,"SF Pro Text",Segoe UI,sans-serif}
h1{font-size:20px;margin:0 0 4px}h2{font-size:14px;margin:0 0 12px;letter-spacing:.04em;
text-transform:uppercase;color:var(--muted)}
.sub{color:var(--muted);margin-bottom:20px;font-size:13px}
.banner{border:1px solid var(--line);border-left:3px solid var(--accent);
background:var(--card);padding:10px 14px;border-radius:6px;margin-bottom:20px;font-size:13px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:16px;
align-items:start}
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:16px;
min-width:0;overflow:auto;max-height:560px}
.card.wide{grid-column:1/-1}
.card td.wrap{min-width:220px}
table{border-collapse:collapse;width:100%;font-size:13px}
th,td{text-align:left;padding:6px 10px 6px 0;border-bottom:1px solid var(--line);
vertical-align:top;white-space:nowrap}
th{color:var(--muted);font-weight:500;font-size:12px}
td.wrap,th.wrap{white-space:normal}
.kv{display:flex;justify-content:space-between;gap:16px;padding:5px 0;
border-bottom:1px solid var(--line)}
.kv:last-child{border-bottom:0}.kv span:first-child{color:var(--muted)}
.pill{display:inline-block;padding:1px 8px;border-radius:999px;font-size:12px;
border:1px solid var(--line)}
.ok{color:var(--ok)}.warn{color:var(--warn)}.blocker{color:var(--blocker)}
.empty{color:var(--muted);font-style:italic}
code{font:12px ui-monospace,SFMono-Regular,Menlo,monospace}
ul.tree{list-style:none;padding-left:16px;margin:0}
ul.tree li{position:relative;padding:2px 0}
ul.tree li::before{content:"└ ";color:var(--muted)}
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
        "<tr>"
        + "".join(
            f'<td class="wrap">{_e(c)}</td>' if i == wrap else f"<td>{_e(c)}</td>"
            for i, c in enumerate(row)
        )
        + "</tr>"
        for row in rows
    )
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def _kv(pairs: list[tuple[str, Any]]) -> str:
    return "".join(
        f'<div class="kv"><span>{_e(k)}</span><span>{_e(v)}</span></div>'
        for k, v in pairs
    )


def _card(title: str, body: str, *, wide: bool = False) -> str:
    css = "card wide" if wide else "card"
    return f'<section class="{css}"><h2>{_e(title)}</h2>{body}</section>'


def _tree_html(node: dict[str, Any]) -> str:
    label = _e(node.get("agent_id"))
    if node.get("cycle"):
        label += ' <span class="blocker">(cycle)</span>'
    reports = node.get("reports") or []
    if not reports:
        return f"<li>{label}</li>"
    inner = "".join(_tree_html(child) for child in reports)
    return f'<li>{label}<ul class="tree">{inner}</ul></li>'


def render_html(state: dict[str, Any]) -> str:
    """Render the state to one self-contained HTML page. Returns a string."""
    p = state["panels"]
    stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(state["generated_at"]))

    notices = p["operator_notices"]
    notice_rows = "".join(
        f'<tr><td><span class="pill {_e(n["level"])}">{_e(n["level"])}</span></td>'
        f"<td><code>{_e(n['code'])}</code></td>"
        f'<td class="wrap">{_e(n["detail"])}</td></tr>'
        for n in notices["rows"]
    ) or '<tr><td colspan="3" class="empty">No notices.</td></tr>'

    hierarchy = p["agent_hierarchy"]
    if hierarchy.get("status") == "ok":
        tree = f'<ul class="tree">{_tree_html(hierarchy["tree"])}</ul>'
        roles_table = _table(
            ["agent", "escalates to", "reviewed by", "authority", "gates", "code"],
            [
                [
                    r["agent_id"], r["escalates_to"], ", ".join(r["reviewed_by"]) or "—",
                    r["max_authority"], "yes" if r["approves_gates"] else "no",
                    "yes" if r["writes_code"] else "no",
                ]
                for r in hierarchy["roles"]
            ],
        )
        hierarchy_body = tree + roles_table
    else:
        hierarchy_body = (
            f'<p class="blocker">Registry invalid: <code>{_e(hierarchy.get("code"))}</code> '
            f"{_e(hierarchy.get('detail'))}</p>"
        )

    repo = p["repository"]
    repo_body = (
        _kv([
            ("branch", repo.get("branch")),
            ("head", (repo.get("head") or "")[:12]),
            ("clean", "yes" if repo.get("clean") else f"no ({repo.get('dirty_count')} paths)"),
            ("path", repo.get("path")),
        ])
        if repo.get("status") == "ok"
        else f'<p class="warn">Unavailable: {_e(repo.get("detail"))}</p>'
    )

    wt = p["worktrees"]
    if wt.get("status") == "ok":
        counts = wt["counts"]
        findings = wt["findings"]
        worktree_body = _kv([
            ("git worktrees", counts["git_total"]),
            ("agent branches", counts["agent_branches"]),
            ("registered active", counts["registered_active"]),
            ("prunable (stale)", counts["prunable"]),
            ("unregistered agent trees", len(findings["unregistered_agent_worktrees"])),
            ("registered, missing on disk", len(findings["registered_but_missing_on_disk"])),
            ("duplicate branch checkouts", len(findings["duplicate_branch_checkouts"])),
        ])
    else:
        worktree_body = f'<p class="warn">Unavailable: {_e(wt.get("detail"))}</p>'

    res = p["resources"]
    host = res["host"]
    ceilings = res["declared_ceilings"]
    resource_body = _kv([
        ("host", f'{host["system"]} {host["machine"]}, {host["cpu_count"]} CPU'),
        ("physical memory", f'{host["total_memory_gib"]} GiB'),
        ("free disk", f'{host["disk_free_gib"]} GiB'),
        ("load average", ", ".join(str(x) for x in host["load_average"])),
        ("this process, peak RSS", f'{host["peak_process_memory_mib"]} MiB'),
        ("max reasoning agents", ceilings["max_reasoning_agents"]),
        ("max coding agents", ceilings["max_coding_agents"]),
        ("max testing agents", ceilings["max_testing_agents"]),
        ("max local models", ceilings["max_local_model_instances"]),
        ("ceiling enforcement", res["enforcement"]),
    ])

    branches = p["branches"]
    branch_body = (
        _table(
            ["branch", "head", "committed", "agent"],
            [
                [r["branch"], r["head"], r["committed_at"][:16],
                 "yes" if r["agent_branch"] else ""]
                for r in branches["rows"]
            ],
        )
        if branches.get("status") == "ok"
        else f'<p class="warn">Unavailable: {_e(branches.get("detail"))}</p>'
    )

    ev = p["evidence"]
    term = p["terminology"]

    cards = [
        _card(
            "1 · Operator notices",
            f"<table><thead><tr><th>level</th><th>code</th>"
            f'<th class="wrap">detail</th></tr></thead><tbody>{notice_rows}</tbody></table>',
            wide=True,
        ),
        _card(
            "2 · Missions",
            f'<p class="empty">{p["missions"]["active"]} active of '
            f'{p["missions"]["total"]} total. Active first, then every mission.</p>'
            + _table(
                ["mission", "title", "state", "unmet gates", "vetoes", "verdict"],
                [
                    [r["dev_mission_id"], r["title"], r["state"],
                     ", ".join(r["unmet_exit_gates"]) or "—",
                     ", ".join(r["open_vetoes"]) or "—",
                     r["terminal_verdict"] or "—"]
                    for r in (p["missions"]["rows"] or p["missions"]["all_rows"])
                ],
                wrap=1,
            ),
            wide=True,
        ),
        _card(
            "3 · Blocked missions",
            _table(
                ["mission", "state", "blocked because"],
                [
                    [r["dev_mission_id"], r["state"], ", ".join(r["blocked_because"])]
                    for r in p["blocked_missions"]["rows"]
                ],
                wrap=2,
            ),
        ),
        _card(
            "4 · Mission lifecycle",
            _table(
                ["state", "missions", "exit gates"],
                [
                    [s["state"], s["missions"], ", ".join(s["exit_gates"]) or "—"]
                    for s in p["mission_lifecycle"]["states"]
                ],
                wrap=2,
            ),
        ),
        _card("5 · Agent hierarchy", hierarchy_body, wide=True),
        _card(
            "6 · Review queue",
            _table(
                ["mission", "artifact", "kind", "author", "status"],
                [
                    [r["dev_mission_id"], r["artifact_id"], r["kind"],
                     r["author"], r["status"]]
                    for r in p["review_queue"]["rows"]
                ],
            ),
        ),
        _card(
            "7 · Approvals",
            _kv([
                ("recorded", p["approvals"]["count"]),
                ("passed", p["approvals"]["passed"]),
                ("failed", p["approvals"]["failed"]),
                ("self-approved", p["approvals"]["self_approved"]),
            ])
            + _table(
                ["mission", "gate", "status", "approver", "subject"],
                [
                    [r["dev_mission_id"], r["gate"], r["status"],
                     r["approver"] or "—", r["subject_author"] or "—"]
                    for r in p["approvals"]["rows"]
                ],
            ),
        ),
        _card(
            "8 · Disagreements",
            _kv([
                ("challenges", p["disagreements"]["challenges"]),
                ("unanswered", p["disagreements"]["unanswered"]),
            ])
            + _table(
                ["mission", "challenge", "raised by", "answered"],
                [
                    [r["dev_mission_id"], r["title"], r["raised_by"],
                     "yes" if r["answered"] else "no"]
                    for r in p["disagreements"]["rows"]
                ],
                wrap=1,
            ),
        ),
        _card(
            "9 · Evidence",
            _kv([("artifacts", ev["total"]), ("lineage edges", len(ev["lineage"]))])
            + _table(
                ["kind", "count"], [[k, v] for k, v in ev["by_kind"].items()]
            ),
        ),
        _card("10 · Worktrees", worktree_body),
        _card(
            "11 · Certification",
            _table(
                ["milestone", "verdict", "machine-readable"],
                [
                    [r["milestone"], r["verdict"] or "—",
                     "yes" if r["has_machine_readable"] else "no"]
                    for r in p["certification"]["rows"]
                ],
                wrap=1,
            ),
        ),
        _card("12 · Repository", repo_body),
        _card("13 · Active branches", branch_body, wide=True),
        _card(
            "14 · Integration candidates",
            _table(
                ["mission", "verdict", "candidacy gate", "owner gate", "carried risks"],
                [
                    [r["dev_mission_id"], r["terminal_verdict"],
                     r["integration_candidacy_gate"], r["owner_approval_gate"],
                     ", ".join(r["carried_risks"]) or "—"]
                    for r in p["integration_candidates"]["rows"]
                ],
                wrap=4,
            )
            + f'<p class="empty">{_e(p["integration_candidates"]["note"])}</p>',
            wide=True,
        ),
        _card("15 · Resource usage", resource_body),
        _card(
            "Terminology guard",
            _kv([
                ("files scanned", term["files_scanned"]),
                ("findings", len(term["findings"])),
                ("status", "clean" if term["clean"] else "violations present"),
            ]),
        ),
    ]

    qualification = p["local_model_qualification"]
    cards.append(_card(
        "16 · local-model qualification",
        _kv([
            ("installed models", qualification["installed_models"]),
            ("eligible", qualification["eligible_models"]),
            ("excluded by this host", qualification["excluded_models"]),
            ("evaluated", qualification["evaluated_models"]),
            ("qualified model-role pairs", qualification["qualified_pairs"]),
            ("roles routed", f"{qualification['roles_routed']}/{qualification['roles']}"),
            ("pending owner decisions", qualification["pending_owner_decisions"]),
            ("certification", qualification["certification"]),
        ]) + (
            f'<p class="sub">Full panels: '
            f'<code>{_e(qualification["detail_command"])}</code></p>'
        ) if qualification["status"] == "ok"
        else '<p class="empty">No qualification evidence recorded yet.</p>',
        wide=True,
    ))

    blockers = notices["blockers"]
    headline = (
        f'<span class="blocker">{blockers} blocker(s)</span>'
        if blockers
        else '<span class="ok">no blockers</span>'
    )

    return (
        "<!doctype html>\n"
        '<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        "<title>SaathiOS Agent Operations Console</title>"
        f"<style>{_CSS}</style></head><body>"
        "<h1>SaathiOS Agent Operations Console</h1>"
        f'<p class="sub">Snapshot {_e(stamp)} · {headline} · store '
        f"<code>{_e(state['store_path'])}</code></p>"
        '<div class="banner"><strong>Read-only.</strong> This page displays state. '
        "It has no approve, advance, create, remove, merge, deploy or provider "
        "control, and it does not poll — refreshing means running "
        "<code>python -m saathi.agentdev console render</code> again.</div>"
        f'<div class="grid">{"".join(cards)}</div>'
        f"<footer>{_e(state['console'])} · {_e(state['limitation'])}</footer>"
        "</body></html>\n"
    )


def render_text(state: dict[str, Any]) -> str:
    """A terminal-friendly summary, for operators without a browser."""
    p = state["panels"]
    lines: list[str] = []
    stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(state["generated_at"]))
    lines.append(f"SaathiOS Agent Operations Console — snapshot {stamp}")
    lines.append(f"store: {state['store_path']}  (read-only, no polling)")
    lines.append("")

    notices = p["operator_notices"]
    lines.append(
        f"1  operator notices        {notices['count']} "
        f"({notices['blockers']} blocker, {notices['warnings']} warning)"
    )
    for n in notices["rows"][:12]:
        lines.append(f"     [{n['level']:<7}] {n['code']}: {n['detail'][:90]}")
    lines.append(f"2  missions                {p['missions']['active']} active / "
                 f"{p['missions']['total']} total")
    for row in p["missions"]["rows"][:12]:
        lines.append(
            f"     {row['dev_mission_id']}  {row['state']:<20} {row['title'][:44]}"
        )
    lines.append(f"3  blocked missions        {p['blocked_missions']['count']}")
    lines.append(f"4  mission lifecycle       {len(p['mission_lifecycle']['states'])} states, "
                 f"{len(p['mission_lifecycle']['gate_catalogue'])} gates")
    hierarchy = p["agent_hierarchy"]
    lines.append(f"5  agent hierarchy         {hierarchy.get('count', 0)} roles "
                 f"({hierarchy.get('status')})")
    lines.append(f"6  review queue            {p['review_queue']['count']} waiting")
    approvals = p["approvals"]
    lines.append(f"7  approvals               {approvals['count']} recorded, "
                 f"{approvals['passed']} passed, {approvals['failed']} failed, "
                 f"{approvals['self_approved']} self-approved")
    lines.append(f"8  disagreements           {p['disagreements']['challenges']} challenges, "
                 f"{p['disagreements']['unanswered']} unanswered")
    lines.append(f"9  evidence                {p['evidence']['total']} artifacts, "
                 f"{len(p['evidence']['lineage'])} lineage edges")
    wt = p["worktrees"]
    if wt.get("status") == "ok":
        c = wt["counts"]
        lines.append(f"10 worktrees               {c['git_total']} git, "
                     f"{c['agent_branches']} agent, {c['prunable']} prunable")
    else:
        lines.append(f"10 worktrees               unavailable: {wt.get('detail')}")
    for row in p["certification"]["rows"]:
        lines.append(f"11 certification           {row['milestone']}: {row['verdict']}")
    repo = p["repository"]
    if repo.get("status") == "ok":
        lines.append(f"12 repository              {repo['branch']} @ {repo['head'][:12]} "
                     f"({'clean' if repo['clean'] else str(repo['dirty_count']) + ' dirty'})")
    else:
        lines.append(f"12 repository              unavailable")
    branches = p["branches"]
    lines.append(f"13 active branches         {branches.get('count', 0)} "
                 f"({branches.get('agent_branches', 0)} agent)")
    lines.append(f"14 integration candidates  {p['integration_candidates']['count']}")
    host = p["resources"]["host"]
    lines.append(f"15 resource usage          {host['total_memory_gib']} GiB RAM, "
                 f"{host['cpu_count']} CPU, {host['disk_free_gib']} GiB free, "
                 f"peak RSS {host['peak_process_memory_mib']} MiB")
    qualification = p["local_model_qualification"]
    if qualification["status"] == "ok":
        lines.append(
            f"16 model qualification     {qualification['evaluated_models']}/"
            f"{qualification['eligible_models']} eligible models evaluated, "
            f"{qualification['qualified_pairs']} qualified model-role pair(s), "
            f"{qualification['roles_routed']}/{qualification['roles']} roles routed"
        )
        lines.append(f"     certification: {qualification['certification']}")
        lines.append(f"     detail: {qualification['detail_command']}")
    else:
        lines.append("16 model qualification     no evidence recorded yet")
    lines.append("")
    lines.append(state["limitation"])
    return "\n".join(lines) + "\n"
