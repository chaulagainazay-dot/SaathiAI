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
  control-center         Control Center engineering facet (read-only)
  approve-readonly       create bound read-only approval for Claude launch
  integrity              capture/verify repository integrity snapshot
  ledger [session_id]    M20.5 session ledger census / timeline
  recover [--dry-run]    M20.5 reconcile stale/crashed sessions
  evidence <session_id>  M20.5 integrity evidence for session
  resume-plan <session>  M20.5 operator resume plan (no auto-launch)
  m20                    M20.7 unified console status (read-only)
  launch <item> --mode readonly [--adapter mock|claude_code] [--approval ID]

Writes/commits/pushes remain disabled unless explicit env flags are set.
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
        mode = "readonly"
        approval = ""
        if "--adapter" in rest:
            i = rest.index("--adapter")
            if i + 1 < len(rest):
                adapter = rest[i + 1]
        if "--mode" in rest:
            i = rest.index("--mode")
            if i + 1 < len(rest):
                mode = rest[i + 1]
        if "--approval" in rest:
            i = rest.index("--approval")
            if i + 1 < len(rest):
                approval = rest[i + 1]
        if "--write" in rest:
            write = True
            mode = "write"
        # Forbidden flags
        for bad in (
            "--unsafe", "--skip-approval", "--force-push", "--deploy",
            "--force", "--merge", "--write-anywhere",
        ):
            if bad in rest:
                _emit({"error": f"forbidden_flag:{bad}"})
                return EXIT_BAD
        r = _orch().launch(
            item,
            adapter_name=adapter,
            write_enabled=write,
            mode=mode,
            approval_id=approval,
        )
        out = r.to_dict()
        out["safety_display"] = {
            "writes": "DISABLED" if not write else "REQUESTED",
            "commits": "DISABLED",
            "pushes": "DISABLED",
            "mode": mode,
        }
        _emit(out)
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

    if cmd in ("control-center", "control_center"):
        from saathi.engineering.control_center_facet import engineering_control_center_status
        _emit(engineering_control_center_status())
        return EXIT_OK

    if cmd == "approve-readonly":
        # usage: approve-readonly <item_id> [--adapter claude_code]
        if not rest:
            _emit({"error": "item_id_required"})
            return EXIT_BAD
        item_id = rest[0]
        adapter = "claude_code"
        if "--adapter" in rest:
            i = rest.index("--adapter")
            if i + 1 < len(rest):
                adapter = rest[i + 1]
        o = _orch()
        item = o.store.get_item(item_id)
        if not item:
            _emit({"error": "item_not_found"})
            return EXIT_BAD
        ready = o.readiness()
        plan = o.plan(item_id)
        p = plan.get("prompt") or {}
        # Approval binds the same body prefix used at launch for readonly mode
        raw_body = p.get("body") if isinstance(p, dict) else str(p)
        raw_body = raw_body or item.title
        prompt_body = (
            "MODE: READ-ONLY SUPERVISED SESSION.\n"
            "You may inspect and plan only. Do NOT create, modify, delete, "
            "rename, stage, commit, push, merge, rebase, checkout, install "
            "packages, deploy, or trade.\n\n"
            + str(raw_body)
        )
        from saathi.engineering.approval import create_readonly_approval
        from saathi.config import ROOT
        appr = create_readonly_approval(
            o.store,
            repository=str(Path(ROOT).resolve()),
            branch=str(ready.get("branch") or ""),
            starting_commit=str(ready.get("head") or ""),
            backlog_item_id=item_id,
            provider=adapter,
            prompt=prompt_body,
            validation_plan=list(item.required_validations or []),
        )
        _emit({
            "approval_id": appr.approval_id,
            "mode": "readonly",
            "expires_at": appr.expires_at,
            "prompt_fingerprint": appr.prompt_fingerprint,
            "writes": "DISABLED",
            "commits": "DISABLED",
            "pushes": "DISABLED",
        })
        return EXIT_OK

    if cmd == "integrity":
        from saathi.engineering.integrity import capture_snapshot, verify_unchanged, RepoSnapshot
        from saathi.config import ROOT
        snap = capture_snapshot(ROOT)
        if rest and rest[0] == "verify" and len(rest) > 1:
            # verify against JSON path
            base = json.loads(Path(rest[1]).read_text(encoding="utf-8"))
            diff = verify_unchanged(ROOT, RepoSnapshot.from_dict(base))
            _emit(diff.to_dict())
            return EXIT_OK if diff.ok else EXIT_FAIL
        _emit(snap.to_dict())
        return EXIT_OK

    if cmd == "ledger":
        o = _orch()
        led = o.store.ledger()
        if rest:
            _emit({
                "session_id": rest[0],
                "timeline": led.session_timeline(rest[0]),
                "chain": led.verify_chain(),
            })
        else:
            _emit(led.census())
        return EXIT_OK

    if cmd == "recover":
        from saathi.engineering.recovery import recover_store
        dry = "--dry-run" in rest
        o = _orch()
        _emit(recover_store(o.store, apply=not dry))
        return EXIT_OK

    if cmd == "evidence" and rest:
        from saathi.engineering.evidence import IntegrityEvidenceStore
        o = _orch()
        store = IntegrityEvidenceStore(o.store.root, o.store.ledger())
        items = [e.to_dict() for e in store.list_for_session(rest[0])]
        _emit({"session_id": rest[0], "evidence": items})
        return EXIT_OK

    if cmd == "resume-plan" and rest:
        from saathi.engineering.recovery import SessionRecovery
        o = _orch()
        _emit(SessionRecovery(o.store).resume_plan(rest[0]))
        return EXIT_OK

    if cmd == "m20":
        from saathi.m20_console.status import m20_console_status
        _emit(m20_console_status())
        return EXIT_OK

    _emit({"error": "unknown_or_bad_command", "cmd": cmd, "hint": "help"})
    return EXIT_BAD


if __name__ == "__main__":
    raise SystemExit(main())
