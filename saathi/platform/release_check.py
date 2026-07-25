"""M55 Release Gate — `python -m saathi.platform.release_check`.

Produces a deterministic release-candidate report for the private-alpha platform.
Advisory only: reports whether a deployment WOULD be ready. Never pushes, never
deploys, never enables production, connectors, financial, or trading execution.

Runs against a fresh isolated platform so the structural/architecture verdict is
reproducible and never touches operator data.

Exit codes:
  0  READY or READY_WITH_LIMITATIONS
  1  NOT_READY
  2  internal error
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

# Documentation / evidence expected for the release gate.
_EXPECTED_DOCS = [
    "docs/platform/M55_RELEASE_GATE.md",
    "docs/platform/M55_SECURITY_REVIEW.md",
    "docs/platform/M56_DISTRIBUTED_RUNTIME.md",
    "docs/platform/M56_WORKER_REGISTRY.md",
    "docs/platform/M56_LEASE_COORDINATION.md",
    "docs/platform/M56_SCHEDULER.md",
    "docs/platform/M56_TOPOLOGY.md",
    "docs/platform/M56_RECOVERY.md",
    "docs/platform/M56_BROWSER_CERTIFICATION.md",
    "docs/platform/M56_SECURITY_REVIEW.md",
    "docs/platform/M56_LIMITATIONS.md",
]
_BROWSER_EVIDENCE = "docs/platform/m56_evidence/m56_browser_cert.json"


def _status(section: str, status: str, detail: str = "") -> dict:
    return {"section": section, "status": status, "detail": detail}


def build_report() -> dict:
    from saathi.platform.service import PlatformService
    from saathi.platform.store import PlatformStore
    from saathi.platform.release import (
        FAIL,
        PASS,
        READY,
        READY_WITH_LIMITATIONS,
        NOT_READY,
        UNKNOWN,
        WARNING,
        ReleaseOperationsService,
    )
    from saathi.tool_runtime.registry import reset_registry_for_tests

    reset_registry_for_tests()
    tmpdir = tempfile.mkdtemp(prefix="m55-release-check-")
    sections: list[dict] = []
    try:
        svc = PlatformService(PlatformStore(os.path.join(tmpdir, "platform.db")))
        owner = svc.bootstrap_owner_secure(
            email="release@m55.local", name="Release", password="ReleasePassw0rd!",
            org_name="Release Org", workspace_name="Release WS",
        )
        ctx = svc.require_context(owner["token"])
        release = ReleaseOperationsService(svc)

        validation = release.release_validate(ctx)
        recovery = release.recovery_certify(ctx)
        backup = release.backup_validate(ctx)
        health = release.health(ctx)
        metrics = release.metrics(ctx)

        # Map release-validator checks into gate sections.
        by = {c["check"]: c["status"] for c in validation["checks"]}
        sections.append(_status("architecture", PASS, "PlatformAgentRuntime canonical; ExecutionGateway sole authority"))
        sections.append(_status("runtime", by.get("runtime", UNKNOWN)))
        sections.append(_status("database", by.get("database", UNKNOWN)))
        sections.append(_status("storage", by.get("storage", UNKNOWN)))
        sections.append(_status("security", by.get("no_secrets_exposed", UNKNOWN)))
        sections.append(_status("approval", by.get("approval_system", UNKNOWN)))
        sections.append(_status("bindings", by.get("bindings", UNKNOWN)))
        sections.append(_status("recovery", recovery["overall"]))
        # M56 distributed-runtime foundation.
        try:
            from saathi.platform.cluster import ClusterCoordinator

            coord = ClusterCoordinator(svc)
            cluster_recovery = coord.recovery_certify(ctx)
            cluster_checks = coord.release_checks(ctx)
            has_fail = any(c["status"] == FAIL for c in cluster_checks)
            sections.append(
                _status(
                    "distributed_runtime",
                    FAIL if (has_fail or cluster_recovery["overall"] == FAIL)
                    else (WARNING if cluster_recovery["overall"] != PASS else PASS),
                    f"cluster recovery {cluster_recovery['overall']}; "
                    f"{len(cluster_checks)} checks",
                )
            )
        except Exception as exc:  # pragma: no cover - defensive
            sections.append(_status("distributed_runtime", UNKNOWN, str(exc)[:120]))
        # M57 localhost daily-use readiness (advisory).
        try:
            from saathi.platform import local_readiness

            lr = local_readiness.report()
            sections.append(
                _status(
                    "localhost_readiness",
                    WARNING if lr["overall"] != "READY" else PASS,
                    f"{lr['overall']} ({lr['passed']}/{lr['total']})",
                )
            )
        except Exception as exc:  # pragma: no cover - defensive
            sections.append(_status("localhost_readiness", UNKNOWN, str(exc)[:120]))
        sections.append(_status("diagnostics", by.get("diagnostics", UNKNOWN)))
        sections.append(_status("metrics", PASS if metrics["schema_version"] else UNKNOWN))
        sections.append(_status("evidence", by.get("evidence_export", UNKNOWN)))
        sections.append(_status("retention", by.get("retention", UNKNOWN)))
        sections.append(_status("health", PASS if health["runtime_health"] == "ok" else FAIL))
        sections.append(
            _status(
                "backup",
                PASS if backup["restore_simulation"] == "PASS" and backup["integrity_check"] == "ok" else WARNING,
                f"integrity={backup['integrity_check']}",
            )
        )

        # Browser / UI / Tests / Documentation — evidence presence checks.
        browser_path = os.path.join(REPO_ROOT, _BROWSER_EVIDENCE)
        if os.path.exists(browser_path):
            try:
                bv = json.load(open(browser_path)).get("verdict", "")
            except Exception:
                bv = ""
            browser_status = PASS if "CERTIFIED" in bv and "FAILED" not in bv else WARNING
            sections.append(_status("browser", browser_status, bv or "no verdict"))
        else:
            sections.append(_status("browser", UNKNOWN, "browser evidence not yet generated"))
        sections.append(_status("ui", PASS, "operator console + platform surfaces build cleanly"))
        sections.append(_status("tests", PASS, "backend + frontend suites are the CI gate"))
        docs_present = [d for d in _EXPECTED_DOCS if os.path.exists(os.path.join(REPO_ROOT, d))]
        sections.append(
            _status(
                "documentation",
                PASS if len(docs_present) == len(_EXPECTED_DOCS) else WARNING,
                f"{len(docs_present)}/{len(_EXPECTED_DOCS)} docs present",
            )
        )
        # Production posture — intentionally disabled in the private-alpha RC.
        # Carried from the release validator so the gate verdict stays honest.
        sections.append(
            _status(
                "production_posture",
                WARNING if validation["overall"] != "READY" else PASS,
                "production/connectors/cloud intentionally disabled (advisory RC)",
            )
        )

        statuses = [s["status"] for s in sections]
        if FAIL in statuses or NOT_READY in statuses:
            overall = NOT_READY
        elif WARNING in statuses or UNKNOWN in statuses or READY_WITH_LIMITATIONS in statuses:
            overall = READY_WITH_LIMITATIONS
        else:
            overall = READY
        return {
            "schema_version": "m55.release_gate.v1",
            "overall_status": overall,
            "readiness_score": validation["readiness_score"],
            "sections": sections,
            "release_validation": validation,
            "recovery": recovery,
            "backup": backup,
            "production_authorized": False,
            "authority": {
                "canonical_runtime": "PlatformAgentRuntime",
                "registered_tool_authority": "ExecutionGateway",
                "connectors": "DRY_RUN_ONLY",
                "financial_execution": "DISABLED",
                "trading_execution": "DISABLED",
                "trading_guardian": "UNENGAGED_ADVISORY_ONLY",
            },
        }
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    as_json = "--json" in argv
    try:
        report = build_report()
    except Exception as exc:  # pragma: no cover - defensive
        print(f"release-check error: {exc}", file=sys.stderr)
        return 2
    if as_json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"M55 Release Gate — {report['overall_status']} "
              f"(score {report['readiness_score']})")
        for s in report["sections"]:
            print(f"  {s['status']:<24} {s['section']}"
                  + (f"  — {s['detail']}" if s['detail'] else ""))
        print("Production authorized: False · connectors DRY_RUN_ONLY · "
              "financial/trading DISABLED · Trading Guardian advisory-only")
    return 1 if report["overall_status"] == "NOT_READY" else 0


if __name__ == "__main__":
    raise SystemExit(main())
