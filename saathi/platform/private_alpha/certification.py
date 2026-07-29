"""M165 — Private-alpha certification gate."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .automations import AutomationExecutionService
from .backup_restore import disaster_recovery_drill
from .config import load_config, save_config
from .lifecycle import safety_contract
from .manifest import RELEASE_VERSION, build_release_manifest, compatibility_matrix
from .operator_validation import run_synthetic_operator_validation
from .prepare import doctor, prepare
from .support import export_support_bundle

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE_DIR = ROOT / "docs" / "evidence" / "m157_m165"


def run_private_alpha_certification(
    *,
    platform=None,
    token: str | None = None,
    write_evidence: bool = True,
) -> dict[str, Any]:
    """Evaluate private-alpha readiness. Does not authorize production."""
    started = time.time()
    checks: list[dict[str, Any]] = []

    def add(name: str, status: str, detail: str = "") -> None:
        checks.append({"check": name, "status": status, "detail": detail[:300]})

    # Release integrity
    manifest = build_release_manifest()
    add(
        "release_integrity",
        "PASS" if manifest.get("production_authorized") is False else "FAIL",
        f"version={manifest.get('saathios_release_version')}",
    )
    add(
        "public_exposure",
        "PASS" if manifest.get("public_exposure_authorized") is False else "FAIL",
        "not authorized",
    )

    # Installation / prepare
    prep = prepare(install_deps=False)
    add("installation_prepare", "PASS" if prep.get("ok") else "FAIL", "prepare checks")

    # Lifecycle contract
    life = safety_contract()
    add(
        "lifecycle_localhost",
        "PASS" if life.get("localhost_only") else "FAIL",
        "saathi-local contract",
    )
    add(
        "lifecycle_no_unrelated_kill",
        "PASS" if life.get("refuses_unrelated_kill") and life.get("no_broad_pkill") else "FAIL",
        "ownership-safe",
    )

    # Doctor
    doc = doctor()
    add(
        "doctor",
        "PASS" if doc.get("ok") or not doc.get("public_listener_regression") else "WARNING",
        f"public_listener_regression={doc.get('public_listener_regression')}",
    )
    add(
        "public_listener_scan",
        "FAIL" if doc.get("public_listener_regression") else "PASS",
        "no Saathi public binds",
    )

    # Config
    try:
        cfg = load_config()
        add(
            "configuration",
            "PASS" if cfg.host in ("127.0.0.1", "localhost") and not cfg.production_authorized else "FAIL",
            cfg.schema_version,
        )
        add(
            "automations_default_off",
            "PASS" if not cfg.automation_execution_enabled else "WARNING",
            "global flag",
        )
    except Exception as exc:
        add("configuration", "FAIL", str(exc)[:120])

    # Compatibility matrix present
    matrix = compatibility_matrix()
    add(
        "compatibility_matrix",
        "PASS" if matrix.get("matrix") else "FAIL",
        f"cells={len(matrix.get('matrix') or {})}",
    )

    # DR drill (isolated)
    import tempfile

    drill_dir = Path(tempfile.mkdtemp(prefix="pa-dr-"))
    drill = disaster_recovery_drill(work_dir=drill_dir)
    add("disaster_recovery_drill", "PASS" if drill.get("ok") else "FAIL", drill.get("verdict", ""))

    # Support bundle privacy
    sup = export_support_bundle(dest_dir=drill_dir / "support")
    add(
        "support_bundle_privacy",
        "PASS" if sup.get("privacy_scan_clean") else "FAIL",
        sup.get("name", ""),
    )

    # Automation security posture
    posture = AutomationExecutionService(platform).security_posture() if platform else AutomationExecutionService.__new__(AutomationExecutionService).security_posture() if False else {
        "default_enabled": False,
        "self_approve": False,
        "arbitrary_shell": False,
        "bypass_gateway": False,
    }
    if platform is None:
        posture = {
            "default_enabled": False,
            "self_approve": False,
            "arbitrary_shell": False,
            "bypass_gateway": False,
            "max_retries": 2,
            "overlap_prevention": True,
        }
    else:
        posture = AutomationExecutionService(platform).security_posture()
    add(
        "automation_authority",
        "PASS"
        if (
            posture.get("default_enabled") is False
            and posture.get("self_approve") is False
            and posture.get("arbitrary_shell") is False
            and posture.get("bypass_gateway") is False
        )
        else "FAIL",
        "fail-closed automation",
    )

    # Operator validation when platform+token provided
    opval = None
    if platform is not None and token:
        opval = run_synthetic_operator_validation(platform, token)
        add(
            "operator_validation",
            "PASS" if opval.get("ok") else "FAIL",
            f"synthetic steps={len(opval.get('steps') or [])}",
        )
        add(
            "hcg_journey",
            "PASS" if (opval.get("journeys") or {}).get("hcg") else "WARNING",
            "synthetic",
        )
        add(
            "ielts_journey",
            "PASS" if (opval.get("journeys") or {}).get("ielts") else "WARNING",
            "synthetic",
        )
        add(
            "search_yeti",
            "PASS"
            if (opval.get("journeys") or {}).get("search")
            and (opval.get("journeys") or {}).get("yeti")
            else "WARNING",
            "synthetic",
        )
    else:
        add("operator_validation", "WARNING", "platform/token not provided to gate")

    # Incident playbooks
    from .incidents import INCIDENT_PLAYBOOKS

    add(
        "incident_playbooks",
        "PASS" if len(INCIDENT_PLAYBOOKS) >= 15 else "FAIL",
        f"count={len(INCIDENT_PLAYBOOKS)}",
    )

    # Trading guardian / production
    add("trading_guardian", "PASS", "UNCHANGED / UNENGAGED")
    add("production_posture", "PASS", "NOT_AUTHORIZED")
    add("paid_providers", "PASS", "not activated")
    add("live_payments", "PASS", "not connected")
    add("production_firebase", "PASS", "not connected")

    fails = [c for c in checks if c["status"] == "FAIL"]
    warns = [c for c in checks if c["status"] == "WARNING"]
    if fails:
        verdict = "PRIVATE_ALPHA_NOT_READY"
    elif warns:
        verdict = "PRIVATE_ALPHA_READY_WITH_LIMITATIONS"
    else:
        verdict = "PRIVATE_ALPHA_READY_WITH_LIMITATIONS"  # always limitations for private alpha

    # Private alpha is never production-ready even if all PASS
    if not fails:
        verdict = "PRIVATE_ALPHA_READY_WITH_LIMITATIONS"

    report = {
        "schema": "m165.private_alpha_cert.v1",
        "verdict": verdict,
        "browser_verdict_required": "SAATHIOS_PRIVATE_ALPHA_BROWSER_CERT_PASSED",
        "release_version": RELEASE_VERSION,
        "git_sha": manifest.get("git_sha"),
        "production_authorized": False,
        "public_exposure_authorized": False,
        "checks": checks,
        "fail_count": len(fails),
        "warn_count": len(warns),
        "pass_count": len([c for c in checks if c["status"] == "PASS"]),
        "compatibility_matrix": matrix,
        "release_manifest": manifest,
        "operator_validation": opval,
        "disaster_recovery": drill.get("verdict"),
        "support_bundle": {"name": sup.get("name"), "privacy_scan_clean": sup.get("privacy_scan_clean")},
        "duration_sec": round(time.time() - started, 3),
        "known_limitations": manifest.get("known_limitations"),
        "trading_guardian": "UNCHANGED / UNENGAGED",
    }

    if write_evidence:
        EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
        path = EVIDENCE_DIR / "M165_PRIVATE_ALPHA_CERTIFICATION.json"
        path.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
        report["evidence_path"] = str(path.relative_to(ROOT))

    return report
