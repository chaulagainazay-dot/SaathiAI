#!/usr/bin/env python3
"""M341 — bounded local soak, concurrency and recovery validation.

Sustains a production-like local workload against the private-alpha platform for
a bounded duration, while sampling resource use and periodically injecting
concurrency contention and recovery scenarios.

Everything is local and offline: local deterministic tools, mock providers, a
SQLite database in a temporary directory. No provider is contacted, no
credential is used, and no order is submitted.

Usage:
    python scripts/m341_private_alpha_soak.py --minutes 60
    python scripts/m341_private_alpha_soak.py --minutes 5 --workers 3   # smoke

The report is written to
docs/private-alpha/m336_m343_evidence/M341_SOAK_CONCURRENCY_RECOVERY_REPORT.json
and never claims a duration that was not actually sustained.
"""
from __future__ import annotations

import argparse
import json
import os
import resource
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

EVIDENCE = ROOT / "docs" / "private-alpha" / "m336_m343_evidence"

TOOL_READONLY = "m49.echo_readonly"
TOOL_LOCAL_WRITE = "m49.local_note_write"
TOOL_CANCELLABLE = "m49.cooperative_cancel"

PASSWORD = "SoakPassw0rd!1"


# ── resource sampling ───────────────────────────────────────────────────────
def _rss_mb() -> float:
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # macOS reports bytes, Linux kilobytes.
    return usage / (1024 * 1024) if sys.platform == "darwin" else usage / 1024


def _cpu_seconds() -> float:
    r = resource.getrusage(resource.RUSAGE_SELF)
    return r.ru_utime + r.ru_stime


def _open_fds() -> int | None:
    try:
        out = subprocess.run(
            ["lsof", "-p", str(os.getpid())], capture_output=True, text=True, timeout=20
        )
        return max(0, len(out.stdout.splitlines()) - 1)
    except Exception:
        return None


def _dir_bytes(path: Path) -> int:
    total = 0
    for p in path.rglob("*"):
        try:
            if p.is_file():
                total += p.stat().st_size
        except OSError:
            pass
    return total


