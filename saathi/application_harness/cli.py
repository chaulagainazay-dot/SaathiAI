"""M17.3 application-harness CLI (read-only inspection + safe live pilot).

    python -m saathi.application_harness.cli list
    python -m saathi.application_harness.cli inspect <harness_id>
    python -m saathi.application_harness.cli operations <harness_id>
    python -m saathi.application_harness.cli resolve <application> <operation>
    python -m saathi.application_harness.cli import-cli-anything <registry.json>
    python -m saathi.application_harness.cli health
    python -m saathi.application_harness.cli live-report

M17.9 durable run-ledger operations — LOCAL ADMIN-MAINTENANCE surface.

    python -m saathi.application_harness.cli ledger-health           (always: aggregate)
  # the rest require SAATHI_HARNESS_ADMIN=1 (trusted local operator):
    python -m saathi.application_harness.cli runs
    python -m saathi.application_harness.cli run-inspect <run_id>
    python -m saathi.application_harness.cli run-cancel <run_id>
    python -m saathi.application_harness.cli run-reconcile <run_id>
    python -m saathi.application_harness.cli runs-reconcile-stale
    python -m saathi.application_harness.cli run-transitions <run_id>
    python -m saathi.application_harness.cli runs-monitor          (M17.10 sweep)
    python -m saathi.application_harness.cli run-alerts            (M17.10 open alerts)
    python -m saathi.application_harness.cli alert-ack <alert_id>  (M17.10 acknowledge)
    python -m saathi.application_harness.cli notify-dispatch       (M17.11 enqueue+dispatch)
    python -m saathi.application_harness.cli alert-deliveries      (M17.11 open deliveries)
    python -m saathi.application_harness.cli retry-delivery <id>   (M17.11 admin retry)
    python -m saathi.application_harness.cli monitor-schedule-status (M17.11 scheduler)
    python -m saathi.application_harness.cli pipeline-health        (M17.12 census: always)
    python -m saathi.application_harness.cli mission-health         (M17.13 census: always)
  # admin-gated (SAATHI_HARNESS_ADMIN=1):
    python -m saathi.application_harness.cli pipelines             (M17.12 recent pipelines)
    python -m saathi.application_harness.cli pipeline-inspect <id> (M17.12 steps, owner-safe)
    python -m saathi.application_harness.cli missions             (M17.13 recent missions)
    python -m saathi.application_harness.cli mission-inspect <id> (M17.13 mission + runs)
    python -m saathi.application_harness.cli mission-history <id> (M17.13 run history)
    python -m saathi.application_harness.cli mission-run <id>     (M17.13 execute, fail-closed)
    python -m saathi.application_harness.cli mission-retry <id>   (M17.13 clone a failed mission)
    python -m saathi.application_harness.cli scheduler-health      (M17.14 census: always)
  # M17.14 scheduler admin-gated (SAATHI_HARNESS_ADMIN=1), owner-safe:
    python -m saathi.application_harness.cli schedules
    python -m saathi.application_harness.cli schedule-inspect <id>
    python -m saathi.application_harness.cli schedule-create <owner> <template> <type> <expr_json> [params_json]
    python -m saathi.application_harness.cli schedule-pause|schedule-resume|schedule-disable <id>
    python -m saathi.application_harness.cli occurrences
    python -m saathi.application_harness.cli occurrence-inspect <id>
    python -m saathi.application_harness.cli occurrence-reconcile
    python -m saathi.application_harness.cli triggers
    python -m saathi.application_harness.cli trigger-inspect <id>

Security model: this CLI has NO authenticated user context, so it never trusts a
caller-supplied identity for authorization. Ledger inspection + mutation are
admin-maintenance-only, gated by the SAATHI_HARNESS_ADMIN=1 operator opt-in; the
acting identity is the *verified local OS user* (never a --requester/--owner
flag), and every mutation is audit-logged through the event bus with that
operator id. End-user, owner-scoped run access is served by the authenticated API
/ Control Center, not here. Reconcile commands only settle dead-PID runs — they
never rerun work or overwrite a live process. Output is owner-safe: no raw argv,
output, secrets, approval material, or private artifact paths.
"""
from __future__ import annotations

import json
import os
import sys

from saathi.application_harness import registry, resolver, importer
from saathi.application_harness.pilots import ffmpeg as F

