"""Auto-Repair CLI — `python -m saathi.repair.cli <command>`.

Commands:
  diagnose                 collect evidence + classify the latest failure (read-only)
  latest                   diagnose + attempt a SAFE repair of the latest incident
  incident <id>            show a stored incident record
  verify <id>              re-run the verification ladder for an incident
  rollback <id>            restore the repair's rollback point (operator action)
  report <id>              print the repair report
  history                  list repair history

Never pushes, never deploys.
"""
from __future__ import annotations

import json
import sys

from saathi.repair import AutoRepairLoop, RepairIncident, RepairHistory
from saathi.repair.incident import RepairEvidence


def _latest_incident() -> RepairIncident:
    """Build an incident from the current repo/runtime state (best-effort)."""
    from saathi.repair import evidence as ev_mod
    ev = ev_mod.collect(RepairEvidence())
    inc = RepairIncident(source="scheduled", evidence=ev)
    if ev.server_import_ok is False:
        inc.stack_trace = "server import failed: " + (ev.stack_trace or "")
    return inc


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    if not argv:
        print(__doc__)
        return 0
    cmd, *rest = argv
    hist = RepairHistory()
    loop = AutoRepairLoop(history=hist)

    if cmd == "diagnose":
        inc = loop.diagnose(_latest_incident())
        print(json.dumps({"incident_id": inc.incident_id,
                          "category": inc.category.value,
                          "confidence": inc.confidence,
                          "policy": inc.policy.value,
                          "subsystem": inc.subsystem}, indent=1))
        return 0
    if cmd == "latest":
        out = loop.run(_latest_incident())
        print(json.dumps(out.to_dict(), indent=1))
        return 0
    if cmd == "incident" and rest:
        rec = hist.get(rest[0])
        print(json.dumps(rec or {"error": "not found"}, indent=1))
        return 0 if rec else 1
    if cmd == "rollback" and rest:
        from saathi.repair import rollback as rb
        rec = hist.get(rest[0])
        if not rec or not rec.get("rollback_commit"):
            print(json.dumps({"error": "no rollback ref for incident"}))
            return 1
        ok = rb.rollback_to(rec["rollback_commit"])
        print(json.dumps({"rolled_back": ok, "to": rec["rollback_commit"]}))
        return 0 if ok else 1
    if cmd in ("report", "verify") and rest:
        rec = hist.get(rest[0])
        print(json.dumps(rec or {"error": "not found"}, indent=1))
        return 0 if rec else 1
    if cmd == "history":
        print(json.dumps(hist.all(), indent=1))
        return 0

    print(f"unknown command: {cmd}\n{__doc__}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