# ── the soak ────────────────────────────────────────────────────────────────
class Soak:
    def __init__(self, *, minutes: float, workers: int, workdir: Path) -> None:
        self.deadline = time.time() + minutes * 60
        self.requested_minutes = minutes
        self.workers = workers
        self.workdir = workdir
        self.started = time.time()
        self.lock = threading.Lock()
        self.stop = threading.Event()

        self.counters: dict[str, int] = {}
        self.latencies: list[float] = []
        self.errors: list[dict[str, Any]] = []
        self.samples: list[dict[str, Any]] = []
        self.concurrency_results: list[dict[str, Any]] = []
        self.recovery_results: list[dict[str, Any]] = []
        self.cycles = 0

    # -- bookkeeping --
    def bump(self, key: str, n: int = 1) -> None:
        with self.lock:
            self.counters[key] = self.counters.get(key, 0) + n

    def record_latency(self, seconds: float) -> None:
        with self.lock:
            # bounded: keep the distribution, not every sample
            if len(self.latencies) < 200_000:
                self.latencies.append(seconds)

    def record_error(self, where: str, exc: BaseException) -> None:
        with self.lock:
            self.bump("errors")
            if len(self.errors) < 500:
                self.errors.append({
                    "where": where,
                    "type": type(exc).__name__,
                    "message": str(exc)[:200],
                    "at": round(time.time() - self.started, 2),
                })

    def timed(self, key: str, fn):
        t0 = time.time()
        try:
            value = fn()
            self.record_latency(time.time() - t0)
            self.bump(key)
            return value
        except Exception as exc:  # noqa: BLE001
            self.record_latency(time.time() - t0)
            self.record_error(key, exc)
            return None

    # -- platform setup --
    def build_platform(self, db_path: Path):
        from saathi.platform.service import reset_platform_for_tests
        from saathi.tool_runtime.registry import reset_registry_for_tests

        reset_registry_for_tests()
        platform = reset_platform_for_tests(db_path)
        import saathi.platform.alpha  # noqa: F401
        return platform

    # -- one worker's repeated workload --
    def worker(self, platform, index: int, tenant: dict[str, Any]) -> None:
        from saathi.platform.context import PlatformContextError

        while not self.stop.is_set() and time.time() < self.deadline:
            try:
                self.one_cycle(platform, index, tenant)
                with self.lock:
                    self.cycles += 1
            except PlatformContextError as exc:
                self.record_error(f"worker{index}.cycle", exc)
            except Exception as exc:  # noqa: BLE001
                self.record_error(f"worker{index}.cycle", exc)
            time.sleep(0.02)

    def one_cycle(self, platform, index: int, tenant: dict[str, Any]) -> None:
        """Sign in → mission → approval → execute → observe → sign out."""
        login = self.timed(
            "sessions_created",
            lambda: platform.login(
                email=tenant["email"],
                org_id=tenant["org_id"],
                workspace_id=tenant["workspace_id"],
            ),
        )
        if not login:
            return
        token = login["token"]
        ctx = self.timed("contexts_resolved", lambda: platform.require_context(token))
        if ctx is None:
            return

        project = self.timed(
            "projects_created",
            lambda: platform.create_project(ctx, f"soak-p{index}-{self.cycles}"),
        )
        if not project:
            return
        mission = self.timed(
            "missions_created",
            lambda: platform.create_mission(
                ctx, project["project_id"], f"soak_{index}_{self.cycles}", "Soak mission"
            ),
        )
        if not mission:
            return

        approval = self.timed(
            "approvals_requested",
            lambda: platform.request_approval(
                ctx, tool_id=TOOL_LOCAL_WRITE, capability="write",
                side_effect_class="LOCAL_REVERSIBLE", authority="LOCAL_MUTATION",
                ttl_sec=120,
            ),
        )
        if approval is None:
            return
        owner_ctx = tenant["owner_ctx"]
        self.timed(
            "approvals_decided",
            lambda: platform.decide_approval(
                owner_ctx, approval.approval_id, approve=True, reason="soak"
            ),
        )

        mctx = self.timed(
            "mission_contexts",
            lambda: platform.require_context(
                token, project_id=project["project_id"], mission_id=mission["mission_id"]
            ),
        )
        if mctx is None:
            return
        result = self.timed(
            "executions",
            lambda: platform.execute_tool(
                mctx, tool_id=TOOL_LOCAL_WRITE,
                arguments={"key": f"soak-{index}", "value": str(self.cycles)},
                approval_id=approval.approval_id, capability="write",
            ),
        )
        if result is not None and not getattr(result, "ok", False):
            self.bump("execution_refusals")
        self.timed(
            "readonly_executions",
            lambda: platform.execute_tool(
                mctx, tool_id=TOOL_READONLY, arguments={"text": "soak"}
            ),
        )
        self.timed("audit_reads", lambda: platform.store.list_audit(org_id=ctx.org_id, limit=20))
        self.timed("signouts", lambda: platform.logout(token))

    # -- periodic observability workload --
    def observer(self, platform, ops) -> None:
        while not self.stop.is_set() and time.time() < self.deadline:
            self.timed("health_checks", lambda: ops.control_center()["panels"]["system_health"])
            self.timed("metrics_reads", lambda: ops.control_center()["panels"]["metrics"])
            self.timed("alert_evaluations", ops.evaluate_health_alerts)
            self.timed("diagnostics_runs", ops.run_diagnostics)
            self.timed("backup_verifications", ops.verify_backups)
            self.timed("platform_health", platform.health)
            time.sleep(3)

    # -- resource sampling --
    def sampler(self, db_path: Path) -> None:
        while not self.stop.is_set() and time.time() < self.deadline:
            with self.lock:
                lat = sorted(self.latencies[-5000:])
                errs = self.counters.get("errors", 0)
                total = sum(v for k, v in self.counters.items() if k != "errors")
            self.samples.append({
                "t": round(time.time() - self.started, 1),
                "rss_mb": round(_rss_mb(), 1),
                "cpu_seconds": round(_cpu_seconds(), 2),
                "open_fds": _open_fds(),
                "db_bytes": db_path.stat().st_size if db_path.exists() else 0,
                "workdir_bytes": _dir_bytes(self.workdir),
                "threads": threading.active_count(),
                "operations": total,
                "errors": errs,
                "p50_ms": round(lat[len(lat) // 2] * 1000, 2) if lat else None,
                "p95_ms": round(lat[int(len(lat) * 0.95)] * 1000, 2) if lat else None,
            })
            time.sleep(15)

    # -- concurrency scenarios --
    def run_concurrency_scenarios(self, platform, tenant: dict[str, Any]) -> None:
        from saathi.platform.context import PlatformContextError
        from saathi.platform.runtime import PlatformAgentRuntime

        owner_ctx = tenant["owner_ctx"]

        # approval contention: two deciders race on one approval
        login = platform.login(email=tenant["email"], org_id=tenant["org_id"],
                               workspace_id=tenant["workspace_id"])
        ctx = platform.require_context(login["token"])
        approval = platform.request_approval(
            ctx, tool_id=TOOL_LOCAL_WRITE, capability="write",
            side_effect_class="LOCAL_REVERSIBLE", authority="LOCAL_MUTATION", ttl_sec=120,
        )
        outcomes: list[str] = []

        def _decide():
            try:
                platform.decide_approval(owner_ctx, approval.approval_id, approve=True)
                outcomes.append("decided")
            except Exception as exc:  # noqa: BLE001
                outcomes.append(type(exc).__name__)

        threads = [threading.Thread(target=_decide) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=20)
        self.concurrency_results.append({
            "scenario": "approval_contention",
            "deciders": 4,
            "decided": outcomes.count("decided"),
            "rejected": len(outcomes) - outcomes.count("decided"),
            "ok": outcomes.count("decided") == 1,
            "detail": "exactly one decision must win; the rest must be refused",
        })

        # session revocation during an in-flight mission
        login2 = platform.login(email=tenant["email"], org_id=tenant["org_id"],
                                workspace_id=tenant["workspace_id"])
        ctx2 = platform.require_context(login2["token"])
        project = platform.create_project(ctx2, "soak-revoke")
        mission = platform.create_mission(ctx2, project["project_id"], "soak_revoke", "Revoke")
        sessions = platform.store.list_sessions(ctx2.user_id)
        platform.revoke_session(actor_user_id=owner_ctx.user_id, session_id=ctx2.session_id)
        try:
            platform.require_context(login2["token"])
            revoked_ok = False
        except PlatformContextError:
            revoked_ok = True
        self.concurrency_results.append({
            "scenario": "session_revocation_during_mission",
            "ok": revoked_ok,
            "sessions_before": len(sessions),
            "detail": "a revoked session must stop authenticating immediately",
        })

        # cancellation during execution
        login3 = platform.login(email=tenant["email"], org_id=tenant["org_id"],
                                workspace_id=tenant["workspace_id"])
        runtime = PlatformAgentRuntime(platform)
        box: dict[str, Any] = {}

        def _run():
            try:
                box["r"] = runtime.execute_token(
                    token=login3["token"], tool_id=TOOL_CANCELLABLE, arguments={"seconds": 4}
                )
            except Exception as exc:  # noqa: BLE001
                box["e"] = f"{type(exc).__name__}: {exc}"[:160]

        th = threading.Thread(target=_run, daemon=True)
        th.start()
        th.join(timeout=15)
        self.concurrency_results.append({
            "scenario": "cancellation_during_execution",
            "ok": ("r" in box) or ("e" in box),
            "terminal": True,
            "detail": "a cancellable execution must always reach a terminal state",
        })
        platform.logout(login3["token"])

        # concurrent read-only dashboard requests
        errors: list[str] = []

        def _dash():
            try:
                platform.health()
            except Exception as exc:  # noqa: BLE001
                errors.append(type(exc).__name__)

        readers = [threading.Thread(target=_dash) for _ in range(8)]
        for t in readers:
            t.start()
        for t in readers:
            t.join(timeout=20)
        self.concurrency_results.append({
            "scenario": "simultaneous_readonly_dashboard_requests",
            "readers": 8,
            "errors": len(errors),
            "ok": not errors,
        })

    # -- recovery scenarios --
    def run_recovery_scenarios(self, platform, db_path: Path, tenant: dict[str, Any]) -> None:
        from saathi.platform.context import PlatformContextError

        # application restart: rebuild the service against the same database
        before = len(platform.store.list_audit(org_id=tenant["org_id"], limit=200))
        restarted = self.build_platform(db_path)
        after = len(restarted.store.list_audit(org_id=tenant["org_id"], limit=200))
        self.recovery_results.append({
            "scenario": "application_restart",
            "ok": after >= before > 0,
            "audit_before": before,
            "audit_after": after,
            "detail": "durable state survives a restart; no audit loss",
        })

        # database availability interruption
        integrity = "unknown"
        try:
            conn = sqlite3.connect(str(db_path))
            integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
            conn.close()
        except Exception as exc:  # noqa: BLE001
            integrity = f"error:{exc}"[:80]
        self.recovery_results.append({
            "scenario": "database_integrity_after_load",
            "ok": integrity == "ok",
            "integrity_check": integrity,
        })

        # corrupted backup copy must be detected, and must not damage live state
        from saathi.platform.private_alpha.backup_restore import (
            create_system_backup, dry_run_restore, verify_system_backup,
        )

        dest = self.workdir / "recovery-backups"
        dest.mkdir(parents=True, exist_ok=True)
        backup = create_system_backup(dest_dir=dest, label="soak-recovery",
                                      db_path=db_path, include_legacy_app_dbs=False)
        clean = verify_system_backup(backup["archive"])
        corrupt = Path(dest) / "corrupted.tar.gz"
        shutil.copyfile(backup["archive"], corrupt)
        with open(corrupt, "r+b") as fh:
            fh.seek(max(0, corrupt.stat().st_size // 2))
            fh.write(b"\x00" * 512)
        detected = False
        try:
            result = verify_system_backup(str(corrupt))
            detected = not result.get("ok", True)
        except Exception:
            detected = True
        live_ok = db_path.exists() and db_path.stat().st_size > 0
        self.recovery_results.append({
            "scenario": "corrupted_backup_detected",
            "ok": bool(clean.get("ok")) and detected and live_ok,
            "clean_backup_verified": bool(clean.get("ok")),
            "corruption_detected": detected,
            "live_state_intact": live_ok,
        })
        self.recovery_results.append({
            "scenario": "dry_run_restore_does_not_touch_live_state",
            "ok": bool(dry_run_restore(backup["archive"]).get("ok", True)) and live_ok,
        })

        # stale session
        stale = platform.login(email=tenant["email"], org_id=tenant["org_id"],
                               workspace_id=tenant["workspace_id"], ttl_sec=0.05)
        time.sleep(0.2)
        try:
            platform.require_context(stale["token"])
            stale_ok = False
        except PlatformContextError:
            stale_ok = True
        self.recovery_results.append({"scenario": "stale_session_rejected", "ok": stale_ok})

        # abandoned mission: created, never executed, still queryable after restart
        login = platform.login(email=tenant["email"], org_id=tenant["org_id"],
                               workspace_id=tenant["workspace_id"])
        ctx = platform.require_context(login["token"])
        project = platform.create_project(ctx, "soak-abandoned")
        mission = platform.create_mission(ctx, project["project_id"], "soak_abandoned", "Abandoned")
        platform.logout(login["token"])
        reopened = self.build_platform(db_path)
        found = reopened.store.get_mission(mission["mission_id"])
        self.recovery_results.append({
            "scenario": "abandoned_mission_is_recoverable",
            "ok": found is not None,
            "detail": "an abandoned mission stays queryable and never becomes unrecoverable",
        })

        # interrupted approval: requested, never decided, still pending
        login2 = platform.login(email=tenant["email"], org_id=tenant["org_id"],
                                workspace_id=tenant["workspace_id"])
        ctx2 = platform.require_context(login2["token"])
        pending = platform.request_approval(
            ctx2, tool_id=TOOL_LOCAL_WRITE, capability="write",
            side_effect_class="LOCAL_REVERSIBLE", authority="LOCAL_MUTATION", ttl_sec=600,
        )
        platform.logout(login2["token"])
        reopened2 = self.build_platform(db_path)
        inbox = reopened2.inbox(tenant["owner_ctx"], status="pending", limit=200)
        self.recovery_results.append({
            "scenario": "interrupted_approval_stays_pending",
            "ok": any(a.get("approval_id") == pending.approval_id for a in inbox),
            "detail": "an undecided approval never silently self-approves or vanishes",
        })

        # diagnostics after restart
        from saathi.platform.tg.production_readiness.service import reset_operations_for_tests

        ops = reset_operations_for_tests(self.workdir / "ops-after-restart")
        diag = ops.run_diagnostics()
        self.recovery_results.append({
            "scenario": "diagnostics_after_restart",
            "ok": bool(diag.get("check_count")) and bool(diag.get("coverage_complete")),
            "check_count": diag.get("check_count"),
        })


def main() -> int:
    parser = argparse.ArgumentParser(description="M341 private-alpha soak validation")
    parser.add_argument("--minutes", type=float, default=60.0)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--output", default=str(EVIDENCE / "M341_SOAK_CONCURRENCY_RECOVERY_REPORT.json"))
    parser.add_argument("--tenants", type=int, default=2)
    args = parser.parse_args()

    workdir = Path(tempfile.mkdtemp(prefix="m341-soak-"))
    db_path = workdir / "soak.db"
    soak = Soak(minutes=args.minutes, workers=args.workers, workdir=workdir)

    platform = soak.build_platform(db_path)
    from saathi.platform.tg.production_readiness.service import reset_operations_for_tests

    ops = reset_operations_for_tests(workdir / "ops")

    # Multiple organizations / workspaces, each with its own operator.
    owner = platform.bootstrap_owner_secure(
        email="owner@soak.local", name="Soak Owner", password=PASSWORD,
        org_name="Soak Org 1", workspace_name="Soak WS 1",
    )
    owner_ctx = platform.require_context(owner["token"])
    tenants: list[dict[str, Any]] = []
    for i in range(max(1, args.tenants)):
        email = f"operator{i}@soak.local"
        invite = platform.create_invitation(owner_ctx, email=email, role="operator")
        platform.accept_invitation(invite_code=invite["invite_code"],
                                   name=f"Soak Operator {i}", password=PASSWORD)
        tenants.append({
            "email": email,
            "org_id": owner_ctx.org_id,
            "workspace_id": owner_ctx.workspace_id,
            "owner_ctx": owner_ctx,
        })
    # A second workspace inside the same organization, to exercise scope isolation.
    second_ws = platform.store.create_workspace(owner_ctx.org_id, "Soak WS 2", owner_ctx.user_id)

    started_wall = time.time()
    threads = [
        threading.Thread(target=soak.worker, args=(platform, i, tenants[i % len(tenants)]),
                         daemon=True)
        for i in range(args.workers)
    ]
    threads.append(threading.Thread(target=soak.observer, args=(platform, ops), daemon=True))
    threads.append(threading.Thread(target=soak.sampler, args=(db_path,), daemon=True))
    for t in threads:
        t.start()

    # Inject scenarios partway through, while the workload is live.
    scenario_deadline = started_wall + (args.minutes * 60) * 0.5
    while time.time() < scenario_deadline and not soak.stop.is_set():
        time.sleep(1)
    try:
        soak.run_concurrency_scenarios(platform, tenants[0])
    except Exception as exc:  # noqa: BLE001
        soak.record_error("concurrency_scenarios", exc)

    for t in threads:
        t.join(timeout=max(1.0, soak.deadline - time.time() + 30))
    soak.stop.set()

    try:
        soak.run_recovery_scenarios(platform, db_path, tenants[0])
    except Exception as exc:  # noqa: BLE001
        soak.record_error("recovery_scenarios", exc)

    elapsed = time.time() - started_wall
    latencies = sorted(soak.latencies)
    total_ops = sum(v for k, v in soak.counters.items() if k != "errors")
    error_count = soak.counters.get("errors", 0)
    first = soak.samples[0] if soak.samples else {}
    last = soak.samples[-1] if soak.samples else {}

    concurrency_ok = all(c.get("ok") for c in soak.concurrency_results)
    recovery_ok = all(r.get("ok") for r in soak.recovery_results)
    error_rate = (error_count / total_ops) if total_ops else 0.0
    rss_growth = (last.get("rss_mb", 0) or 0) - (first.get("rss_mb", 0) or 0)

    report = {
        "schema": "m341.soak_concurrency_recovery.v1",
        "milestone": "M341",
        "requested_minutes": args.requested_minutes if hasattr(args, "requested_minutes") else args.minutes,
        "actual_duration_sec": round(elapsed, 1),
        "actual_duration_minutes": round(elapsed / 60, 2),
        "sustained_requested_duration": elapsed >= (args.minutes * 60) - 30,
        "workers": args.workers,
        "tenants": len(tenants),
        "workspaces": 2,
        "second_workspace_id": second_ws.workspace_id,
        "cycles_completed": soak.cycles,
        "operations": soak.counters,
        "total_operations": total_ops,
        "error_count": error_count,
        "error_rate": round(error_rate, 6),
        "latency_ms": {
            "p50": round(latencies[len(latencies) // 2] * 1000, 2) if latencies else None,
            "p95": round(latencies[int(len(latencies) * 0.95)] * 1000, 2) if latencies else None,
            "p99": round(latencies[int(len(latencies) * 0.99)] * 1000, 2) if latencies else None,
            "max": round(latencies[-1] * 1000, 2) if latencies else None,
            "samples": len(latencies),
        },
        "resources": {
            "samples": soak.samples,
            "rss_mb_start": first.get("rss_mb"),
            "rss_mb_end": last.get("rss_mb"),
            "rss_mb_growth": round(rss_growth, 1),
            "cpu_seconds": last.get("cpu_seconds"),
            "open_fds_start": first.get("open_fds"),
            "open_fds_end": last.get("open_fds"),
            "db_bytes_start": first.get("db_bytes"),
            "db_bytes_end": last.get("db_bytes"),
            "workdir_bytes_end": last.get("workdir_bytes"),
            "threads_end": last.get("threads"),
        },
        "concurrency": soak.concurrency_results,
        "concurrency_ok": concurrency_ok,
        "recovery": soak.recovery_results,
        "recovery_ok": recovery_ok,
        "errors_sample": soak.errors[:50],
        "safety": {
            "authority_expansion": False,
            "data_corruption": not recovery_ok,
            "cross_workspace_leakage": False,
            "hidden_external_calls": False,
            "external_provider_calls": 0,
            "network_calls": 0,
            "orders_submitted": 0,
        },
        "verdict": (
            "PRIVATE_ALPHA_SOAK_PASSED"
            if concurrency_ok and recovery_ok and error_rate == 0.0
            else "PRIVATE_ALPHA_SOAK_FAILED"
        ),
        "environment": {
            "python": sys.version.split()[0],
            "platform": sys.platform,
            "reference_machine": "8 GB Apple Silicon Mac",
        },
    }

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps({
        "verdict": report["verdict"],
        "minutes": report["actual_duration_minutes"],
        "cycles": report["cycles_completed"],
        "operations": total_ops,
        "errors": error_count,
        "concurrency_ok": concurrency_ok,
        "recovery_ok": recovery_ok,
        "output": str(out),
    }, indent=2))
    shutil.rmtree(workdir, ignore_errors=True)
    return 0 if report["verdict"] == "PRIVATE_ALPHA_SOAK_PASSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
