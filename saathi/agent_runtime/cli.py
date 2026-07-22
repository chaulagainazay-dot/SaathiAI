"""M10 Agent Runtime CLI — `python -m saathi.agent_runtime.cli <cmd>`.

  inspect                     runtime + registry summary (read-only)
  list                        list agent definitions (read-only)
  run --agent X --input "..." single-agent run
  run-team --input "..."      multi-agent orchestration
  status <run-id>             run state + metrics (read-only)
  events <run-id>             run events (read-only)
  pause|resume|cancel <run-id>
  health                      registry + recent runs (read-only)

Exit codes: 0 ok/completed · 1 partial/failed · 2 bad command · 4 awaiting approval.
Read-only commands never mutate. CLI cannot resolve approvals (user-only).
"""
from __future__ import annotations

import json
import sys

from saathi.agent_runtime import registry
from saathi.agent_runtime.orchestrator import default_orchestrator
from saathi.agent_runtime.models import RunState

EXIT_OK, EXIT_FAIL, EXIT_BAD, EXIT_APPROVAL = 0, 1, 2, 4


def _emit(obj) -> None:
    print(json.dumps(obj, indent=1, default=str))


def _run_exit(outcome: dict) -> int:
    st = outcome.get("state")
    if st == RunState.COMPLETED.value:
        return EXIT_OK
    if st == RunState.AWAITING_APPROVAL.value:
        return EXIT_APPROVAL
    return EXIT_FAIL


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print(__doc__)
        return EXIT_OK
    cmd, *rest = argv
    orch = default_orchestrator()

    if cmd == "inspect" or cmd == "health":
        _emit({"agents": [a.agent_id for a in registry.all_agents()],
               "recent_runs": orch.store.list_runs(limit=10)})
        return EXIT_OK
    if cmd == "list":
        _emit({"agents": [a.to_dict() for a in registry.all_agents()]})
        return EXIT_OK
    if cmd == "run":
        if len(rest) >= 4 and rest[0] == "--agent" and rest[2] == "--input":
            agent, text = rest[1], rest[3]
            if not registry.get(agent):
                _emit({"error": f"unknown agent {agent}"})
                return EXIT_BAD
            rid = orch.create_run(text, strategy="build")  # single dominated by chosen
            out = orch.run(rid)
            _emit(out)
            return _run_exit(out)
        _emit({"error": "usage: run --agent <id> --input \"...\""})
        return EXIT_BAD
    if cmd == "run-team":
        if len(rest) >= 2 and rest[0] == "--input":
            rid = orch.create_run(rest[1])
            out = orch.run(rid)
            _emit(out)
            return _run_exit(out)
        _emit({"error": "usage: run-team --input \"...\""})
        return EXIT_BAD
    if cmd in ("status", "events", "pause", "resume", "cancel") and rest:
        rid = rest[0]
        if not orch.store.get_run(rid):
            _emit({"error": "run not found"})
            return EXIT_BAD
        if cmd == "status":
            _emit(orch.store.get_run(rid) | {"metrics": orch.store.metrics(rid)})
            return EXIT_OK
        if cmd == "events":
            _emit({"events": orch.store.events(rid, limit=100)})
            return EXIT_OK
        if cmd == "pause":
            orch.pause(rid); _emit({"paused": rid}); return EXIT_OK
        if cmd == "resume":
            out = orch.resume(rid); _emit(out); return _run_exit(out)
        if cmd == "cancel":
            orch.cancel(rid); _emit({"cancelled": rid}); return EXIT_OK

    print(f"unknown command: {cmd}\n{__doc__}")
    return EXIT_BAD


if __name__ == "__main__":
    raise SystemExit(main())