_LEDGER_CMDS = {"runs", "run-inspect", "run-cancel", "run-reconcile",
                "runs-reconcile-stale", "run-transitions", "ledger-health",
                "runs-monitor", "run-alerts", "alert-ack",
                "notify-dispatch", "alert-deliveries", "retry-delivery",
                "monitor-schedule-status",
                "pipelines", "pipeline-inspect", "pipeline-health",
                "missions", "mission-inspect", "mission-run", "mission-health",
                "mission-history", "mission-retry",
                "scheduler-health", "schedules", "schedule-inspect",
                "schedule-create", "schedule-pause", "schedule-resume",
                "schedule-disable", "occurrences", "occurrence-inspect",
                "occurrence-reconcile", "triggers", "trigger-inspect"}
_ADMIN_MSG = ("ledger maintenance commands require admin mode: set "
              "SAATHI_HARNESS_ADMIN=1 (the verified local OS identity is used "
              "as the audited operator; no caller-supplied identity is trusted)")


def _operator_identity() -> str:
    """Trusted, kernel-provided local identity — NEVER caller-supplied."""
    try:
        import pwd
        return pwd.getpwuid(os.getuid()).pw_name
    except Exception:
        import getpass
        return getpass.getuser()


def _admin_enabled() -> bool:
    return os.environ.get("SAATHI_HARNESS_ADMIN") == "1"


def _safe_row(row: dict | None) -> dict:
    """Project a raw ledger row to owner-safe fields (no approval material,
    idempotency keys, intent digests, or process internals leak out)."""
    from saathi.application_harness.run_ledger import _SAFE_FIELDS
    if not row:
        return {"error": "not found"}
    return {k: row.get(k) for k in _SAFE_FIELDS}


