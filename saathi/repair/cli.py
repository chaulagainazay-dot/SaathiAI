"""Auto-Repair / Reliability CLI — `python -m saathi.repair.cli <mode>`.

Modes:
  inspect                    read-only environment + failure analysis, no edits
  diagnose                   collection check + critical manifest + server import
  repair --test <node-id>    targeted diagnose/repair of one failing test
  loop --max-cycles N        bounded repair loop (default 3, never infinite)
  report                     latest repair journal entry + open known failures
  critical                   run the critical regression manifest only
  latest                     diagnose + attempt a SAFE repair of latest incident
  incident <id> | rollback <id> | history    (repair-record operations)

Exit codes:
  0 all requested checks passed        4 medium/high-risk repair needs review
  1 unresolved test failures           5 regression introduced
  2 invalid command or configuration   6 test infrastructure failure
  3 unsafe working-tree state          7 max repair cycles reached, unresolved

Never pushes, never deploys.
"""
from __future__ import annotations

import json
import sys

from saathi.repair import AutoRepairLoop, RepairIncident, RepairHistory
from saathi.repair.incident import RepairEvidence, RepairStatus, PolicyDecision

EXIT_OK = 0
EXIT_FAILURES = 1
EXIT_BAD_COMMAND = 2
EXIT_UNSAFE_TREE = 3
EXIT_NEEDS_REVIEW = 4
EXIT_REGRESSION = 5
EXIT_INFRA = 6
EXIT_MAX_CYCLES = 7


def _latest_incident() -> RepairIncident:
    from saathi.repair import evidence as ev_mod
    ev = ev_mod.collect(RepairEvidence())
    inc = RepairIncident(source="scheduled", evidence=ev)
    if ev.server_import_ok is False:
        inc.stack_trace = "server import failed: " + (ev.stack_trace or "")
    return inc


def _emit(obj: dict) -> None:
    print(json.dumps(obj, indent=1, default=str))


def cmd_inspect() -> int:
    """Read-only: environment + git + baseline + open failures. Never edits."""
    from saathi.repair import evidence as ev_mod
    from saathi.repair.baseline import read_baseline
    from saathi.repair.known_failures import KnownFailures
    import platform
    ev = ev_mod.collect(RepairEvidence())
    _emit({
        "branch": ev.git_branch, "head": ev.git_head,
        "dirty_files": ev.git_dirty_files,
        "python": platform.python_version(),
        "server_import": ev.server_import_ok, "route_count": ev.route_count,
        "health": ev.health_overall,
        "env_presence": ev.env_presence,
        "baseline": read_baseline(),
        "open_known_failures": KnownFailures().open_failures(),
    })
    return EXIT_OK


def cmd_diagnose() -> int:
    """Collection check + critical manifest + server import + route count."""
    from saathi.repair import verify as verify_mod
    from saathi.repair.manifest import run_critical_checks
    collect = verify_mod.run_pytest(["tests/", "--collect-only", "-q"])
    if not collect.ran:
        _emit({"error": "test infrastructure failure", "detail": collect.raw_tail})
        return EXIT_INFRA
    checks = run_critical_checks()
    _emit({"collection_errors": collect.errors, "critical_checks": checks})
    if collect.errors:
        return EXIT_FAILURES
    return EXIT_OK if checks.get("_all_ok") else EXIT_FAILURES


def cmd_repair(node_id: str) -> int:
    """Targeted: rerun one node, build an incident from its failure, diagnose."""
    from saathi.repair.manifest import validate_node_id
    from saathi.repair import verify as verify_mod
    if not validate_node_id(node_id):
        _emit({"error": f"invalid test node id: {node_id!r}"})
        return EXIT_BAD_COMMAND
    out = verify_mod.run_pytest([node_id])
    if not out.ran:
        _emit({"error": "test infrastructure failure", "detail": out.raw_tail})
        return EXIT_INFRA
    if out.failed == 0 and out.errors == 0:
        _emit({"node": node_id, "status": "already passing", **out.to_dict()})
        return EXIT_OK
    inc = RepairIncident(source="user_report", failed_tests=[node_id],
                         stack_trace=out.raw_tail)
    loop = AutoRepairLoop()
    result = loop.run(inc)
    _emit(result.to_dict())
    if result.status == RepairStatus.REPAIRED:
        return EXIT_OK
    if inc.policy in (PolicyDecision.APPROVAL_REQUIRED, PolicyDecision.MANUAL_ONLY):
        return EXIT_NEEDS_REVIEW
    return EXIT_FAILURES


