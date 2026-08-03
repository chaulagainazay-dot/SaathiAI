"""M350 — Agent environment control surface.

    python -m saathi.agentdev <command> [...]

Extends the established SaathiOS CLI conventions rather than introducing a
second framework: ``argparse`` sub-parsers as in ``saathi/platform/cli.py``,
structured JSON on stdout as in ``saathi/engineering/cli.py``, and named exit
codes.

Every state-changing command accepts ``--dry-run``. Nothing here can merge,
push, deploy, use a credential or touch trading: those verbs do not exist in
this module, and the settings denial block is re-applied on every load.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_USAGE = 2
EXIT_REFUSED = 3
EXIT_NOT_FOUND = 4

#: Flags this CLI refuses outright, so a caller cannot smuggle intent past the
#: argument parser by copying a habit from another tool.
FORBIDDEN_FLAGS = (
    "--force", "--unsafe", "--skip-approval", "--skip-gate", "--no-verify",
    "--force-push", "--deploy", "--merge", "--push", "--write-anywhere",
    "--live", "--trade",
)


def _emit(payload: Any) -> None:
    print(json.dumps(payload, indent=1, default=str))


def _stores(args: argparse.Namespace):
    from saathi.agentdev.artifacts import ArtifactStore
    from saathi.agentdev.missions import DevMissionStore
    from saathi.agentdev.settings import load_settings

    settings = load_settings(
        **({"store_dir": args.store} if getattr(args, "store", None) else {})
    )
    root = settings.store_path()
    return settings, ArtifactStore(root), DevMissionStore(root)


# --------------------------------------------------------------------------
# doctor
# --------------------------------------------------------------------------


def cmd_doctor(args: argparse.Namespace) -> int:
    from saathi.agentdev.roles import RoleValidationError, registry_summary
    from saathi.agentdev.worktrees import WorktreeManager

    settings, _, missions = _stores(args)
    report: dict[str, Any] = {
        "settings": settings.to_dict(),
        "denials": settings.denials(),
    }

    try:
        summary = registry_summary()
        report["registry"] = {
            "status": "ok",
            "roles": summary["count"],
            "implementation_roles": summary["implementation_roles"],
            "gate_approvers": summary["gate_approvers"],
            "security_veto": summary["security_veto"],
        }
    except RoleValidationError as exc:
        report["registry"] = {"status": "invalid", "code": exc.code, "detail": exc.detail}

    try:
        census = WorktreeManager(settings=settings).inspect_environment()
        report["worktrees"] = {
            "counts": census["counts"],
            "findings": census["findings"],
        }
    except Exception as exc:  # pragma: no cover — git absent or unreadable
        report["worktrees"] = {"status": "unavailable", "error": str(exc)}

    report["missions"] = {
        "count": len(missions.list()),
        "store": str(settings.store_path()),
    }
    report["authority"] = {
        "worktree_creation": settings.worktree_creation_enabled,
        "agentdev_enabled": settings.agentdev_enabled,
        "note": "All denials are re-applied after every settings load.",
    }
    _emit(report)
    ok = report["registry"].get("status") == "ok"
    return EXIT_OK if ok else EXIT_FAIL


# --------------------------------------------------------------------------
# agents
# --------------------------------------------------------------------------


def cmd_agent_list(args: argparse.Namespace) -> int:
    from saathi.agentdev.roles import list_roles

    _emit({
        "roles": [
            {
                "agent_id": r.agent_id,
                "role_name": r.role_name,
                "max_authority": r.max_authority.name,
                "worktree": r.default_worktree_mode,
                "writes_code": r.may_write_code,
                "approves_gates": r.may_approve_gates,
                "escalates_to": r.escalation_to,
                "reviewed_by": list(r.independent_review_by),
            }
            for r in list_roles()
        ]
    })
    return EXIT_OK


def cmd_agent_show(args: argparse.Namespace) -> int:
    from saathi.agentdev.roles import get_role

    role = get_role(args.agent_id)
    if role is None:
        _emit({"error": "unknown_agent_id", "agent_id": args.agent_id})
        return EXIT_NOT_FOUND
    _emit(role.to_dict())
    return EXIT_OK


# --------------------------------------------------------------------------
# missions
# --------------------------------------------------------------------------


def cmd_mission_create(args: argparse.Namespace) -> int:
    from saathi.agentdev.missions import MissionError

    _, _, missions = _stores(args)
    if args.dry_run:
        _emit({
            "dry_run": True,
            "would_create": {
                "title": args.title,
                "objective": args.objective,
                "starting_sha": args.sha,
                "participants": args.participant or [],
            },
        })
        return EXIT_OK
    try:
        mission = missions.create(
            title=args.title,
            objective=args.objective,
            starting_sha=args.sha,
            participants=args.participant or [],
        )
    except MissionError as exc:
        _emit({"error": exc.code, "detail": exc.detail})
        return EXIT_REFUSED
    _emit(missions.status(mission.dev_mission_id))
    return EXIT_OK


def cmd_mission_list(args: argparse.Namespace) -> int:
    _, _, missions = _stores(args)
    _emit({
        "missions": [
            {
                "dev_mission_id": m.dev_mission_id,
                "title": m.title,
                "state": m.state,
                "terminal_verdict": m.terminal_verdict or None,
                "open_vetoes": m.open_vetoes,
            }
            for m in missions.list()
        ]
    })
    return EXIT_OK


def cmd_mission_status(args: argparse.Namespace) -> int:
    from saathi.agentdev.missions import MissionError

    _, _, missions = _stores(args)
    try:
        _emit(missions.status(args.mission_id))
    except MissionError as exc:
        _emit({"error": exc.code, "detail": exc.detail})
        return EXIT_NOT_FOUND
    return EXIT_OK


def cmd_mission_advance(args: argparse.Namespace) -> int:
    from saathi.agentdev.missions import MissionError

    _, _, missions = _stores(args)
    try:
        if args.dry_run:
            status = missions.status(args.mission_id)
            _emit({
                "dry_run": True,
                "current_state": status["state"],
                "requested_state": args.state,
                "unmet_exit_gates": status["unmet_exit_gates"],
                "open_vetoes": status["open_vetoes"],
                "would_succeed": (
                    not status["unmet_exit_gates"]
                    and not status["open_vetoes"]
                    and args.state in status["next_states"]
                ),
            })
            return EXIT_OK
        missions.advance(args.mission_id, args.state, actor=args.actor, reason=args.reason)
    except MissionError as exc:
        _emit({"error": exc.code, "detail": exc.detail})
        return EXIT_REFUSED
    _emit(missions.status(args.mission_id))
    return EXIT_OK


# --------------------------------------------------------------------------
# worktrees
# --------------------------------------------------------------------------


def cmd_worktree_census(args: argparse.Namespace) -> int:
    from saathi.agentdev.worktrees import WorktreeManager

    settings, _, _ = _stores(args)
    _emit(WorktreeManager(settings=settings).inspect_environment())
    return EXIT_OK


def cmd_worktree_plan(args: argparse.Namespace) -> int:
    from saathi.agentdev.worktrees import WorktreeError, WorktreeManager

    settings, _, _ = _stores(args)
    manager = WorktreeManager(settings=settings)
    try:
        plan = manager.plan(
            agent_id=args.agent_id,
            mission_id=args.mission_id,
            description=args.description,
            base_ref=args.base_ref,
            mode=args.mode,
        )
    except WorktreeError as exc:
        _emit({"error": exc.code, "detail": exc.detail})
        return EXIT_REFUSED
    _emit(plan.to_dict())
    return EXIT_OK if plan.allowed else EXIT_REFUSED


def cmd_worktree_create(args: argparse.Namespace) -> int:
    from saathi.agentdev.worktrees import WorktreeError, WorktreeManager

    settings, _, _ = _stores(args)
    manager = WorktreeManager(settings=settings)
    try:
        plan = manager.plan(
            agent_id=args.agent_id,
            mission_id=args.mission_id,
            description=args.description,
            base_ref=args.base_ref,
            mode="writable",
        )
        record = manager.create(plan, dry_run=args.dry_run)
    except PermissionError as exc:
        _emit({"error": "permission_denied", "detail": str(exc)})
        return EXIT_REFUSED
    except WorktreeError as exc:
        _emit({"error": exc.code, "detail": exc.detail})
        return EXIT_REFUSED
    _emit({"dry_run": args.dry_run, "worktree": record.to_dict()})
    return EXIT_OK


def cmd_worktree_inspect(args: argparse.Namespace) -> int:
    from saathi.agentdev.worktrees import WorktreeError, WorktreeManager

    settings, _, _ = _stores(args)
    try:
        _emit(WorktreeManager(settings=settings).inspect(args.name).to_dict())
    except WorktreeError as exc:
        _emit({"error": exc.code, "detail": exc.detail})
        return EXIT_NOT_FOUND
    return EXIT_OK


def cmd_worktree_removal_plan(args: argparse.Namespace) -> int:
    from saathi.agentdev.worktrees import WorktreeError, WorktreeManager

    settings, _, _ = _stores(args)
    try:
        plan = WorktreeManager(settings=settings).removal_plan(args.name)
    except WorktreeError as exc:
        _emit({"error": exc.code, "detail": exc.detail})
        return EXIT_NOT_FOUND
    _emit(plan)
    return EXIT_OK if plan["safe_to_remove"] else EXIT_REFUSED


# --------------------------------------------------------------------------
# meetings
# --------------------------------------------------------------------------


def cmd_meeting_list(args: argparse.Namespace) -> int:
    from saathi.agentdev.meetings import MeetingRunner

    settings, artifacts, missions = _stores(args)
    runner = MeetingRunner(artifacts, missions, root=settings.store_path())
    _emit({
        "meetings": [
            {
                "meeting_id": m.meeting_id,
                "type": m.meeting_type,
                "phase": m.phase,
                "chair": m.chair,
                "outcome": m.outcome or None,
                "unanswered_challenges": m.unanswered_challenges,
            }
            for m in runner.list(args.mission_id)
        ]
    })
    return EXIT_OK


def cmd_meeting_status(args: argparse.Namespace) -> int:
    from saathi.agentdev.meetings import MeetingError, MeetingRunner

    settings, artifacts, missions = _stores(args)
    runner = MeetingRunner(artifacts, missions, root=settings.store_path())
    try:
        _emit(runner.status(args.mission_id, args.meeting_id))
    except MeetingError as exc:
        _emit({"error": exc.code, "detail": exc.detail})
        return EXIT_NOT_FOUND
    return EXIT_OK


def cmd_meeting_participants(args: argparse.Namespace) -> int:
    from saathi.agentdev.meetings import MeetingType, required_participants

    try:
        participants = required_participants(args.meeting_type)
    except ValueError:
        _emit({
            "error": "unknown_meeting_type",
            "known": [t.value for t in MeetingType],
        })
        return EXIT_USAGE
    _emit({"meeting_type": args.meeting_type, "required_participants": list(participants)})
    return EXIT_OK


# --------------------------------------------------------------------------
# gates and review
# --------------------------------------------------------------------------


def cmd_gate_report(args: argparse.Namespace) -> int:
    from saathi.agentdev.gates import GateEngine
    from saathi.agentdev.missions import MissionError

    _, artifacts, missions = _stores(args)
    try:
        _emit(GateEngine(artifacts, missions).report(args.mission_id))
    except MissionError as exc:
        _emit({"error": exc.code, "detail": exc.detail})
        return EXIT_NOT_FOUND
    return EXIT_OK


def cmd_gate_evaluate(args: argparse.Namespace) -> int:
    from saathi.agentdev.gates import GateEngine, GateError
    from saathi.agentdev.missions import MissionError

    _, artifacts, missions = _stores(args)
    engine = GateEngine(artifacts, missions)
    try:
        decision = engine.evaluate(
            args.mission_id,
            args.gate,
            approver=args.approver,
            subject_author=args.subject,
            evidence_artifact_ids=args.evidence or [],
        )
    except (GateError, MissionError) as exc:
        _emit({"error": exc.code, "detail": exc.detail})
        return EXIT_REFUSED
    _emit(decision.to_dict())
    return EXIT_OK if decision.allowed else EXIT_REFUSED


def cmd_review_standard(args: argparse.Namespace) -> int:
    from saathi.agentdev.gates import review_finding_requirements

    _emit(review_finding_requirements())
    return EXIT_OK


# --------------------------------------------------------------------------
# configuration protection
# --------------------------------------------------------------------------


def cmd_config_check(args: argparse.Namespace) -> int:
    from saathi.agentdev.config_protection import classify_path

    verdict = classify_path(args.path)
    _emit(verdict.to_dict())
    return EXIT_REFUSED if verdict.protected else EXIT_OK


def cmd_config_surface(args: argparse.Namespace) -> int:
    from saathi.agentdev.config_protection import protected_surface

    _emit(protected_surface())
    return EXIT_OK


# --------------------------------------------------------------------------
# verification and simulation
# --------------------------------------------------------------------------


def cmd_verify(args: argparse.Namespace) -> int:
    """Read-only completeness check over one mission."""
    from saathi.agentdev.gates import GateEngine
    from saathi.agentdev.missions import MissionError

    _, artifacts, missions = _stores(args)
    try:
        mission = missions.require(args.mission_id)
    except MissionError as exc:
        _emit({"error": exc.code, "detail": exc.detail})
        return EXIT_NOT_FOUND

    all_artifacts = artifacts.list(args.mission_id)
    gate_report = GateEngine(artifacts, missions).report(args.mission_id)
    problems: list[str] = []

    if mission.open_vetoes:
        problems.append("open_security_veto")
    if mission.state == "closed" and not mission.terminal_verdict:
        problems.append("closed_without_verdict")
    for row in gate_report["gates"]:
        if row["status"] == "passed" and not row["evidence"]:
            problems.append(f"gate_passed_without_evidence:{row['gate']}")
        if row["status"] == "passed" and row["approver"] == row["subject_author"]:
            problems.append(f"gate_self_approved:{row['gate']}")

    _emit({
        "dev_mission_id": args.mission_id,
        "state": mission.state,
        "terminal_verdict": mission.terminal_verdict or None,
        "artifact_count": len(all_artifacts),
        "artifact_kinds": sorted({a.kind for a in all_artifacts}),
        "unresolved_disagreements": mission.unresolved_disagreements,
        "open_vetoes": mission.open_vetoes,
        "gates": gate_report["gates"],
        "problems": problems,
        "verdict": "consistent" if not problems else "inconsistent",
    })
    return EXIT_OK if not problems else EXIT_FAIL


def cmd_simulate(args: argparse.Namespace) -> int:
    from saathi.agentdev.simulation import run_offline_mission

    result = run_offline_mission(store_dir=args.store, dry_run=args.dry_run)
    _emit(result)
    return EXIT_OK if result.get("completed") else EXIT_FAIL


# --------------------------------------------------------------------------
# parser
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m saathi.agentdev",
        description=(
            "SaathiOS multi-agent development environment. Read-only by "
            "default; every state-changing command supports --dry-run. "
            "Cannot merge, push, deploy, use credentials or trade."
        ),
    )
    parser.add_argument(
        "--store", default="", help="Override the agentdev store directory."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def _with_dry_run(p: argparse.ArgumentParser) -> argparse.ArgumentParser:
        p.add_argument(
            "--dry-run", action="store_true",
            help="Report what would happen without changing anything.",
        )
        return p

    doctor = sub.add_parser("doctor", help="Environment, settings and registry health.")
    doctor.set_defaults(func=cmd_doctor)

    agent = sub.add_parser("agent", help="Development-agent roles.").add_subparsers(
        dest="agent_command", required=True
    )
    agent.add_parser("list", help="List every declared role.").set_defaults(
        func=cmd_agent_list
    )
    show = agent.add_parser("show", help="Show one role contract.")
    show.add_argument("agent_id")
    show.set_defaults(func=cmd_agent_show)

    mission = sub.add_parser("mission", help="Development missions.").add_subparsers(
        dest="mission_command", required=True
    )
    create = _with_dry_run(mission.add_parser("create", help="Create a mission."))
    create.add_argument("--title", required=True)
    create.add_argument("--objective", required=True)
    create.add_argument("--sha", required=True, help="Starting repository SHA.")
    create.add_argument("--participant", action="append", help="Repeatable.")
    create.set_defaults(func=cmd_mission_create)
    mission.add_parser("list", help="List missions.").set_defaults(func=cmd_mission_list)
    status = mission.add_parser("status", help="Mission status and unmet gates.")
    status.add_argument("mission_id")
    status.set_defaults(func=cmd_mission_status)
    advance = _with_dry_run(mission.add_parser("advance", help="Advance the lifecycle."))
    advance.add_argument("mission_id")
    advance.add_argument("--state", required=True)
    advance.add_argument("--actor", required=True)
    advance.add_argument("--reason", default="")
    advance.set_defaults(func=cmd_mission_advance)

    worktree = sub.add_parser("worktree", help="Mission-bound worktrees.").add_subparsers(
        dest="worktree_command", required=True
    )
    worktree.add_parser(
        "census", help="Live git and registry census. Removes nothing."
    ).set_defaults(func=cmd_worktree_census)
    wplan = worktree.add_parser("plan", help="Propose a worktree. Creates nothing.")
    wplan.add_argument("--agent-id", required=True)
    wplan.add_argument("--mission-id", required=True)
    wplan.add_argument("--description", required=True)
    wplan.add_argument("--base-ref", default="HEAD")
    wplan.add_argument("--mode", default="writable", choices=["readonly", "writable"])
    wplan.set_defaults(func=cmd_worktree_plan)
    wcreate = _with_dry_run(worktree.add_parser("create", help="Create a worktree."))
    wcreate.add_argument("--agent-id", required=True)
    wcreate.add_argument("--mission-id", required=True)
    wcreate.add_argument("--description", required=True)
    wcreate.add_argument("--base-ref", default="HEAD")
    wcreate.set_defaults(func=cmd_worktree_create)
    winspect = worktree.add_parser("inspect", help="Cleanliness and contamination.")
    winspect.add_argument("name")
    winspect.set_defaults(func=cmd_worktree_inspect)
    wremove = worktree.add_parser(
        "removal-plan", help="Plan a removal. Never performs one."
    )
    wremove.add_argument("name")
    wremove.set_defaults(func=cmd_worktree_removal_plan)

    meeting = sub.add_parser("meeting", help="Structured meetings.").add_subparsers(
        dest="meeting_command", required=True
    )
    mlist = meeting.add_parser("list", help="Meetings for a mission.")
    mlist.add_argument("mission_id")
    mlist.set_defaults(func=cmd_meeting_list)
    mstatus = meeting.add_parser("status", help="One meeting's full state.")
    mstatus.add_argument("mission_id")
    mstatus.add_argument("meeting_id")
    mstatus.set_defaults(func=cmd_meeting_status)
    mpart = meeting.add_parser(
        "participants", help="Required participants for a meeting type."
    )
    mpart.add_argument("meeting_type")
    mpart.set_defaults(func=cmd_meeting_participants)

    gate = sub.add_parser("gate", help="Lifecycle gates.").add_subparsers(
        dest="gate_command", required=True
    )
    greport = gate.add_parser("report", help="Every gate and its status.")
    greport.add_argument("mission_id")
    greport.set_defaults(func=cmd_gate_report)
    geval = gate.add_parser("evaluate", help="Evaluate a gate. Writes nothing.")
    geval.add_argument("mission_id")
    geval.add_argument("--gate", required=True)
    geval.add_argument("--approver", required=True)
    geval.add_argument("--subject", required=True)
    geval.add_argument("--evidence", action="append", help="Repeatable artifact id.")
    geval.set_defaults(func=cmd_gate_evaluate)

    review = sub.add_parser("review", help="Review standard.").add_subparsers(
        dest="review_command", required=True
    )
    review.add_parser(
        "standard", help="The evidence a high or critical finding must carry."
    ).set_defaults(func=cmd_review_standard)

    config = sub.add_parser("config", help="Configuration protection.").add_subparsers(
        dest="config_command", required=True
    )
    ccheck = config.add_parser("check", help="Is this path protected?")
    ccheck.add_argument("path")
    ccheck.set_defaults(func=cmd_config_check)
    config.add_parser(
        "surface", help="The full protected surface."
    ).set_defaults(func=cmd_config_surface)

    verify = sub.add_parser("verify", help="Read-only consistency check of a mission.")
    verify.add_argument("mission_id")
    verify.set_defaults(func=cmd_verify)

    simulate = _with_dry_run(
        sub.add_parser("simulate", help="Run the offline simulated mission.")
    )
    simulate.set_defaults(func=cmd_simulate)

    return parser


def main(argv: list[str] | None = None) -> int:
    raw = list(argv if argv is not None else sys.argv[1:])
    for flag in raw:
        if flag in FORBIDDEN_FLAGS:
            _emit({
                "error": "forbidden_flag",
                "flag": flag,
                "detail": (
                    "This surface cannot force, skip approval, merge, push, "
                    "deploy or trade. The verb does not exist here."
                ),
            })
            return EXIT_USAGE

    parser = build_parser()
    try:
        args = parser.parse_args(raw)
    except SystemExit as exc:  # argparse already printed usage
        return int(exc.code or EXIT_USAGE)
    if not hasattr(args, "dry_run"):
        args.dry_run = False
    return int(args.func(args))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
