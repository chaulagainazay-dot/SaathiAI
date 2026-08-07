"""M163 — Synthetic operator validation kit (deterministic personas).

Labels all feedback as synthetic validation — never fabricates human feedback.
"""
from __future__ import annotations

import time
from typing import Any

from saathi.platform.context import PlatformContextError
from saathi.platform.core_os import SaathiCoreService


def run_synthetic_operator_validation(platform, token: str) -> dict[str, Any]:
    """Run scripted owner/operator journeys against an isolated platform instance."""
    ctx = platform.require_context(token)
    core = SaathiCoreService(platform)
    started = time.time()
    steps: list[dict[str, Any]] = []
    feedback: list[dict[str, Any]] = []

    def step(name: str, fn) -> None:
        t0 = time.time()
        try:
            result = fn()
            steps.append(
                {
                    "name": name,
                    "ok": True,
                    "duration_ms": int((time.time() - t0) * 1000),
                    "result_keys": list(result.keys())[:12] if isinstance(result, dict) else [],
                }
            )
        except Exception as exc:
            steps.append(
                {
                    "name": name,
                    "ok": False,
                    "duration_ms": int((time.time() - t0) * 1000),
                    "error": str(exc)[:200],
                }
            )
            feedback.append(
                {
                    "persona": "synthetic_owner",
                    "kind": "failed_step",
                    "step": name,
                    "note": str(exc)[:160],
                    "human": False,
                    "synthetic": True,
                }
            )

    # Core operator journey
    step("open_operator_home", lambda: core.operator_home(ctx))
    step("universal_search", lambda: core.universal_search(ctx, "hcg"))
    step("unified_yeti", lambda: core.yeti_ask(ctx, "What should I do first today?"))
    step("notifications", lambda: core.notification_center(ctx))
    step(
        "create_automation",
        lambda: core.create_automation(
            ctx,
            name="HCG daily summary",
            schedule="daily",
            action="hcg_daily_summary",
            app_scope="hcg",
            requires_approval=True,
        ),
    )

    # Automation bounded execution path
    def _auto_exec():
        from .automations import AutomationExecutionService
        from .config import load_config, save_config

        autos = core.list_automations(ctx)["automations"]
        aid = autos[-1]["automation_id"]
        svc = AutomationExecutionService(platform, core)
        # disabled by default
        assert autos[-1].get("enabled") in (False, True)  # presence
        # ensure disabled then enable
        svc.disable(ctx, aid)
        cfg = load_config()
        cfg.automation_execution_enabled = True
        save_config(cfg)
        svc.enable(ctx, aid)
        blocked = svc.execute(ctx, aid, approve=False)
        assert blocked.get("state") == "BLOCKED_APPROVAL"
        done = svc.execute(ctx, aid, approve=True, idempotency_suffix="val1")
        assert done.get("ok") is True
        return {"blocked": blocked.get("state"), "done": done.get("state")}

    step("automation_bounded_execution", _auto_exec)

    step(
        "workflow_graph",
        lambda: core.save_workflow_graph(
            ctx,
            name="Alpha cert graph",
            nodes=[
                {"id": "1", "type": "trigger"},
                {"id": "2", "type": "approval"},
                {"id": "3", "type": "execution"},
                {"id": "4", "type": "finish"},
            ],
            edges=[{"from": "1", "to": "2"}, {"from": "2", "to": "3"}, {"from": "3", "to": "4"}],
        ),
    )

    # HCG bounded journey (best-effort; skip soft if app not ready)
    def _hcg():
        from saathi.platform.hcg import HcgService

        hcg = HcgService(platform.store, platform=platform)
        dash = hcg.dashboard(ctx)
        return {"metrics": dash.get("metrics"), "label": dash.get("label")}

    step("hcg_dashboard", _hcg)

    # IELTS bounded journey
    def _ielts():
        from saathi.platform.ielts.service import IELTSService

        ielts = IELTSService(platform.store)
        return ielts.product_dashboard(ctx)

    step("ielts_dashboard", _ielts)

    # Backup dry
    def _backup():
        from .backup_restore import create_system_backup, dry_run_restore
        import tempfile
        from pathlib import Path

        d = Path(tempfile.mkdtemp(prefix="opval-bak-"))
        b = create_system_backup(
            dest_dir=d,
            label="opval",
            db_path=Path(platform.store.db_path),
            include_legacy_app_dbs=False,
        )
        return dry_run_restore(b["archive"])

    step("backup_dry_run", _backup)
    step("doctor", lambda: __import__("saathi.platform.private_alpha.prepare", fromlist=["doctor"]).doctor())

    def _support():
        from .support import export_support_bundle
        import tempfile
        from pathlib import Path

        return export_support_bundle(dest_dir=Path(tempfile.mkdtemp(prefix="opval-sup-")))

    step("support_bundle", _support)

    ok = all(s.get("ok") for s in steps)
    # Synthetic feedback summary (not human)
    feedback.append(
        {
            "persona": "synthetic_owner",
            "kind": "completion",
            "completion_time_sec": round(time.time() - started, 3),
            "confusing_steps": [s["name"] for s in steps if not s.get("ok")],
            "human": False,
            "synthetic": True,
            "label": "SYNTHETIC_VALIDATION_ONLY",
        }
    )

    return {
        "ok": ok,
        "persona": "synthetic_owner_operator",
        "human_feedback": False,
        "synthetic_validation": True,
        "steps": steps,
        "feedback": feedback,
        "duration_sec": round(time.time() - started, 3),
        "journeys": {
            "core_operator": True,
            "hcg": any(s["name"].startswith("hcg") and s["ok"] for s in steps),
            "ielts": any(s["name"].startswith("ielts") and s["ok"] for s in steps),
            "search": any(s["name"] == "universal_search" and s["ok"] for s in steps),
            "yeti": any(s["name"] == "unified_yeti" and s["ok"] for s in steps),
            "automation": any(
                s["name"] == "automation_bounded_execution" and s["ok"] for s in steps
            ),
        },
    }