def cmd_loop(max_cycles: int) -> int:
    """Bounded repair loop with no-progress detection. Never infinite."""
    from saathi.repair import rollback as rb
    from saathi.repair.journal import write_run_report
    if max_cycles < 1 or max_cycles > 10:
        _emit({"error": "max-cycles must be 1..10"})
        return EXIT_BAD_COMMAND
    if rb.dirty_files():
        _emit({"error": "unsafe working tree: uncommitted changes present"})
        return EXIT_UNSAFE_TREE

    loop = AutoRepairLoop()
    last_fp = None
    for cycle in range(1, max_cycles + 1):
        inc = _latest_incident()
        loop.diagnose(inc)
        fp = inc.fingerprint()
        if inc.category.value == "UNKNOWN" and inc.evidence.server_import_ok:
            _emit({"cycle": cycle, "status": "no actionable failure detected"})
            return EXIT_OK
        if fp == last_fp:
            _emit({"cycle": cycle, "status": "no progress — same fingerprint, stopping",
                   "fingerprint": fp})
            write_run_report({"status": "blocked", "message": "no progress",
                              "incident_id": inc.incident_id})
            return EXIT_MAX_CYCLES
        last_fp = fp
        result = loop.run(inc)
        write_run_report(result.to_dict())
        if result.status == RepairStatus.REPAIRED:
            continue
        if result.status in (RepairStatus.MANUAL_REQUIRED,):
            _emit(result.to_dict())
            return EXIT_NEEDS_REVIEW
        if result.regression and result.regression.get("new_regressions"):
            _emit(result.to_dict())
            return EXIT_REGRESSION
    _emit({"status": "max cycles reached", "cycles": max_cycles})
    return EXIT_MAX_CYCLES


def cmd_report() -> int:
    from saathi.repair.journal import latest_report
    from saathi.repair.known_failures import KnownFailures
    from saathi.repair.baseline import read_baseline
    _emit({"latest_run": latest_report(),
           "open_failures": KnownFailures().open_failures(),
           "baseline": read_baseline()})
    return EXIT_OK


def cmd_critical() -> int:
    from saathi.repair.manifest import run_critical_checks
    checks = run_critical_checks()
    _emit(checks)
    return EXIT_OK if checks.get("_all_ok") else EXIT_FAILURES


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print(__doc__)
        return EXIT_OK
    cmd, *rest = argv
    hist = RepairHistory()

    try:
        if cmd == "inspect":
            return cmd_inspect()
        if cmd == "diagnose":
            return cmd_diagnose()
        if cmd == "repair":
            if len(rest) >= 2 and rest[0] == "--test":
                return cmd_repair(rest[1])
            _emit({"error": "usage: repair --test <node-id>"})
            return EXIT_BAD_COMMAND
        if cmd == "loop":
            n = 3
            if len(rest) >= 2 and rest[0] == "--max-cycles":
                try:
                    n = int(rest[1])
                except ValueError:
                    return EXIT_BAD_COMMAND
            return cmd_loop(n)
        if cmd == "report":
            return cmd_report()
        if cmd == "critical":
            return cmd_critical()
        if cmd == "latest":
            out = AutoRepairLoop(history=hist).run(_latest_incident())
            _emit(out.to_dict())
            return EXIT_OK if out.status == RepairStatus.REPAIRED else EXIT_FAILURES
        if cmd == "incident" and rest:
            rec = hist.get(rest[0])
            _emit(rec or {"error": "not found"})
            return EXIT_OK if rec else EXIT_BAD_COMMAND
        if cmd == "rollback" and rest:
            from saathi.repair import rollback as rb
            rec = hist.get(rest[0])
            if not rec or not rec.get("rollback_commit"):
                _emit({"error": "no rollback ref for incident"})
                return EXIT_BAD_COMMAND
            ok = rb.rollback_to(rec["rollback_commit"])
            _emit({"rolled_back": ok, "to": rec["rollback_commit"]})
            return EXIT_OK if ok else EXIT_INFRA
        if cmd == "history":
            _emit({"history": hist.all()})
            return EXIT_OK
    except Exception as exc:  # infrastructure failure, not a test result
        _emit({"error": "repair infrastructure failure", "detail": repr(exc)[:300]})
        return EXIT_INFRA

    print(f"unknown command: {cmd}\n{__doc__}")
    return EXIT_BAD_COMMAND


if __name__ == "__main__":
    raise SystemExit(main())
