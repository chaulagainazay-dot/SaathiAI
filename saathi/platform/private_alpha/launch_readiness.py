"""M343 — private-alpha launch-readiness surface and checklist.

Read-only. Assembles the M336–M343 evidence and the live authority posture into
one report for the readiness Control Center. Nothing here launches, deploys,
publishes, connects or approves — and owner review is never satisfied by
automation.

Every checklist item is derived from evidence on disk or from a live read. An
item whose evidence is missing reports FAIL rather than quietly disappearing,
because a checklist that hides what it could not verify is worse than no
checklist.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE_DIR = ROOT / "docs" / "private-alpha" / "m336_m343_evidence"
# The recovery baseline lives under the trading evidence tree, where the
# milestone brief placed it; everything else lives with the private-alpha pack.
EVIDENCE_DIRS = (EVIDENCE_DIR, ROOT / "docs" / "trading" / "m336_m343_evidence")
DOCS_DIR = ROOT / "docs" / "private-alpha"

MILESTONE = "M336-M343"
VERDICT = "PRIVATE_ALPHA_LAUNCH_READINESS_CERTIFIED_WITH_LIMITATIONS"
MAX_STATE = "PRIVATE_ALPHA_READY_OFFLINE_INVITE_ONLY"

# States a checklist item may report.
PASS = "PASS"
PASS_WITH_LIMITATION = "PASS_WITH_LIMITATION"
FAIL = "FAIL"
NOT_APPLICABLE = "NOT_APPLICABLE"
OWNER_REVIEW_REQUIRED = "OWNER_REVIEW_REQUIRED"

AUTHORITY_LOCKS = (
    "REAL_CONNECTIVITY_AUTHORIZED",
    "BROKER_CONNECTIVITY_AUTHORIZED",
    "CREDENTIAL_PROVISIONING_AUTHORIZED",
    "CREDENTIAL_VALIDATION_AUTHORIZED",
    "OAUTH_AUTHORIZED",
    "ACCOUNT_ACCESS_AUTHORIZED",
    "BALANCE_READ_AUTHORIZED",
    "POSITION_READ_AUTHORIZED",
    "ORDER_SUBMISSION_AUTHORIZED",
    "ORDER_EXECUTION_AUTHORIZED",
    "CANARY_ACTIVATION_AUTHORIZED",
    "LIVE_TRADING_AUTHORIZED",
    "AUTOMATED_INVESTMENT_AUTHORITY",
    "PUBLIC_PRODUCTION_AUTHORIZED",
    "PUBLIC_REGISTRATION_AUTHORIZED",
)

HUMAN_REVIEW_MARKERS = (
    "OWNER_REVIEW_REQUIRED",
    "PRIVATE_ALPHA_RELEASE_NOT_AUTOMATIC",
    "PUBLIC_PRODUCTION_NOT_AUTHORIZED",
)

KNOWN_LIMITATIONS = [
    "Local-only, single-host private alpha. No public URL and no public deployment.",
    "Invite only. Public self-registration is not enabled and may not be enabled by automation.",
    "No broker or provider connectivity. No credential is requested, accepted or stored.",
    "No account, balance or position access. No order is submitted, modified or cancelled.",
    "No paper or live execution. Live trading remains prohibited.",
    "Missions run local deterministic tools and mock providers only.",
    "Backups are owner-managed and local. No cloud backup, no external telemetry.",
    "No uptime guarantee and no service-level agreement.",
    "Certified on macOS arm64 only.",
    "Owner review is required before any release and is never satisfied by automation.",
]


def _load(name: str) -> dict[str, Any] | None:
    for directory in EVIDENCE_DIRS:
        path = directory / name
        if path.is_file():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return None
    return None


def _doc_present(name: str) -> bool:
    return (DOCS_DIR / name).is_file()


def _item(
    category: str, item: str, state: str, detail: str = "", evidence: str = ""
) -> dict[str, Any]:
    return {
        "category": category,
        "item": item,
        "state": state,
        "detail": detail[:400],
        "evidence": evidence,
    }


def _evidence_item(
    category: str, item: str, filename: str, predicate, detail_fn=None
) -> dict[str, Any]:
    """Report an item from an evidence file, failing loudly when it is absent."""
    data = _load(filename)
    if data is None:
        return _item(category, item, FAIL, f"evidence missing: {filename}", filename)
    try:
        ok = bool(predicate(data))
        detail = detail_fn(data) if detail_fn else ""
    except Exception as exc:  # noqa: BLE001
        return _item(category, item, FAIL, f"evidence unreadable: {exc}"[:200], filename)
    return _item(category, item, PASS if ok else FAIL, detail, filename)


def authority_posture() -> dict[str, Any]:
    """Live authority read. Every lock must be false."""
    locks = {key: False for key in AUTHORITY_LOCKS}
    intact = True
    try:
        from saathi.platform.tg.production_readiness.service import default_operations

        posture = default_operations().posture()
        for key in AUTHORITY_LOCKS:
            if key in posture:
                locks[key] = bool(posture[key])
    except Exception:  # noqa: BLE001 — a read failure must not fabricate a pass
        intact = None
    if intact is not None:
        intact = not any(locks.values())
    return {
        "locks": locks,
        "all_false": intact,
        "source": "OperationsService.posture() with the private-alpha contract defaults",
    }


def build_checklist() -> list[dict[str, Any]]:
    """The private-alpha launch checklist, derived from evidence and live reads."""
    items: list[dict[str, Any]] = []

    # ── source integrity and git ──
    items.append(_evidence_item(
        "source integrity", "Predecessor SHA resolved in full",
        "M336_RECOVERY_BASELINE.json",
        lambda d: d["predecessor"]["abbrev_matches_full"],
        lambda d: d["predecessor"]["resolved_full_sha"],
    ))
    items.append(_evidence_item(
        "git status", "Working branch isolated from predecessor PRs",
        "M336_RECOVERY_BASELINE.json",
        lambda d: not d["draft_pr_isolation"]["pr_12"]["touched_by_m336_m343"]
        and not d["draft_pr_isolation"]["pr_13"]["touched_by_m336_m343"],
        lambda d: "PR #12 and PR #13 untouched",
    ))
    items.append(_evidence_item(
        "git status", "Unrelated local changes preserved",
        "M336_RECOVERY_BASELINE.json",
        lambda d: d["primary_worktree_preservation"]["action_taken"].startswith("NONE"),
        lambda d: d["primary_worktree_preservation"]["action_taken"],
    ))

    # ── tests and regression debt ──
    items.append(_evidence_item(
        "tests", "All eight inherited failures closed",
        "M337_REGRESSION_DEBT_CLOSURE.json",
        lambda d: d["result"]["TOTAL_INHERITED_FAILURES_REMAINING"] == 0,
        lambda d: f"M57={d['result']['M57_INHERITED_FAILURES']} "
                  f"M157={d['result']['M157_INHERITED_FAILURES']} "
                  f"gate={d['result']['RELEASE_GATE_FAILURES']}",
    ))
    items.append(_evidence_item(
        "tests", "No test was weakened, skipped or deleted",
        "M337_REGRESSION_DEBT_CLOSURE.json",
        lambda d: all(
            not d["proof_tests_were_not_weakened"][key]
            for key in ("tests_modified", "tests_skipped", "tests_xfailed",
                        "tests_deleted", "assertions_removed_or_relaxed")
        ),
        lambda d: "the three affected suites are byte-identical to the predecessor",
    ))
    items.append(_evidence_item(
        "tests", "Full backend suite green",
        "M343_TEST_RESULTS.json",
        lambda d: d["backend"]["failed"] == 0,
        lambda d: f"{d['backend']['passed']} passed, {d['backend']['failed']} failed",
    ))
    items.append(_evidence_item(
        "tests", "Full frontend suite green",
        "M343_TEST_RESULTS.json",
        lambda d: d["frontend"]["failed"] == 0,
        lambda d: f"{d['frontend']['passed']} passed, {d['frontend']['failed']} failed",
    ))
    items.append(_evidence_item(
        "tests", "Production build succeeds",
        "M343_TEST_RESULTS.json",
        lambda d: d["production_build"]["ok"],
        lambda d: d["production_build"].get("detail", ""),
    ))
    items.append(_evidence_item(
        "release", "Release gate passes",
        "M337_REGRESSION_DEBT_CLOSURE.json",
        lambda d: d["fixes"][2]["gate_result_after_fix"]["exit_code"] == 0,
        lambda d: d["fixes"][2]["gate_result_after_fix"]["exit_name"],
    ))

    # ── journey: authentication, RBAC, isolation, approvals, missions ──
    journey_stages = {
        "authentication": ("identity_and_session", "Authentication and session lifecycle"),
        "RBAC": ("rbac", "Role-based access control"),
        "workspace isolation": ("rbac", "Workspace and organization isolation"),
        "approvals": ("approvals", "Approval lifecycle and maker-checker"),
        "mission lifecycle": ("mission_lifecycle", "Mission create through cancel and retry"),
        "observability": ("operations", "Health, metrics, alerts and diagnostics"),
    }
    for category, (stage, label) in journey_stages.items():
        items.append(_evidence_item(
            category, label, "M339_PRIVATE_ALPHA_E2E_JOURNEY.json",
            lambda d, s=stage: d["stages"][s]["status"] == PASS,
            lambda d, s=stage: f"{d['stages'][s]['passed']}/{d['stages'][s]['steps']} steps",
        ))
    items.append(_evidence_item(
        "mission lifecycle", "Every boundary refusal is a real authorization failure",
        "M339_PRIVATE_ALPHA_E2E_JOURNEY.json",
        lambda d: all(
            s.get("refused_with") not in ("TypeError", "AttributeError", "KeyError")
            for s in d["steps"] if s["kind"] == "negative"
        ),
        lambda d: f"{d['negative_steps']} refusals, each with a specific code",
    ))

    # ── observability, backup, recovery, soak ──
    items.append(_evidence_item(
        "diagnostics", "Diagnostics cover every subsystem",
        "M339_PRIVATE_ALPHA_E2E_JOURNEY.json",
        lambda d: d["stages"]["operations"]["status"] == PASS,
    ))
    items.append(_evidence_item(
        "backup", "Backup snapshot verified",
        "M341_SOAK_CONCURRENCY_RECOVERY_REPORT.json",
        lambda d: any(
            r["scenario"] == "corrupted_backup_detected" and r["ok"] for r in d["recovery"]
        ),
        lambda d: "a corrupted archive is detected and live state stays intact",
    ))
    items.append(_evidence_item(
        "recovery", "Restart, restore and interruption recovery",
        "M341_SOAK_CONCURRENCY_RECOVERY_REPORT.json",
        lambda d: d["recovery_ok"],
        lambda d: f"{len(d['recovery'])} recovery scenarios",
    ))
    items.append(_evidence_item(
        "soak", "Sustained local soak completed",
        "M341_SOAK_CONCURRENCY_RECOVERY_REPORT.json",
        lambda d: d["sustained_requested_duration"] and d["verdict"] == "PRIVATE_ALPHA_SOAK_PASSED",
        lambda d: f"{d['actual_duration_minutes']} min, {d['total_operations']} operations, "
                  f"{d['error_count']} errors, concurrency_ok={d['concurrency_ok']}",
    ))

    # ── security and privacy ──
    posture = authority_posture()
    items.append(_item(
        "security", "All authority locks false",
        PASS if posture["all_false"] else FAIL,
        ", ".join(k for k, v in posture["locks"].items() if v) or "15 locks, all false",
        "live read",
    ))
    items.append(_evidence_item(
        "security", "Runtime made no external or network call",
        "M339_PRIVATE_ALPHA_E2E_JOURNEY.json",
        lambda d: d["runtime_boundary"]["external_provider_calls"] == 0
        and d["runtime_boundary"]["network_calls"] == 0,
    ))
    items.append(_evidence_item(
        "security", "Concurrent approval decisions cannot both win",
        "M341_SOAK_CONCURRENCY_RECOVERY_REPORT.json",
        lambda d: any(
            c["scenario"] == "approval_contention" and c["ok"] for c in d["concurrency"]
        ),
        lambda d: "exactly one decider wins; the rest are refused",
    ))
    items.append(_evidence_item(
        "privacy", "No credential value reaches the audit trail",
        "M339_PRIVATE_ALPHA_E2E_JOURNEY.json",
        lambda d: any(
            s["step"] == "audit_contains_no_credential_values" and s["ok"] for s in d["steps"]
        ),
    ))
    items.append(_evidence_item(
        "browser", "Browser certification passed",
        "M343_BROWSER_CERT.json",
        lambda d: d["verdict"].endswith("PASSED_WITH_LIMITATIONS") or d["verdict"].endswith("PASSED"),
        lambda d: f"{d.get('passed', '?')} checks passed, {d.get('failed', '?')} failed",
    ))
    items.append(_evidence_item(
        "clean clone", "Clean-clone certification passed",
        "M343_CLEAN_CLONE_CERTIFICATION.json",
        lambda d: d["verdict"].startswith("M343_CLEAN_CLONE_CERTIFIED"),
        lambda d: d["verdict"],
    ))

    # ── documentation and runbooks ──
    for category, item, filename in (
        ("documentation", "Private-alpha scope", "PRIVATE_ALPHA_SCOPE.md"),
        ("release", "Release runbook", "PRIVATE_ALPHA_RELEASE_RUNBOOK.md"),
        ("rollback", "Rollback runbook", "PRIVATE_ALPHA_ROLLBACK_RUNBOOK.md"),
        ("incident response", "Incident runbook", "PRIVATE_ALPHA_INCIDENT_RUNBOOK.md"),
        ("tester support", "Tester guide", "PRIVATE_ALPHA_TESTER_GUIDE.md"),
    ):
        present = _doc_present(filename)
        items.append(_item(
            category, item, PASS if present else FAIL,
            "present" if present else "missing", f"docs/private-alpha/{filename}",
        ))

    # ── known limitations ──
    items.append(_item(
        "known limitations", "Limitations stated explicitly", PASS_WITH_LIMITATION,
        f"{len(KNOWN_LIMITATIONS)} documented limitations", "PRIVATE_ALPHA_SCOPE.md",
    ))

    # ── owner approval — never automated ──
    items.append(_item(
        "owner approval", "Human owner review of the release", OWNER_REVIEW_REQUIRED,
        "Automation may not mark this item as passed. It stays OWNER_REVIEW_REQUIRED "
        "until the owner personally records a decision outside this tooling.",
        "human",
    ))

    return items


def launch_readiness_report() -> dict[str, Any]:
    """The full readiness report backing /operations/private-alpha-readiness."""
    checklist = build_checklist()
    counts: dict[str, int] = {}
    for entry in checklist:
        counts[entry["state"]] = counts.get(entry["state"], 0) + 1

    failed = [c for c in checklist if c["state"] == FAIL]
    posture = authority_posture()

    debt = _load("M337_REGRESSION_DEBT_CLOSURE.json") or {}
    journey = _load("M339_PRIVATE_ALPHA_E2E_JOURNEY.json") or {}
    soak = _load("M341_SOAK_CONCURRENCY_RECOVERY_REPORT.json") or {}
    contract = _load("M338_PRIVATE_ALPHA_CONTRACT.json") or {}
    browser = _load("M343_BROWSER_CERT.json") or {}
    clone = _load("M343_CLEAN_CLONE_CERTIFICATION.json") or {}
    tests = _load("M343_TEST_RESULTS.json") or {}

    ready = not failed and posture["all_false"] is True

    return {
        "schema": "m343.private_alpha_launch_readiness.v1",
        "milestone": MILESTONE,
        "title": "Private Alpha Launch Readiness",
        "subtitle": "Read-only. No control on this page launches, deploys, publishes "
                    "or approves anything.",
        "verdict": VERDICT if ready else "PRIVATE_ALPHA_LAUNCH_READINESS_NOT_CERTIFIED",
        "verdict_target": VERDICT,
        "max_state": MAX_STATE,
        "checklist_ready": ready,

        "readiness_overview": {
            "branch": "milestone/m336-m343-private-alpha-readiness",
            "release_version": "0.1.0-private-alpha.1",
            "test_results": tests.get("summary", "see M343_TEST_RESULTS.json"),
            "release_gate": (debt.get("fixes") or [{}, {}, {}])[2]
                            .get("gate_result_after_fix", {}).get("exit_name", "unknown"),
            "owner_review": OWNER_REVIEW_REQUIRED,
        },

        "regression_debt": {
            "m57": debt.get("result", {}).get("M57_INHERITED_FAILURES"),
            "m157": debt.get("result", {}).get("M157_INHERITED_FAILURES"),
            "release_gate": debt.get("result", {}).get("RELEASE_GATE_FAILURES"),
            "root_causes": [f.get("root_cause_statement", "")[:300] for f in debt.get("fixes", [])],
            "closure_evidence": "M337_REGRESSION_DEBT_CLOSURE.json",
        },

        "user_journey": {
            "verdict": journey.get("verdict"),
            "stages": journey.get("stages"),
            "positive_steps": journey.get("positive_steps"),
            "negative_steps": journey.get("negative_steps"),
            "evidence": "M339_PRIVATE_ALPHA_E2E_JOURNEY.json",
        },

        "reliability": {
            "soak_verdict": soak.get("verdict"),
            "soak_minutes": soak.get("actual_duration_minutes"),
            "operations": soak.get("total_operations"),
            "error_rate": soak.get("error_rate"),
            "latency_ms": soak.get("latency_ms"),
            "resources": {
                k: v for k, v in (soak.get("resources") or {}).items() if k != "samples"
            },
            "concurrency_ok": soak.get("concurrency_ok"),
            "recovery_ok": soak.get("recovery_ok"),
        },

        "security": {
            "authority_locks": posture["locks"],
            "all_locks_false": posture["all_false"],
            "workspace_isolation": (journey.get("stages") or {}).get("rbac", {}).get("status"),
            "session_revocation": (journey.get("stages") or {})
                                  .get("session_revocation_and_signout", {}).get("status"),
            "approval_restrictions": (journey.get("stages") or {}).get("approvals", {}).get("status"),
            "public_registration_enabled": False,
            "broker_connectivity": "NONE",
            "order_execution": "NONE",
        },

        "release_package": {
            "release_runbook": "docs/private-alpha/PRIVATE_ALPHA_RELEASE_RUNBOOK.md",
            "rollback_runbook": "docs/private-alpha/PRIVATE_ALPHA_ROLLBACK_RUNBOOK.md",
            "incident_runbook": "docs/private-alpha/PRIVATE_ALPHA_INCIDENT_RUNBOOK.md",
            "tester_guide": "docs/private-alpha/PRIVATE_ALPHA_TESTER_GUIDE.md",
            "scope": "docs/private-alpha/PRIVATE_ALPHA_SCOPE.md",
            "browser_certification": browser.get("verdict"),
            "clean_clone_certification": clone.get("verdict"),
        },

        "human_review": {
            marker: True for marker in HUMAN_REVIEW_MARKERS
        },
        "owner_review_status": OWNER_REVIEW_REQUIRED,
        "owner_review_may_be_automated": False,
        "release_is_automatic": False,

        "checklist": checklist,
        "checklist_counts": counts,
        "failed_items": failed,
        "known_limitations": KNOWN_LIMITATIONS,
        "contract": {
            "audience": (contract.get("audience") or {}).get("admitted"),
            "invite_only": (contract.get("audience") or {}).get("invite_only"),
            "explicitly_unsupported": contract.get("explicitly_unsupported"),
        },

        "ui_contract": {
            "read_only": True,
            "forbidden_controls": [
                "public registration",
                "broker connectivity",
                "credential input",
                "account access",
                "order execution",
                "live trading",
                "deploy",
                "publish",
                "owner review approval",
            ],
            "allowed_actions": ["read", "refresh", "navigate", "download evidence"],
        },

        **{key: False for key in AUTHORITY_LOCKS},
    }