def _ledger_cmd(cmd, rest) -> int | None:
    """Handle M17.9 run-ledger subcommands. Returns an exit code, or None if
    `cmd` is not a ledger command."""
    if cmd not in _LEDGER_CMDS:
        return None
    from saathi.application_harness.run_ledger import default_ledger
    led = default_ledger()
    # aggregate integrity only — no per-user or secret data — always available
    if cmd == "ledger-health":
        h = led.health()
        print(json.dumps(h, indent=2, default=str))
        return 0 if h.get("ok") else 1
    if cmd == "pipeline-health":              # M17.12 aggregate census — no secrets
        print(json.dumps(led.pipeline_health(), indent=2, default=str)); return 0
    if cmd == "mission-health":               # M17.13 aggregate census — no secrets
        print(json.dumps(led.mission_health(), indent=2, default=str)); return 0
    if cmd == "scheduler-health":             # M17.14 aggregate census — no secrets
        print(json.dumps({"schedules": led.schedule_health(),
                          "occurrences": led.occurrence_health()},
                         indent=2, default=str)); return 0
    # everything else is admin-maintenance-only; identity from trusted OS context
    if not _admin_enabled():
        print(_ADMIN_MSG, file=sys.stderr)
        return 3
    operator = _operator_identity()
    if cmd == "runs":
        rm = led.read_model(None)                # operator diagnostic; owner-safe fields
        print(json.dumps(rm, indent=2, default=str)); return 0
    if cmd == "run-inspect":
        if not rest:
            print("run-inspect needs <run_id>", file=sys.stderr); return 2
        r = led.inspect(rest[0])
        print(json.dumps(_safe_row(r), indent=2, default=str))
        return 0 if r else 1
    if cmd == "run-transitions":
        if not rest:
            print("run-transitions needs <run_id>", file=sys.stderr); return 2
        print(json.dumps(led.transitions(rest[0]), indent=2, default=str)); return 0
    if cmd == "run-cancel":
        if not rest:
            print("run-cancel needs <run_id>", file=sys.stderr); return 2
        res = led.admin_cancel(rest[0], operator=operator)   # audited, state-safe
        print(json.dumps(res, indent=2, default=str))
        return 0 if res.get("cancelled") else 1
    if cmd == "run-reconcile":
        if not rest:
            print("run-reconcile needs <run_id>", file=sys.stderr); return 2
        print(json.dumps(led.reconcile_run(rest[0]), indent=2, default=str)); return 0
    if cmd == "runs-reconcile-stale":
        print(json.dumps(led.reconcile_stale(), indent=2, default=str)); return 0
    if cmd == "runs-monitor":                # M17.10 deterministic stuck-run sweep
        from saathi.application_harness.run_monitor import HarnessRunMonitor
        print(json.dumps(HarnessRunMonitor(led).sweep(), indent=2, default=str)); return 0
    if cmd == "run-alerts":
        print(json.dumps(led.open_alerts(), indent=2, default=str)); return 0
    if cmd == "notify-dispatch":             # M17.11 run one enqueue+dispatch pass
        from saathi.application_harness.notify import NotificationDispatcher
        print(json.dumps(NotificationDispatcher(led).run_once(), indent=2, default=str))
        return 0
    if cmd == "alert-deliveries":
        print(json.dumps(led.open_deliveries(), indent=2, default=str)); return 0
    if cmd == "monitor-schedule-status":
        from saathi.application_harness.run_scheduler import default_scheduler
        print(json.dumps(default_scheduler().schedule_status(), indent=2, default=str))
        return 0
    if cmd == "retry-delivery":              # admin-audited terminal-failure retry
        if not rest:
            print("retry-delivery needs <delivery_id>", file=sys.stderr); return 2
        try:
            did = int(rest[0])
        except ValueError:
            print("retry-delivery needs a numeric <delivery_id>", file=sys.stderr); return 2
        res = led.admin_retry_delivery(did, operator=operator)   # audited, OS identity
        print(json.dumps(res, indent=2, default=str))
        return 0 if res.get("ok") else 1
    if cmd == "pipelines":                    # M17.12 operator diagnostic (owner-safe)
        print(json.dumps(led.list_pipelines(None), indent=2, default=str)); return 0
    if cmd == "pipeline-inspect":
        if not rest:
            print("pipeline-inspect needs <pipeline_id>", file=sys.stderr); return 2
        p = led.inspect_pipeline(rest[0])
        print(json.dumps(p or {"error": "not found"}, indent=2, default=str))
        return 0 if p else 1
    if cmd == "missions":                     # M17.13 operator diagnostic (owner-safe)
        print(json.dumps(led.list_missions(None), indent=2, default=str)); return 0
    if cmd == "mission-inspect":
        if not rest:
            print("mission-inspect needs <mission_id>", file=sys.stderr); return 2
        m = led.inspect_mission(rest[0])
        print(json.dumps(m or {"error": "not found"}, indent=2, default=str))
        return 0 if m else 1
    if cmd == "mission-history":
        if not rest:
            print("mission-history needs <mission_id>", file=sys.stderr); return 2
        print(json.dumps(led.mission_history(rest[0]), indent=2, default=str)); return 0
    if cmd == "mission-run":                   # execute an existing mission (fail-closed)
        if not rest:
            print("mission-run needs <mission_id>", file=sys.stderr); return 2
        m = led.inspect_mission(rest[0])
        if not m:
            print(json.dumps({"error": "not found"})); return 1
        from saathi.application_harness.mission import MissionEngine
        eng = MissionEngine(ledger=led)
        # runs under the mission's OWN stored owner; approval-required missions
        # halt at approval_required (never elevated by the operator).
        res = eng.launch(rest[0], owner=m["owner"], session_id=f"cli:{operator}")
        print(json.dumps(res, indent=2, default=str))
        return 0 if res.get("ok") else 1
    if cmd == "mission-retry":                 # clone a FAILED mission to a new instance
        if not rest:
            print("mission-retry needs <mission_id>", file=sys.stderr); return 2
        m = led.inspect_mission(rest[0])
        if not m:
            print(json.dumps({"error": "not found"})); return 1
        from saathi.application_harness.mission import MissionEngine
        res = MissionEngine(ledger=led).retry(rest[0], owner=m["owner"])
        print(json.dumps(res, indent=2, default=str))
        return 0 if res.get("ok") else 1
    if cmd == "schedules":                     # M17.14 operator diagnostic (owner-safe)
        print(json.dumps(led.list_schedules(None), indent=2, default=str)); return 0
    if cmd == "schedule-inspect":
        if not rest:
            print("schedule-inspect needs <schedule_id>", file=sys.stderr); return 2
        s = led.get_schedule(rest[0])
        print(json.dumps(s or {"error": "not found"}, indent=2, default=str))
        return 0 if s else 1
    if cmd == "schedule-create":               # admin-audited; typed template params
        if len(rest) < 4:
            print("schedule-create needs <owner> <template_id> <schedule_type> "
                  "<expr_json> [params_json]", file=sys.stderr); return 2
        try:
            expr = json.loads(rest[3]); params = json.loads(rest[4]) if len(rest) > 4 else {}
        except ValueError as e:
            print(f"bad json: {e}", file=sys.stderr); return 2
        from saathi.application_harness.scheduler import MissionScheduler
        res = MissionScheduler(ledger=led).create_schedule(
            owner=rest[0], mission_template_id=rest[1], schedule_type=rest[2],
            expression=expr, params=params)
        print(json.dumps(res, indent=2, default=str))
        return 0 if res.get("ok") else 1
    if cmd in ("schedule-pause", "schedule-resume", "schedule-disable"):
        if not rest:
            print(f"{cmd} needs <schedule_id>", file=sys.stderr); return 2
        s = led.get_schedule(rest[0])
        if not s:
            print(json.dumps({"error": "not found"})); return 1
        from saathi.application_harness.scheduler import MissionScheduler
        sch = MissionScheduler(ledger=led)
        fn = {"schedule-pause": sch.pause, "schedule-resume": sch.resume,
              "schedule-disable": sch.disable}[cmd]
        res = fn(rest[0], owner=s["owner"])      # audited via ledger event
        print(json.dumps(res, indent=2, default=str))
        return 0 if res.get("ok") else 1
    if cmd == "occurrences":
        print(json.dumps(led.list_occurrences(None), indent=2, default=str)); return 0
    if cmd == "occurrence-inspect":
        if not rest:
            print("occurrence-inspect needs <occurrence_id>", file=sys.stderr); return 2
        o = led.inspect_occurrence(rest[0])
        print(json.dumps(o or {"error": "not found"}, indent=2, default=str))
        return 0 if o else 1
    if cmd == "occurrence-reconcile":          # settle stale-lease occurrences only
        from saathi.application_harness.scheduler import MissionScheduler
        print(json.dumps(MissionScheduler(ledger=led).reconcile(), indent=2, default=str))
        return 0
    if cmd == "triggers":
        print(json.dumps(led.list_triggers(None), indent=2, default=str)); return 0
    if cmd == "trigger-inspect":
        if not rest:
            print("trigger-inspect needs <trigger_id>", file=sys.stderr); return 2
        t = led.get_trigger(rest[0])
        print(json.dumps(t or {"error": "not found"}, indent=2, default=str))
        return 0 if t else 1
    if cmd == "alert-ack":
        if not rest:
            print("alert-ack needs <alert_id>", file=sys.stderr); return 2
        try:
            aid = int(rest[0])
        except ValueError:
            print("alert-ack needs a numeric <alert_id>", file=sys.stderr); return 2
        res = led.acknowledge_alert(aid, operator=operator)   # audited, OS identity
        print(json.dumps(res, indent=2, default=str))
        return 0 if res.get("ok") else 1
    return None


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print("usage: list|inspect|operations|resolve|import-cli-anything|health|live-report"
              "|runs|run-inspect|run-cancel|run-reconcile|runs-reconcile-stale"
              "|run-transitions|ledger-health|runs-monitor|run-alerts|alert-ack"
              "|notify-dispatch|alert-deliveries|retry-delivery|monitor-schedule-status"
              "|pipelines|pipeline-inspect|pipeline-health"
              "|missions|mission-inspect|mission-run|mission-health|mission-history|mission-retry"
              "|scheduler-health|schedules|schedule-inspect|schedule-create|schedule-pause"
              "|schedule-resume|schedule-disable|occurrences|occurrence-inspect"
              "|occurrence-reconcile|triggers|trigger-inspect",
              file=sys.stderr)
        return 2
    cmd, rest = argv[0], argv[1:]
    ledger_rc = _ledger_cmd(cmd, rest)
    if ledger_rc is not None:
        return ledger_rc
    if cmd == "list":
        print(json.dumps(registry.summary(), indent=2)); return 0
    if cmd == "inspect":
        d = registry.get(rest[0]) if rest else None
        print(json.dumps(d.to_dict() if d else {"error": "not found"}, indent=2, default=str))
        return 0 if d else 1
    if cmd == "operations":
        if rest and rest[0] == "ffmpeg":
            print(json.dumps([o.to_dict() for o in F.operations()], indent=2)); return 0
        print("[]"); return 0
    if cmd == "resolve":
        if len(rest) < 2:
            print("resolve needs <application> <operation>", file=sys.stderr); return 2
        h = registry.get(rest[0]) or next((d for d in registry.all_harnesses()
                                           if d.application_name == rest[0]), None)
        r = resolver.resolve(application=rest[0], operation=rest[1], harness=h)
        print(json.dumps(r.to_dict(), indent=2)); return 0
    if cmd == "import-cli-anything":
        if not rest:
            print("needs a registry.json path", file=sys.stderr); return 2
        raw = open(rest[0]).read()
        res = importer.import_registry(raw)
        print(json.dumps({"imported": res["imported"], "rejected": len(res["rejected"]),
                          "trust": res["trust"]}, indent=2)); return 0
    if cmd == "health":
        print(json.dumps({"ffmpeg": F.available(), "registry": registry.summary()},
                         indent=2)); return 0
    if cmd == "live-report":
        from saathi.application_harness.live_report import build_report
        print(json.dumps(build_report(), indent=2, default=str)); return 0
    print(f"unknown command {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
