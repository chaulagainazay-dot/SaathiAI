"""M25 — Canonical production-certification evidence store.

First-class artifacts for the three package gates that were previously only
injectable as NOT_TESTED placeholders:

  * full_suite_evidence
  * secret_scan_evidence
  * critical_check_evidence

Also records a package fingerprint (code/policy/schema/model identity) so
temporary RAM drops or discover re-runs do not invalidate suite/scan evidence.

CLI::

    python -m saathi.inference.cert_evidence status
    python -m saathi.inference.cert_evidence record-secret-scan
    python -m saathi.inference.cert_evidence record-critical-checks
    python -m saathi.inference.cert_evidence record-full-suite [--from-log PATH]
    python -m saathi.inference.cert_evidence record-package
    python -m saathi.inference.cert_evidence inject-for-gate

Atomic JSON writes only. No secrets in artifacts.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[2]
# TEST-INFRA-2: evidence artifacts are written under the repository tree, which
# means a test run rewrites tracked files. ``SAATHI_EVIDENCE_ROOT`` redirects the
# evidence OUTPUT root only. ROOT itself stays the real repository root because it
# is also used for source scanning, subprocess cwd, and relative_to().
_EVIDENCE_ROOT_ENV = os.environ.get("SAATHI_EVIDENCE_ROOT", "").strip()
EVIDENCE_ROOT = Path(_EVIDENCE_ROOT_ENV) if _EVIDENCE_ROOT_ENV else ROOT
EVIDENCE_DIR = EVIDENCE_ROOT / "docs" / "evidence" / "m25" / "cert"
SCHEMA = "m25.cert_evidence.v1"
PRODUCER_VERSION = "m25.cert_evidence.1"
# Suite/scan/critical evidence stays valid for 14 days unless fingerprint mismatches
DEFAULT_TTL_SECONDS = 14 * 24 * 3600

# Paths for each artifact
SUITE_PATH = EVIDENCE_DIR / "full_suite_evidence.json"
SECRET_PATH = EVIDENCE_DIR / "secret_scan_evidence.json"
CRITICAL_PATH = EVIDENCE_DIR / "critical_check_evidence.json"
FOCUSED_PATH = EVIDENCE_DIR / "focused_suite_evidence.json"
PACKAGE_PATH = EVIDENCE_DIR / "certification_package.json"

# Material files for package fingerprint (policy/code identity — not RAM)
_FINGERPRINT_PATHS = (
    "saathi/inference/runtime_gate.py",
    "saathi/inference/release_check.py",
    "saathi/inference/live_cert_m25.py",
    "saathi/inference/cert_evidence.py",
    "saathi/inference/gateway_path.py",
    "saathi/inference/certification.py",
    "saathi/inference/provider_policy.py",
    "saathi/inference/residual_paths.py",
    "docs/M21_3_RESIDUAL_EXCEPTION_MANIFEST.json",
    "saathi/repair/critical_checks.json",
)


@dataclass
class EvidenceRecord:
    """One certification evidence artifact."""

    evidence_id: str
    schema: str = SCHEMA
    status: str = "MISSING"  # PASS | FAIL | STALE | MISSING | ENVIRONMENT_BLOCKED
    producer: str = "saathi.inference.cert_evidence"
    producer_version: str = PRODUCER_VERSION
    created_at: str = ""
    expires_at: str = ""
    ttl_seconds: int = DEFAULT_TTL_SECONDS
    package_fingerprint: str = ""
    tip_commit: str = ""
    detail: str = ""
    metrics: dict[str, Any] = field(default_factory=dict)
    privacy_safe: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _iso(dt: Optional[datetime] = None) -> str:
    return (dt or _utc_now()).isoformat()


def _git_head() -> str:
    try:
        r = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=5,
        )
        return (r.stdout or "").strip() if r.returncode == 0 else ""
    except Exception:
        return ""


def package_fingerprint() -> str:
    """Fingerprint of material cert code/policy (not environment RAM)."""
    h = hashlib.sha256()
    h.update(b"m25.cert.package.v1\n")
    for rel in _FINGERPRINT_PATHS:
        p = ROOT / rel
        h.update(rel.encode())
        h.update(b"\0")
        if p.is_file():
            h.update(p.read_bytes())
        h.update(b"\n")
    # Live model identity from last successful cert if present
    live = EVIDENCE_ROOT / "docs" / "evidence" / "m25" / "LAST_SUCCESSFUL_LIVE_CERTIFICATION.json"
    if live.is_file():
        try:
            data = json.loads(live.read_text(encoding="utf-8"))
            mid = (data.get("selected_model") or {}).get("model_id") or ""
            h.update(f"live_model:{mid}".encode())
        except Exception:
            pass
    return "sha256:" + h.hexdigest()[:32]


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    os.replace(str(tmp), str(path))


def _load_json(path: Path) -> Optional[dict[str, Any]]:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def evaluate_freshness(
    record: dict[str, Any],
    *,
    current_fingerprint: Optional[str] = None,
    now: Optional[datetime] = None,
) -> str:
    """Return PASS | STALE | FAIL | MISSING for a stored record."""
    if not record:
        return "MISSING"
    status = (record.get("status") or "").upper()
    if status == "FAIL":
        return "FAIL"
    if status not in {"PASS", "OK", "TRUE"}:
        if status in {"STALE", "MISSING", "ENVIRONMENT_BLOCKED"}:
            return status
        # unknown status treated as missing
        if status not in {"PASS"}:
            return "MISSING" if status in {"", "MISSING", "NOT_TESTED"} else status

    fp = current_fingerprint or package_fingerprint()
    if record.get("package_fingerprint") and record["package_fingerprint"] != fp:
        return "STALE"

    exp = record.get("expires_at") or ""
    if exp:
        try:
            exp_dt = datetime.fromisoformat(exp.replace("Z", "+00:00"))
            n = now or _utc_now()
            if n > exp_dt:
                return "STALE"
        except Exception:
            return "STALE"
    return "PASS"


def write_evidence(
    evidence_id: str,
    *,
    status: str,
    detail: str = "",
    metrics: Optional[dict[str, Any]] = None,
    path: Optional[Path] = None,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> EvidenceRecord:
    """Atomically write one evidence artifact."""
    now = _utc_now()
    exp = datetime.fromtimestamp(now.timestamp() + int(ttl_seconds), tz=timezone.utc).replace(
        microsecond=0
    )
    rec = EvidenceRecord(
        evidence_id=evidence_id,
        status=status.upper(),
        created_at=_iso(now),
        expires_at=_iso(exp),
        ttl_seconds=int(ttl_seconds),
        package_fingerprint=package_fingerprint(),
        tip_commit=_git_head(),
        detail=detail[:500],
        metrics=dict(metrics or {}),
    )
    target = path or {
        "full_suite_evidence": SUITE_PATH,
        "secret_scan_evidence": SECRET_PATH,
        "critical_check_evidence": CRITICAL_PATH,
        "focused_suite_evidence": FOCUSED_PATH,
    }.get(evidence_id, EVIDENCE_DIR / f"{evidence_id}.json")
    _atomic_write_json(target, rec.to_dict())
    return rec


def load_evidence(evidence_id: str) -> Optional[dict[str, Any]]:
    path = {
        "full_suite_evidence": SUITE_PATH,
        "secret_scan_evidence": SECRET_PATH,
        "critical_check_evidence": CRITICAL_PATH,
        "focused_suite_evidence": FOCUSED_PATH,
    }.get(evidence_id, EVIDENCE_DIR / f"{evidence_id}.json")
    return _load_json(path)


def evidence_status_for_gate(evidence_id: str) -> tuple[str, dict[str, Any]]:
    """Status string for runtime gate: PASS|FAIL|STALE|MISSING."""
    rec = load_evidence(evidence_id)
    if not rec:
        return "MISSING", {"evidence_id": evidence_id, "path": ""}
    fresh = evaluate_freshness(rec)
    meta = {
        "evidence_id": evidence_id,
        "stored_status": rec.get("status"),
        "freshness": fresh,
        "created_at": rec.get("created_at"),
        "expires_at": rec.get("expires_at"),
        "package_fingerprint": rec.get("package_fingerprint"),
        "current_fingerprint": package_fingerprint(),
        "detail": rec.get("detail"),
        "metrics": rec.get("metrics") or {},
    }
    if fresh == "PASS" and (rec.get("status") or "").upper() == "PASS":
        return "PASS", meta
    if fresh == "STALE":
        return "STALE", meta
    if (rec.get("status") or "").upper() == "FAIL" or fresh == "FAIL":
        return "FAIL", meta
    return fresh, meta


def record_secret_scan() -> EvidenceRecord:
    """Run strong-credential secret scan (same policy as ops release_gate)."""
    from saathi.repair.secrets_scan import scan_files

    _STRONG = {
        "huggingface_token",
        "openai_key",
        "google_api_key",
        "slack_token",
        "aws_access_key",
        "private_key_block",
        "github_pat",
        "bearer_jwt",
    }
    tracked = subprocess.run(
        ["git", "ls-files"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=30,
    ).stdout.split()
    subset = [
        f
        for f in tracked
        if f.endswith((".py", ".json", ".yml", ".env.example"))
        and not f.startswith(("tests/", "docs/"))
    ][:4000]
    raw = scan_files([str(ROOT / f) for f in subset])
    strong = {
        f: [h for h in r.hits if h.rule in _STRONG] for f, r in raw.items()
    }
    strong = {f: hs for f, hs in strong.items() if hs}
    clean = not strong
    return write_evidence(
        "secret_scan_evidence",
        status="PASS" if clean else "FAIL",
        detail="strong-credential rules only; tests/docs excluded",
        metrics={
            "files_scanned": len(subset),
            "strong_hits": sum(len(v) for v in strong.values()),
            "clean": clean,
        },
        path=SECRET_PATH,
    )


def record_critical_checks(*, ids_prefix: Optional[tuple[str, ...]] = None) -> EvidenceRecord:
    """Run critical checks (optionally filtered by id prefix for speed).

    Default: M21.4+M22+M23+m24 related blocking checks + server.import.
    Full manifest available via ids_prefix=().
    """
    from saathi.repair.manifest import load_manifest
    from saathi.repair import verify as verify_mod

    checks = load_manifest()
    if ids_prefix is None:
        ids_prefix = ("m21.4", "m22", "m23", "m24", "m25", "security.")
    selected = [
        c
        for c in checks
        if not ids_prefix or any(c.id.startswith(p) or p in c.id for p in ids_prefix)
    ]
    results: dict[str, Any] = {}
    all_ok = True
    for chk in selected:
        out = verify_mod.run_pytest(chk.targets)
        ok = out.ran and out.failed == 0 and out.errors == 0
        results[chk.id] = {
            "ok": ok,
            "blocking": chk.blocking,
            "failed": out.failed,
            "errors": out.errors,
            "passed": out.passed,
        }
        if chk.blocking and not ok:
            all_ok = False
    import_ok, routes = verify_mod.server_smoke()
    results["server.import"] = {"ok": import_ok, "routes": routes, "blocking": True}
    if not import_ok:
        all_ok = False

    return write_evidence(
        "critical_check_evidence",
        status="PASS" if all_ok else "FAIL",
        detail=f"checks={len(selected)}+server.import",
        metrics={
            "all_ok": all_ok,
            "checks_run": len(selected) + 1,
            "failed_ids": [k for k, v in results.items() if not v.get("ok")],
            "results": {k: {"ok": v.get("ok"), "blocking": v.get("blocking")} for k, v in results.items()},
        },
        path=CRITICAL_PATH,
    )


def record_full_suite(
    *,
    from_log: Optional[Path] = None,
    run_pytest: bool = False,
    passed: Optional[int] = None,
    failed: Optional[int] = None,
    skipped: Optional[int] = None,
    duration_s: Optional[float] = None,
) -> EvidenceRecord:
    """Record full suite evidence from log, explicit counts, or live pytest run."""
    metrics: dict[str, Any] = {}
    status = "FAIL"
    detail = ""

    if from_log and Path(from_log).is_file():
        text = Path(from_log).read_text(encoding="utf-8", errors="replace")
        # pytest summary: "3095 passed, 1 skipped, 370 warnings in 669.97s"
        m = re.search(
            r"(\d+)\s+passed(?:,\s*(\d+)\s+skipped)?(?:,\s*(\d+)\s+failed)?.*?(?:in\s+([\d.]+)s)?",
            text,
        )
        # also handle "5 failed, 3083 passed"
        m2 = re.search(
            r"(?:(\d+)\s+failed,\s*)?(\d+)\s+passed(?:,\s*(\d+)\s+skipped)?",
            text,
        )
        if m2:
            failed_n = int(m2.group(1) or 0)
            passed_n = int(m2.group(2) or 0)
            skipped_n = int(m2.group(3) or 0)
            metrics = {
                "passed": passed_n,
                "failed": failed_n,
                "skipped": skipped_n,
                "source": f"log:{from_log}",
            }
            status = "PASS" if failed_n == 0 and passed_n > 0 else "FAIL"
            detail = f"{passed_n} passed, {failed_n} failed, {skipped_n} skipped"
        elif m:
            passed_n = int(m.group(1))
            skipped_n = int(m.group(2) or 0)
            failed_n = int(m.group(3) or 0)
            metrics = {
                "passed": passed_n,
                "failed": failed_n,
                "skipped": skipped_n,
                "duration_s": float(m.group(4)) if m.group(4) else None,
                "source": f"log:{from_log}",
            }
            status = "PASS" if failed_n == 0 and passed_n > 0 else "FAIL"
            detail = f"{passed_n} passed, {failed_n} failed, {skipped_n} skipped"
        else:
            status = "FAIL"
            detail = "could not parse pytest summary from log"
            metrics = {"source": f"log:{from_log}", "parse_error": True}
    elif passed is not None:
        failed_n = int(failed or 0)
        skipped_n = int(skipped or 0)
        passed_n = int(passed)
        metrics = {
            "passed": passed_n,
            "failed": failed_n,
            "skipped": skipped_n,
            "duration_s": duration_s,
            "source": "explicit_counts",
        }
        status = "PASS" if failed_n == 0 and passed_n > 0 else "FAIL"
        detail = f"{passed_n} passed, {failed_n} failed, {skipped_n} skipped"
    elif run_pytest:
        t0 = time.time()
        r = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "--tb=line"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=3600,
        )
        text = (r.stdout or "") + "\n" + (r.stderr or "")
        # write log for audit
        log_path = EVIDENCE_DIR / "last_full_suite.log"
        EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
        log_path.write_text(text[-200000:], encoding="utf-8")
        return record_full_suite(from_log=log_path)
    else:
        # Try last known log
        for cand in (
            Path("/tmp/m25_closeout_suite.log"),
            Path("/tmp/m25_suite_rerun.log"),
            EVIDENCE_DIR / "last_full_suite.log",
        ):
            if cand.is_file():
                return record_full_suite(from_log=cand)
        status = "MISSING"
        detail = "no suite log or counts provided"
        metrics = {"source": "none"}

    return write_evidence(
        "full_suite_evidence",
        status=status if status != "MISSING" else "FAIL",
        detail=detail,
        metrics=metrics,
        path=SUITE_PATH,
    )


def record_focused_suite() -> EvidenceRecord:
    """Run focused M25 + memory isolation tests."""
    t0 = time.time()
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_m25_live_provider_certification.py",
            "tests/test_memory_engine.py",
            "tests/test_m25_cert_evidence.py",
            "-q",
            "--tb=line",
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=600,
    )
    text = (r.stdout or "") + (r.stderr or "")
    m = re.search(r"(\d+)\s+passed", text)
    failed = re.search(r"(\d+)\s+failed", text)
    passed_n = int(m.group(1)) if m else 0
    failed_n = int(failed.group(1)) if failed else (0 if r.returncode == 0 else 1)
    ok = r.returncode == 0 and failed_n == 0
    return write_evidence(
        "focused_suite_evidence",
        status="PASS" if ok else "FAIL",
        detail=f"focused m25+memory exit={r.returncode}",
        metrics={
            "passed": passed_n,
            "failed": failed_n,
            "duration_s": round(time.time() - t0, 2),
            "returncode": r.returncode,
        },
        path=FOCUSED_PATH,
    )


def record_package(
    *,
    suite_log: Optional[Path] = None,
    suite_passed: Optional[int] = None,
    suite_failed: Optional[int] = None,
    suite_skipped: Optional[int] = None,
    run_full_pytest: bool = False,
    critical_prefixes: Optional[tuple[str, ...]] = None,
) -> dict[str, Any]:
    """Record secret scan + critical + full suite and write package summary."""
    secret = record_secret_scan()
    critical = record_critical_checks(ids_prefix=critical_prefixes)
    if suite_passed is not None:
        suite = record_full_suite(
            passed=suite_passed, failed=suite_failed, skipped=suite_skipped
        )
    else:
        suite = record_full_suite(from_log=suite_log, run_pytest=run_full_pytest)
    focused = record_focused_suite()

    package = {
        "schema": "m25.certification_package.v1",
        "created_at": _iso(),
        "package_fingerprint": package_fingerprint(),
        "tip_commit": _git_head(),
        "artifacts": {
            "secret_scan_evidence": secret.to_dict(),
            "critical_check_evidence": critical.to_dict(),
            "full_suite_evidence": suite.to_dict(),
            "focused_suite_evidence": focused.to_dict(),
        },
        "all_pass": all(
            r.status == "PASS" for r in (secret, critical, suite, focused)
        ),
        "privacy_safe": True,
        "cloud_fallback": False,
        "trading_guardian": "UNCHANGED / UNENGAGED",
    }
    _atomic_write_json(PACKAGE_PATH, package)
    return package


def inject_evidence_dict() -> dict[str, Any]:
    """Build evidence dict for evaluate_runtime_gate from on-disk artifacts."""
    out: dict[str, Any] = {}
    for eid, key in (
        ("full_suite_evidence", "full_suite_status"),
        ("secret_scan_evidence", "secret_scan_status"),
        ("critical_check_evidence", "critical_check_status"),
        ("focused_suite_evidence", "focused_suite_status"),
    ):
        st, meta = evidence_status_for_gate(eid)
        out[key] = st
        out[f"{key}_meta"] = meta
    return out


def status_report() -> dict[str, Any]:
    fp = package_fingerprint()
    items = {}
    for eid in (
        "full_suite_evidence",
        "secret_scan_evidence",
        "critical_check_evidence",
        "focused_suite_evidence",
    ):
        st, meta = evidence_status_for_gate(eid)
        items[eid] = {"status": st, **meta}
    return {
        "schema": "m25.cert_evidence_status.v1",
        "package_fingerprint": fp,
        "tip_commit": _git_head(),
        "items": items,
        "all_pass": all(v["status"] == "PASS" for v in items.values()),
    }


def main(argv: Optional[list[str]] = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    cmd = argv[0]
    if cmd == "status":
        print(json.dumps(status_report(), indent=2, default=str))
        return 0
    if cmd == "record-secret-scan":
        rec = record_secret_scan()
        print(json.dumps(rec.to_dict(), indent=2))
        return 0 if rec.status == "PASS" else 1
    if cmd == "record-critical-checks":
        rec = record_critical_checks()
        print(json.dumps(rec.to_dict(), indent=2))
        return 0 if rec.status == "PASS" else 1
    if cmd == "record-full-suite":
        log = None
        passed = failed = skipped = None
        run = False
        if "--from-log" in argv:
            i = argv.index("--from-log")
            log = Path(argv[i + 1])
        if "--passed" in argv:
            passed = int(argv[argv.index("--passed") + 1])
        if "--failed" in argv:
            failed = int(argv[argv.index("--failed") + 1])
        if "--skipped" in argv:
            skipped = int(argv[argv.index("--skipped") + 1])
        if "--run" in argv:
            run = True
        rec = record_full_suite(
            from_log=log, run_pytest=run, passed=passed, failed=failed, skipped=skipped
        )
        print(json.dumps(rec.to_dict(), indent=2))
        return 0 if rec.status == "PASS" else 1
    if cmd == "record-package":
        log = None
        if "--from-log" in argv:
            log = Path(argv[argv.index("--from-log") + 1])
        run = "--run-pytest" in argv
        passed = failed = skipped = None
        if "--passed" in argv:
            passed = int(argv[argv.index("--passed") + 1])
            failed = int(argv[argv.index("--failed") + 1]) if "--failed" in argv else 0
            skipped = int(argv[argv.index("--skipped") + 1]) if "--skipped" in argv else 0
        pkg = record_package(
            suite_log=log,
            suite_passed=passed,
            suite_failed=failed,
            suite_skipped=skipped,
            run_full_pytest=run,
        )
        print(json.dumps(pkg, indent=2, default=str))
        return 0 if pkg.get("all_pass") else 1
    if cmd == "inject-for-gate":
        print(json.dumps(inject_evidence_dict(), indent=2, default=str))
        return 0
    print(f"unknown command: {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
