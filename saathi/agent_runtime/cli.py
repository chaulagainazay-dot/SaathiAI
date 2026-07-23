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
        from saathi.agent_runtime.contracts import contract_summary

        _emit(
            {
                "agents": [a.agent_id for a in registry.all_agents()],
                "recent_runs": orch.store.list_runs(limit=10),
                "m48_1_contract": contract_summary(),
            }
        )
        return EXIT_OK
    if cmd == "contract":
        # Read-only M48.1 contract inventory (never executes agents/tools).
        from saathi.agent_runtime.contracts import contract_summary

        _emit(contract_summary())
        return EXIT_OK
    if cmd == "lifecycle-health":
        from saathi.agent_runtime.lifecycle import provider_health_evidence

        _emit({"providers": [p.to_dict() for p in provider_health_evidence()]})
        return EXIT_OK
    if cmd == "recover" and rest:
        from saathi.agent_runtime.lifecycle import RunLifecycleController

        _emit(RunLifecycleController(orch.store).recover_run(rest[0]))
        return EXIT_OK
    if cmd == "recover-all":
        from saathi.agent_runtime.lifecycle import RunLifecycleController

        _emit(RunLifecycleController(orch.store).recover_all())
        return EXIT_OK
    if cmd == "reconcile-all":
        from saathi.agent_runtime.lifecycle import RunLifecycleController

        _emit(RunLifecycleController(orch.store).reconcile_all())
        return EXIT_OK
    if cmd == "kill-switch":
        from saathi.agent_runtime.lifecycle import RunLifecycleController

        scope = rest[0] if rest else "all"
        rid = rest[1] if len(rest) > 1 else ""
        lc = RunLifecycleController(orch.store)
        if scope == "run":
            _emit(lc.kill_switch(scope="run", run_id=rid))
        elif scope == "mission":
            _emit(lc.kill_switch(scope="mission", mission_id=rid))
        else:
            _emit(lc.kill_switch(scope="all"))
        return EXIT_OK
    if cmd == "list":
        _emit({"agents": [a.to_dict() for a in registry.all_agents()]})
        return EXIT_OK
    # M49.1 read-only tool diagnostics (never executes arbitrary tools)
    if cmd == "tools":
        from saathi.tool_runtime.registry import default_registry

        reg = default_registry()
        sub = rest[0] if rest else "list"
        if sub == "list":
            _emit(
                {
                    "tools": [m.to_public_dict() for m in reg.list_manifests(include_disabled=True)],
                    "count": len(reg.list_manifests(include_disabled=True)),
                }
            )
            return EXIT_OK
        if sub == "inspect" and len(rest) >= 2:
            m = reg.get_manifest(rest[1])
            if not m:
                _emit({"error": "tool not found", "tool_id": rest[1]})
                return EXIT_BAD
            _emit(m.to_public_dict())
            return EXIT_OK
        if sub == "validate":
            _emit(reg.validate_all())
            return EXIT_OK
        if sub == "capability-matrix":
            _emit({"matrix": reg.capability_matrix()})
            return EXIT_OK
        if sub == "reconcile-idempotency":
            # Read/repair stale durable idempotency leases only — no tool execute
            from saathi.tool_runtime.durable_idempotency import (
                default_durable_idempotency_store,
            )

            _emit(default_durable_idempotency_store().reconcile_stale())
            return EXIT_OK
        _emit(
            {
                "error": "usage: tools list|inspect <id>|validate|capability-matrix|reconcile-idempotency",
                "note": "read-only diagnostics; no generic tool execute command",
            }
        )
        return EXIT_BAD
    if cmd == "run":
        if len(rest) >= 4 and rest[0] == "--agent" and rest[2] == "--input":
            from saathi.agent_runtime.service import start_agent_run

            agent, text = rest[1], rest[3]
            if not registry.get(agent):
                _emit({"error": f"unknown agent {agent}"})
                return EXIT_BAD
            rec = start_agent_run(
                objective=text,
                strategy="build",
                execute=True,
                orchestrator=orch,
                authority_class="READ_ONLY",
            )
            if not rec.ok:
                _emit(rec.to_dict())
                return EXIT_FAIL
            out = rec.outcome or {"run_id": rec.run_id, "state": rec.state}
            _emit(out)
            return _run_exit(out)
        _emit({"error": "usage: run --agent <id> --input \"...\""})
        return EXIT_BAD
    if cmd == "run-team":
        if len(rest) >= 2 and rest[0] == "--input":
            from saathi.agent_runtime.service import start_agent_run

            rec = start_agent_run(
                objective=rest[1],
                execute=True,
                orchestrator=orch,
                authority_class="READ_ONLY",
            )
            if not rec.ok:
                _emit(rec.to_dict())
                return EXIT_FAIL
            out = rec.outcome or {"run_id": rec.run_id, "state": rec.state}
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
