"""M20.0 Engineering Orchestrator CLI — `python -m saathi.engineering <cmd>`.

  status                 settings + session census (read-only)
  backlog                list backlog items (read-only)
  inspect <item>         item detail (read-only)
  select                 deterministic candidate selection
  plan <item>            generate bounded prompt (no launch)
  readiness              repository readiness report
  launch <item>          launch agent (requires enable flags)
  monitor <session>      progress snapshot
  pause <session>        graceful stop (alias)
  stop <session>         stop session [--force]
  validate <item>        run validation plan
  resume <item>          re-queue ready if partial/failed
  handoff                show/write current handoff summary
  history                recent orchestrator events
  pilot                  run harmless mock pilot
  security               trading-guardian isolation report

No --unsafe, --skip-approval, --force-push, --deploy, or free-form shell.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_BAD = 2
EXIT_BLOCKED = 3
EXIT_APPROVAL = 4


def _emit(obj) -> None:
    print(json.dumps(obj, indent=1, default=str))


def _orch(**kwargs):
    from saathi.engineering.orchestrator import default_orchestrator
    return default_orchestrator(**kwargs)


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        return EXIT_OK

    cmd, *rest = argv

    if cmd == "status":
        _emit(_orch().status())
        return EXIT_OK

    if cmd == "backlog":
        _emit({"items": _orch().backlog()})
        return EXIT_OK

    if cmd == "inspect" and rest:
        r = _orch().inspect(rest[0])
        _emit(r)
        return EXIT_OK if "error" not in r else EXIT_BAD

    if cmd == "select":
        _emit(_orch().select())
        return EXIT_OK

    if cmd == "plan" and rest:
        _emit(_orch().plan(rest[0]))
        return EXIT_OK

    if cmd == "readiness":
        _emit(_orch().readiness())
        return EXIT_OK

    if cmd == "launch" and rest:
        item = rest[0]
        adapter = "mock"
        write = False
        if "--adapter" in rest:
            i = rest.index("--adapter")
            if i + 1 < len(rest):
                adapter = rest[i + 1]
        if "--write" in rest:
            write = True
        # Forbidden flags
        for bad in ("--unsafe", "--skip-approval", "--force-push", "--deploy"):
            if bad in rest:
                _emit({"error": f"forbidden_flag:{bad}"})
                return EXIT_BAD
        r = _orch().launch(item, adapter_name=adapter, write_enabled=write)
        _emit(r.to_dict())
        if r.ok:
            return EXIT_OK
        if r.verdict in ("blocked", "validation_pending"):
            return EXIT_BLOCKED
        return EXIT_FAIL

    if cmd == "monitor" and rest:
        from saathi.engineering.monitor import ProgressMonitor
        o = _orch()
        snap = o.monitor.snapshot(rest[0])
        _emit(snap.to_dict())
        return EXIT_OK

    if cmd in ("stop", "pause") and rest:
        force = "--force" in rest
        r = _orch().stop(rest[0], force=force)
        _emit(r)
        return EXIT_OK if "error" not in r else EXIT_BAD

    if cmd == "validate" and rest:
        _emit(_orch().validate_item(rest[0]))
        return EXIT_OK

    if cmd == "resume" and rest:
        from saathi.engineering.models import ItemStatus
        o = _orch()
        item = o.store.get_item(rest[0])
        if not item:
            _emit({"error": "not_found"})
            return EXIT_BAD
        if item.status not in (
            ItemStatus.PARTIAL.value, ItemStatus.FAILED.value,
            ItemStatus.STOPPED.value,
        ):
            _emit({"error": f"cannot_resume_from:{item.status}"})
            return EXIT_BAD
        try:
            o.store.set_status(item.item_id, ItemStatus.READY)
        except ValueError as exc:
            _emit({"error": str(exc)})
            return EXIT_FAIL
        _emit({"item_id": item.item_id, "status": ItemStatus.READY.value})
        return EXIT_OK

    if cmd == "handoff":
        from saathi.engineering.handoff import HANDOFF_DIR_NAME, HANDOFF_MD, SESSION_JSON
        from saathi.config import ROOT
        base = Path(ROOT) / HANDOFF_DIR_NAME
        md = base / HANDOFF_MD
        js = base / SESSION_JSON
        _emit({
            "handoff_md": str(md) if md.exists() else None,
            "session_json": str(js) if js.exists() else None,
            "session": json.loads(js.read_text()) if js.exists() else None,
        })
        return EXIT_OK

    if cmd == "history":
        _emit({"history": _orch().history()})
        return EXIT_OK

    if cmd == "pilot":
        from saathi.engineering.pilot import run_first_pilot
        import tempfile
        # Isolated store under data/engineering/pilot-run or tmp
        store = Path(tempfile.mkdtemp(prefix="m20_pilot_"))
        r = run_first_pilot(store_dir=store, enable_orchestrator=True, enable_launch=True)
        _emit(r)
        ok = bool((r.get("result") or {}).get("ok"))
        return EXIT_OK if ok else EXIT_FAIL

    if cmd == "security":
        from saathi.engineering.security import (
            trading_guardian_isolation_report,
            assert_no_trading_imports,
        )
        from pathlib import Path as P
        pkg = P(__file__).resolve().parent
        _emit({
            "trading_guardian": trading_guardian_isolation_report(),
            "import_violations": assert_no_trading_imports(pkg),
        })
        return EXIT_OK

    _emit({"error": "unknown_or_bad_command", "cmd": cmd, "hint": "help"})
    return EXIT_BAD


if __name__ == "__main__":
    raise SystemExit(main())
