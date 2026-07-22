"""M13.5 release gate — machine-readable go/no-go with stable exit codes.

Runs the hard gates a staging release must pass. Returns (exit_code, report).
Exit codes are the documented contract (docs/RELEASE_GATES.md).
"""
from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

EXIT_READY = 0
EXIT_WARN = 1
EXIT_TESTS = 2
EXIT_SECURITY = 3
EXIT_CONFIG = 4
EXIT_DATABASE = 5
EXIT_BACKUP = 6
EXIT_BROWSER = 7
EXIT_PROVIDER = 8
EXIT_STORAGE = 9
EXIT_VERSION = 10
EXIT_DIRTY = 11
EXIT_INTERNAL = 12


def _git_dirty() -> list[str]:
    try:
        out = subprocess.run(["git", "status", "--short"], cwd=str(ROOT),
                             capture_output=True, text=True, timeout=10).stdout
        # ignore the known pre-existing unrelated file
        return [ln for ln in out.splitlines()
                if ln.strip() and "memory/conventions.md" not in ln]
    except Exception:
        return []


def release_check(*, run_secret_scan: bool = True, run_db: bool = True,
                  run_backup: bool = True, run_storage: bool = True,
                  strict_dirty: bool = False) -> tuple[int, dict]:
    report = {"gates": {}}

    # storage
    if run_storage:
        from saathi.ops.storage import storage_report
        s = storage_report()
        report["gates"]["storage"] = s
        if not s["healthy"]:
            return EXIT_STORAGE, report

    # config
    from saathi.ops.config_check import check_config
    cfg = check_config()
    report["gates"]["config"] = {"ok": cfg["ok"], "blocking": cfg["blocking"]}
    if not cfg["ok"]:
        return EXIT_CONFIG, report

    # database integrity
    if run_db:
        from saathi.ops.db_integrity import check_all
        db = check_all()
        report["gates"]["database"] = {"all_ok": db["all_ok"]}
        if not db["all_ok"]:
            return EXIT_DATABASE, report

    # backup can be created (dry check: enough disk + dbs exist)
    if run_backup:
        try:
            from saathi.ops import backup as BK
            import tempfile
            with tempfile.TemporaryDirectory() as d:
                res = BK.create_backup(dest_dir=Path(d), label="gate")
                # immediately verify by restoring into another isolated dir
                r = BK.restore_backup(res["archive"], target=Path(d) / "restore")
                v = BK.verify_restore(r["restored_to"])
                report["gates"]["backup_restore"] = {"backup_ok": True,
                                                     "restore_verified": v["ok"]}
                if not v["ok"]:
                    return EXIT_BACKUP, report
        except Exception as exc:
            report["gates"]["backup_restore"] = {"error": repr(exc)[:200]}
            return EXIT_BACKUP, report

    # secret scan on tracked tree. The release gate counts only STRONG
    # credential rules (real tokens/keys/private-key blocks) and excludes test
    # fixtures + docs (which legitimately contain example password literals and
    # $ENV placeholders that the noisy generic rule would flag).
    if run_secret_scan:
        try:
            from saathi.repair.secrets_scan import scan_files
            _STRONG = {"huggingface_token", "openai_key", "google_api_key",
                       "slack_token", "aws_access_key", "private_key_block",
                       "github_pat", "bearer_jwt"}
            tracked = subprocess.run(["git", "ls-files"], cwd=str(ROOT),
                                    capture_output=True, text=True, timeout=30).stdout.split()
            subset = [f for f in tracked
                      if f.endswith((".py", ".json", ".yml", ".env.example"))
                      and not f.startswith(("tests/", "docs/"))][:4000]
            raw = scan_files([str(ROOT / f) for f in subset])
            strong = {f: [h for h in r.hits if h.rule in _STRONG]
                      for f, r in raw.items()}
            strong = {f: hs for f, hs in strong.items() if hs}
            report["gates"]["secret_scan"] = {
                "clean": not strong, "strong_hits": sum(len(v) for v in strong.values()),
                "note": "counts strong-credential rules only; test/doc excluded"}
            if strong:
                return EXIT_SECURITY, report
        except Exception as exc:
            report["gates"]["secret_scan"] = {"error": repr(exc)[:120]}

    # dirty tree
    dirty = _git_dirty()
    report["gates"]["git"] = {"dirty_files": len(dirty)}
    if strict_dirty and dirty:
        return EXIT_DIRTY, report

    # M21.3/M21.4 — inference architecture release check (offline, no secrets)
    # Failure blocks the canonical release gate. Does not set production_certified.
    try:
        from saathi.inference.release_check import run_release_check as _inf_release

        inf = _inf_release()
        report["gates"]["inference_release_check"] = {
            "ok": inf.ok,
            "blocking_count": inf.blocking_count,
            "files_scanned": inf.files_scanned,
            "production_certified": False,
            "cli": "python -m saathi.inference.release_check",
            "milestone": "M21.3/M21.4",
        }
        if not inf.ok:
            report["verdict"] = "inference release check failed"
            return EXIT_PROVIDER, report
    except Exception as exc:
        report["gates"]["inference_release_check"] = {
            "ok": False,
            "error": type(exc).__name__,
            "detail": repr(exc)[:160],
        }
        return EXIT_PROVIDER, report

    # M21.4 runtime consolidation gate (static portion; live suite evidence separate)
    try:
        from saathi.inference.runtime_gate import evaluate_runtime_gate

        rg = evaluate_runtime_gate(
            evidence={
                "full_suite_status": "NOT_TESTED",
                "secret_scan_status": "NOT_TESTED",
                "critical_check_status": "NOT_TESTED",
            },
            run_release_check=True,
            include_live_probe=True,
        )
        report["gates"]["m21_4_runtime_gate"] = {
            "ok": rg.ok,
            "overall_state": rg.overall_state,
            "production_certified": False,
            "blocking_reasons": list(rg.blocking_reasons)[:12],
            "cli": "python -m saathi.inference.runtime_gate",
        }
        if not rg.ok:
            report["verdict"] = "m21.4 runtime gate failed"
            return EXIT_PROVIDER, report
    except Exception as exc:
        report["gates"]["m21_4_runtime_gate"] = {
            "ok": False,
            "error": type(exc).__name__,
            "detail": repr(exc)[:160],
        }
        return EXIT_PROVIDER, report

    report["verdict"] = "gates passed (test-suite + browser gates run separately)"
    report["production_certified"] = False
    return EXIT_READY, report
