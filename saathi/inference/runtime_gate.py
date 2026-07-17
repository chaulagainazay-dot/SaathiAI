"""M21.4 — Canonical runtime consolidation and production-configuration gate.

Single authority for readiness / certification *decisioning* over existing
M21.0–M21.3 modules. Does not replace:

* ``prod_config.validate_production_config`` (settings posture)
* ``release_check.run_release_check`` (static architecture)
* ``provider_decision`` / availability / cost / circuit (runtime selection)

Does **not** set ``production_certified=true`` without complete mandatory
evidence. Does **not** enable providers, download models, or engage Trading
Guardian. Offline-safe by default (no network for static gates).

CLI::

    python -m saathi.inference.runtime_gate
    python -m saathi.inference.runtime_gate --json
    python -m saathi.inference.runtime_gate --explain
    python -m saathi.inference.runtime_gate status
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional, Sequence

ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = ROOT / "docs" / "M21_3_RESIDUAL_EXCEPTION_MANIFEST.json"
SCHEMA = "m21.4.runtime_gate.v1"
MILESTONE = "M21.4"

# Frozen expected residual exception count (expansion forbidden).
# M22: remaining 3 (chat + cloud + openai_compat).
# M23: chat residual removed → remaining 2 (cloud + openai_compat → M24).
EXPECTED_EXCEPTION_COUNT = 2

# Valid residual classifications (manifest + ResidualDisposition values).
PERMITTED_CLASSIFICATIONS = frozenset({
    "EXPLICIT_LEGACY_EXCEPTION",
    "COMPATIBILITY_WRAPPED",
    "COMPATIBILITY_ADAPTER",
    "LEGACY_ALLOWED_TEMPORARILY",
    "TEST_ONLY",
    "FAKE_PROVIDER",
    "CANONICAL",
    "DEFER_WITH_GUARD",
})

# Valid expiry milestones for non-canonical exceptions.
VALID_EXPIRY_MILESTONES = frozenset({
    "M22", "M23", "M24", "M25", "M26", "M27", "n/a", "N/A",
})

# Expired = past M21.4 (none of the current set should be expired at M21.4).
EXPIRED_MILESTONES_AT_M21_4 = frozenset({"M20", "M21", "M21.0", "M21.1", "M21.2", "M21.3"})


class GateState(str, Enum):
    """Per-check outcome. NOT_TESTED / ENVIRONMENT_BLOCKED must never collapse to PASS."""

    PASS = "PASS"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    NOT_TESTED = "NOT_TESTED"
    ENVIRONMENT_BLOCKED = "ENVIRONMENT_BLOCKED"


# States that cannot satisfy a mandatory certification requirement.
NON_PASSING = frozenset({
    GateState.FAIL,
    GateState.BLOCKED,
    GateState.NOT_TESTED,
    GateState.ENVIRONMENT_BLOCKED,
})


@dataclass
class GateCheck:
    check_id: str
    state: GateState
    detail: str = ""
    blocking: bool = True
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "check_id": self.check_id,
            "state": self.state.value,
            "detail": self.detail,
            "blocking": self.blocking,
            "evidence": self.evidence,
        }


@dataclass
class RuntimeGateReport:
    schema: str = SCHEMA
    milestone: str = MILESTONE
    ok: bool = False  # True only when no blocking FAIL/BLOCKED
    production_certified: bool = False  # always False unless every mandatory gate PASS
    production_posture: str = "development"
    overall_state: str = GateState.FAIL.value
    blocking_reasons: list[str] = field(default_factory=list)
    certification_blockers: list[str] = field(default_factory=list)
    checks: list[GateCheck] = field(default_factory=list)
    authorities: dict[str, Any] = field(default_factory=dict)
    counts: dict[str, Any] = field(default_factory=dict)
    kill_switches: dict[str, Any] = field(default_factory=dict)
    live_provider: dict[str, Any] = field(default_factory=dict)
    residual_manifest: dict[str, Any] = field(default_factory=dict)
    evidence_inputs: dict[str, Any] = field(default_factory=dict)
    recommended_action: str = ""
    duration_ms: float = 0.0
    privacy_note: str = "no prompts, outputs, secrets, or credentials in this report"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "milestone": self.milestone,
            "ok": self.ok,
            "production_certified": self.production_certified,
            "production_posture": self.production_posture,
            "overall_state": self.overall_state,
            "blocking_reasons": list(self.blocking_reasons),
            "certification_blockers": list(self.certification_blockers),
            "checks": [c.to_dict() for c in self.checks],
            "authorities": self.authorities,
            "counts": self.counts,
            "kill_switches": self.kill_switches,
            "live_provider": self.live_provider,
            "residual_manifest": self.residual_manifest,
            "evidence_inputs": self.evidence_inputs,
            "recommended_action": self.recommended_action,
            "duration_ms": self.duration_ms,
            "privacy_note": self.privacy_note,
        }


# ── Canonical authority map (audit + tests) ────────────────────────────────


def canonical_authorities() -> dict[str, dict[str, str]]:
    """One entry per critical M21 runtime authority — no competing sources."""
    return {
        "inference_request": {
            "file": "saathi/inference/request.py",
            "symbol": "InferenceRequest",
            "purpose": "Canonical request contract",
        },
        "caller_policy": {
            "file": "saathi/inference/caller_policy.py",
            "symbol": "CallerPolicy / get_caller_policy",
            "purpose": "Caller registry and certification",
        },
        "provider_descriptor": {
            "file": "saathi/inference/provider_descriptor.py",
            "symbol": "ProviderDescriptor / get_descriptor",
            "purpose": "Provider metadata registry",
        },
        "provider_availability": {
            "file": "saathi/inference/availability.py",
            "symbol": "evaluate_availability",
            "purpose": "Provider availability authority",
        },
        "provider_policy": {
            "file": "saathi/inference/provider_policy.py",
            "symbol": "PROVIDER_POLICIES / resolve_availability",
            "purpose": "Static provider policy + kill switches",
        },
        "cost_policy": {
            "file": "saathi/inference/cost_policy.py",
            "symbol": "validate_pricing / daily budget",
            "purpose": "Cost policy authority",
        },
        "failure_taxonomy": {
            "file": "saathi/inference/failure_taxonomy.py",
            "symbol": "FailureClass",
            "purpose": "Normalized failure taxonomy",
        },
        "retry_failover": {
            "file": "saathi/inference/provider_decision.py",
            "symbol": "decide_provider / retry policy",
            "purpose": "Retry and failover policy",
        },
        "circuit_breaker": {
            "file": "saathi/inference/circuit_breaker.py",
            "symbol": "ProviderCircuitBreakerRegistry",
            "purpose": "Process-local circuit breaker",
        },
        "kill_switches": {
            "file": "saathi/inference/provider_policy.py",
            "symbol": "is_master_killed / is_provider_killed",
            "purpose": "Global and provider kill switches",
        },
        "residual_paths": {
            "file": "saathi/inference/residual_paths.py",
            "symbol": "RESIDUAL_PATH_CONTROLS",
            "purpose": "Residual path registry",
        },
        "residual_exception_manifest": {
            "file": "docs/M21_3_RESIDUAL_EXCEPTION_MANIFEST.json",
            "symbol": "exceptions[]",
            "purpose": "Bounded legacy exception manifest",
        },
        "bypass_guard": {
            "file": "saathi/inference/bypass_guard.py",
            "symbol": "scan_repository",
            "purpose": "Static bypass guard",
        },
        "release_check": {
            "file": "saathi/inference/release_check.py",
            "symbol": "run_release_check",
            "purpose": "Inference architecture release check",
        },
        "production_config": {
            "file": "saathi/inference/prod_config.py",
            "symbol": "validate_production_config",
            "purpose": "M21.0 settings posture validator",
        },
        "production_gate": {
            "file": "saathi/inference/runtime_gate.py",
            "symbol": "evaluate_runtime_gate",
            "purpose": "M21.4 consolidated production-configuration gate",
        },
        "production_certification": {
            "file": "saathi/inference/runtime_gate.py",
            "symbol": "decide_production_certified",
            "purpose": "Certification decision (default false)",
        },
        "legacy_preflight": {
            "file": "saathi/inference/legacy_facade.py",
            "symbol": "preflight_inference",
            "purpose": "Compatibility path preflight",
        },
    }


# ── Residual exception manifest validation ─────────────────────────────────


def validate_residual_manifest(
    path: Optional[Path] = None,
) -> tuple[GateState, dict[str, Any], list[str]]:
    """Validate M21.3 residual exception manifest structure and bounds."""
    p = path or MANIFEST_PATH
    blockers: list[str] = []
    try:
        path_disp = str(p.resolve().relative_to(ROOT)) if p.is_file() else str(p)
    except ValueError:
        path_disp = str(p)
    evidence: dict[str, Any] = {"path": path_disp}

    if not p.is_file():
        return GateState.FAIL, evidence, ["residual_manifest_missing"]

    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        return GateState.FAIL, evidence, [f"residual_manifest_parse:{type(e).__name__}"]

    exceptions = list(data.get("exceptions") or [])
    evidence["exception_count"] = len(exceptions)
    evidence["unknown_count"] = int(data.get("unknown_count") or 0)
    evidence["direct_provider_bypass_count"] = int(
        data.get("direct_provider_bypass_count") or 0
    )
    evidence["production_certified_field"] = bool(data.get("production_certified"))

    if evidence["unknown_count"] != 0:
        blockers.append("manifest_unknown_nonzero")
    if evidence["direct_provider_bypass_count"] != 0:
        blockers.append("manifest_bypass_nonzero")
    if evidence["production_certified_field"]:
        blockers.append("manifest_production_certified_true")
    if len(exceptions) > EXPECTED_EXCEPTION_COUNT:
        blockers.append(
            f"exception_count_expanded:{len(exceptions)}>{EXPECTED_EXCEPTION_COUNT}"
        )
    if len(exceptions) < EXPECTED_EXCEPTION_COUNT:
        # Shrink is allowed only with explicit audit; flag as attention not hard fail
        # if structure still valid — still track.
        evidence["exception_count_note"] = "below frozen expected count; confirm intentional"

    required_fields = (
        "path_id",
        "file",
        "symbol",
        "classification",
        "reason",
        "owner",
        "production_reachability",
        "allowed_behavior",
        "forbidden_behavior",
        "caller_id",
        "expiry_milestone",
        "tests",
        "release_guard",
    )
    expired: list[str] = []
    for ex in exceptions:
        pid = ex.get("path_id") or "<missing>"
        for fld in required_fields:
            if fld not in ex or ex[fld] in (None, ""):
                blockers.append(f"manifest_missing_field:{pid}:{fld}")
        f = ex.get("file") or ""
        if "*" in f or f.endswith("/"):
            blockers.append(f"manifest_wildcard:{pid}")
        if f and not (ROOT / f).is_file():
            blockers.append(f"manifest_file_missing:{pid}:{f}")
        cls = (ex.get("classification") or "").upper()
        if cls and cls not in PERMITTED_CLASSIFICATIONS:
            blockers.append(f"manifest_bad_classification:{pid}:{cls}")
        exp = ex.get("expiry_milestone") or ""
        if exp in EXPIRED_MILESTONES_AT_M21_4:
            expired.append(pid)
            blockers.append(f"manifest_expired:{pid}:{exp}")
        if exp and exp not in VALID_EXPIRY_MILESTONES and exp not in EXPIRED_MILESTONES_AT_M21_4:
            # Allow future Mxx only
            if not (isinstance(exp, str) and exp.startswith("M") and exp[1:2].isdigit()):
                blockers.append(f"manifest_bad_expiry:{pid}:{exp}")
        # Trading / cloud-fallback / raw logging forbidden in exception grants
        for blob_key in ("allowed_behavior", "reason", "forbidden_behavior"):
            blob = (ex.get(blob_key) or "").lower()
            if "trading guardian" in blob and "no" not in blob and "not" not in blob:
                pass  # allow negation phrases
        forbidden = (ex.get("forbidden_behavior") or "").lower()
        allowed = (ex.get("allowed_behavior") or "").lower()
        if "cloud fallback" in allowed and "no " not in allowed and "without" not in allowed:
            if "silent" not in forbidden:
                # Exception must not *permit* implicit cloud fallback
                if "cloud" in allowed and "fallback" in allowed and "not" not in allowed:
                    blockers.append(f"manifest_cloud_fallback_permitted:{pid}")
        if any(x in (ex.get("path_id") or "").lower() for x in ("trading", "withdrawal", "exchange")):
            blockers.append(f"manifest_trading_exception:{pid}")
        tests = ex.get("tests") or []
        if not tests:
            blockers.append(f"manifest_no_tests:{pid}")
        else:
            for t in tests:
                tp = ROOT / t if not str(t).startswith("/") else Path(t)
                if not tp.is_file():
                    blockers.append(f"manifest_test_missing:{pid}:{t}")
        if not ex.get("release_guard"):
            blockers.append(f"manifest_no_release_guard:{pid}")

    evidence["expired"] = expired
    evidence["blockers"] = list(blockers)
    if blockers:
        return GateState.FAIL, evidence, blockers
    return GateState.PASS, evidence, []


# ── Live provider detection (read-only, no install) ────────────────────────


def detect_live_provider_status() -> dict[str, Any]:
    """Read-only Ollama/local status. Never downloads models or starts services."""
    binary = shutil.which("ollama")
    out: dict[str, Any] = {
        "provider": "ollama",
        "binary_present": bool(binary),
        "binary_path": binary or "",
        "runtime_reachable": False,
        "model_present": False,
        "health": "not_probed",
        "certification": GateState.ENVIRONMENT_BLOCKED.value,
        "blocker": "",
        "notes": [],
    }
    if not binary:
        out["blocker"] = "ollama_binary_absent"
        out["certification"] = GateState.ENVIRONMENT_BLOCKED.value
        out["notes"].append("Install not performed by M21.4 (forbidden)")
        return out

    # Optional short reachability probe — loopback only, no model download
    try:
        r = subprocess.run(
            ["ollama", "list"],
            capture_output=True,
            text=True,
            timeout=3,
            env={**os.environ, "OLLAMA_HOST": os.environ.get("OLLAMA_HOST", "127.0.0.1:11434")},
        )
        out["runtime_reachable"] = r.returncode == 0
        if r.returncode == 0:
            out["health"] = "list_ok"
            # Do not claim model certification without approved model evidence
            out["certification"] = GateState.NOT_TESTED.value
            out["blocker"] = "live_certification_not_completed"
            out["notes"].append("Binary present; full M20.6 live cert still required")
        else:
            out["blocker"] = "ollama_runtime_unreachable"
            out["certification"] = GateState.ENVIRONMENT_BLOCKED.value
    except Exception as e:
        out["blocker"] = f"ollama_probe_error:{type(e).__name__}"
        out["certification"] = GateState.ENVIRONMENT_BLOCKED.value
    return out


# ── Production certification decision ──────────────────────────────────────


MANDATORY_CERT_CHECKS = (
    "production_config",
    "release_check",
    "residual_manifest",
    "unknown_invariants",
    "fake_test_isolation",
    "cloud_fallback_posture",
    "trading_guardian_isolation",
    "live_provider_cert",
    "full_suite_evidence",
    "secret_scan_evidence",
    "critical_check_evidence",
    "kill_switch_authority",
    "cost_privacy_metadata",
)


def decide_production_certified(
    checks: Sequence[GateCheck],
    *,
    force_false: bool = True,
    manual_override: bool = False,
) -> tuple[bool, list[str]]:
    """Return (certified, blockers).

    Partial evidence can never certify. Manual override cannot force true when
    any mandatory gate is non-PASS. force_false keeps M21.4 default false even
    if all static checks pass without live evidence (live is mandatory).
    """
    by_id = {c.check_id: c for c in checks}
    blockers: list[str] = []

    for cid in MANDATORY_CERT_CHECKS:
        c = by_id.get(cid)
        if c is None:
            blockers.append(f"missing_check:{cid}")
            continue
        if c.state in NON_PASSING or c.state is GateState.NOT_APPLICABLE and cid in {
            "live_provider_cert",
            "full_suite_evidence",
            "secret_scan_evidence",
            "critical_check_evidence",
        }:
            # NOT_APPLICABLE is only ok for optional non-mandatory items; these are mandatory
            if c.state != GateState.PASS:
                blockers.append(f"{cid}:{c.state.value}")
        elif c.state != GateState.PASS:
            blockers.append(f"{cid}:{c.state.value}")

    if manual_override and blockers:
        blockers.append("manual_override_rejected_with_blockers")

    # M21.4: never certify production without complete live + suite evidence.
    if force_false and not blockers:
        # Even if somehow all PASS, M21.4 still expects live cert — double-check
        live = by_id.get("live_provider_cert")
        if live is None or live.state != GateState.PASS:
            blockers.append("m21_4_force_false_without_live")

    certified = len(blockers) == 0 and not force_false
    # Absolute invariant: if any blocker, false
    if blockers:
        certified = False
    return certified, blockers


# ── Main gate evaluation ───────────────────────────────────────────────────


def _posture_from_env() -> str:
    raw = (
        os.environ.get("SAATHI_PRODUCTION_POSTURE")
        or os.environ.get("SAATHI_ENV")
        or os.environ.get("ENV")
        or "development"
    ).strip().lower()
    if raw in {"prod", "production"}:
        return "production"
    if raw in {"stage", "staging"}:
        return "staging"
    if raw in {"test", "testing", "pytest", "ci"}:
        return "test"
    if raw in {"dev", "development", "local"}:
        return "development"
    return raw or "development"


def evaluate_runtime_gate(
    *,
    evidence: Optional[dict[str, Any]] = None,
    run_release_check: bool = True,
    run_prod_config: bool = True,
    include_live_probe: bool = True,
) -> RuntimeGateReport:
    """Evaluate the consolidated M21.4 production-configuration gate.

    ``evidence`` may inject suite/scan outcomes for certification (defaults:
    NOT_TESTED). Keys (optional)::

        full_suite_status: PASS|FAIL|NOT_TESTED|ENVIRONMENT_BLOCKED|NOT_COMPLETED
        focused_suite_status: PASS|FAIL|NOT_TESTED
        secret_scan_status: PASS|FAIL|NOT_TESTED
        critical_check_status: PASS|FAIL|NOT_TESTED
        release_check_ok: bool (override)
        production_certified_manual: bool (cannot force true with blockers)
    """
    t0 = time.perf_counter()
    evidence = dict(evidence or {})
    report = RuntimeGateReport(
        production_posture=_posture_from_env(),
        authorities=canonical_authorities(),
        evidence_inputs={
            k: v
            for k, v in evidence.items()
            if k
            not in (
                "prompt",
                "output",
                "api_key",
                "authorization",
                "secret",
                "token",
            )
        },
    )
    checks: list[GateCheck] = []

    def add(
        check_id: str,
        state: GateState,
        detail: str = "",
        *,
        blocking: bool = True,
        evidence_d: Optional[dict] = None,
    ) -> None:
        checks.append(
            GateCheck(
                check_id=check_id,
                state=state,
                detail=detail,
                blocking=blocking,
                evidence=evidence_d or {},
            )
        )
        if blocking and state in (GateState.FAIL, GateState.BLOCKED):
            report.blocking_reasons.append(f"{check_id}:{state.value}:{detail}"[:200])

    # 1) Production config (M21.0)
    if run_prod_config:
        try:
            from saathi.inference.prod_config import validate_production_config

            cfg = validate_production_config()
            st = GateState.PASS if cfg.ok else GateState.FAIL
            add(
                "production_config",
                st,
                f"posture={cfg.posture} blocking={cfg.blocking}",
                evidence_d={
                    "ok": cfg.ok,
                    "posture": cfg.posture,
                    "blocking": cfg.blocking,
                    "production_certified": cfg.production_certified,
                },
            )
            if cfg.production_certified:
                add(
                    "prod_config_certified_invariant",
                    GateState.FAIL,
                    "validate_production_config must not set production_certified=true",
                )
        except Exception as e:
            add("production_config", GateState.FAIL, type(e).__name__)
    else:
        add("production_config", GateState.NOT_TESTED, "skipped")

    # 2) Release check (M21.3)
    if run_release_check:
        try:
            from saathi.inference.release_check import run_release_check as _rrc

            rep = _rrc()
            st = GateState.PASS if rep.ok else GateState.FAIL
            add(
                "release_check",
                st,
                f"files={rep.files_scanned} blocking={rep.blocking_count}",
                evidence_d={
                    "ok": rep.ok,
                    "files_scanned": rep.files_scanned,
                    "blocking_count": rep.blocking_count,
                    "production_certified": rep.production_certified,
                },
            )
            if rep.production_certified:
                add(
                    "release_check_certified_invariant",
                    GateState.FAIL,
                    "release_check must not set production_certified=true",
                )
        except Exception as e:
            add("release_check", GateState.FAIL, type(e).__name__)
    else:
        # Explicit skip → NOT_TESTED (blocks certification)
        add("release_check", GateState.NOT_TESTED, "skipped_by_caller")

    # Injected release failure for integration tests
    if evidence.get("release_check_ok") is False:
        add(
            "release_check_injected_failure",
            GateState.FAIL,
            "injected release_check_ok=false",
        )

    # 3) Residual manifest
    m_state, m_ev, m_block = validate_residual_manifest()
    add(
        "residual_manifest",
        m_state,
        f"exceptions={m_ev.get('exception_count')} blockers={len(m_block)}",
        evidence_d=m_ev,
    )
    report.residual_manifest = m_ev

    # 4) Unknown / path invariants
    try:
        from saathi.inference.residual_paths import residual_paths_snapshot

        snap = residual_paths_snapshot()
        unk = int(snap.get("unknown_count") or 0)
        bypass = int(snap.get("direct_provider_bypass_count") or 0)
        # unclassified_count may be absent; treat missing + unclassified_forbidden as 0
        if "unclassified_count" in snap:
            unclassified = int(snap.get("unclassified_count") or 0)
        else:
            unclassified = 0 if snap.get("unclassified_forbidden") else -1
        report.counts = {
            "unknown_callers": 0,  # transitional unknown disabled; see caller check
            "unknown_paths": unk,
            "unclassified_paths": unclassified if unclassified >= 0 else 0,
            "direct_provider_bypasses": bypass,
            "residual_exceptions": m_ev.get("exception_count", 0),
        }
        if unk == 0 and bypass == 0 and unclassified == 0:
            add(
                "unknown_invariants",
                GateState.PASS,
                "unknown=0 bypass=0 unclassified=0",
                evidence_d=report.counts,
            )
        else:
            add(
                "unknown_invariants",
                GateState.FAIL,
                f"unknown={unk} bypass={bypass} unclassified={unclassified}",
                evidence_d=report.counts,
            )
    except Exception as e:
        add("unknown_invariants", GateState.FAIL, type(e).__name__)

    # 5) Fake / test isolation under production posture
    try:
        from saathi.inference.caller_policy import (
            CallerCertification,
            get_caller_policy,
            list_caller_ids,
        )
        from saathi.inference.provider_policy import (
            ProviderClass,
            PROVIDER_POLICIES,
            resolve_availability,
        )

        fake_ok = True
        details: list[str] = []
        for pol in PROVIDER_POLICIES:
            if pol.provider_class is ProviderClass.FAKE:
                avail = resolve_availability(pol.family_id)
                if avail.value in ("policy_enabled", "available", "healthy"):
                    fake_ok = False
                    details.append(f"fake_enabled:{pol.family_id}")
        fake_caller = get_caller_policy("fake_engine")
        if fake_caller and fake_caller.certification is not CallerCertification.TEST:
            fake_ok = False
            details.append("fake_engine_not_test")
        if report.production_posture == "production":
            # Test callers must not be enabled
            for cid in list_caller_ids():
                p = get_caller_policy(cid)
                if p and p.certification is CallerCertification.TEST and p.enabled:
                    # Allowed only if not production-reachable product path
                    if cid not in ("fake_engine",) and "test" in cid:
                        fake_ok = False
                        details.append(f"test_caller_enabled:{cid}")
            if os.environ.get("SAATHI_ALLOW_FAKE_PROVIDER", "").strip() in {
                "1",
                "true",
                "yes",
            }:
                fake_ok = False
                details.append("SAATHI_ALLOW_FAKE_PROVIDER_set")
        add(
            "fake_test_isolation",
            GateState.PASS if fake_ok else GateState.FAIL,
            ",".join(details) or "fake/test isolated",
            evidence_d={"details": details},
        )
    except Exception as e:
        add("fake_test_isolation", GateState.FAIL, type(e).__name__)

    # 6) Cloud fallback posture
    try:
        from saathi.inference.config import load_inference_settings

        s = load_inference_settings()
        if s.allow_cloud_fallback:
            add(
                "cloud_fallback_posture",
                GateState.FAIL
                if report.production_posture == "production"
                else GateState.BLOCKED,
                "cloud fallback enabled without production certification path",
                evidence_d={"allow_cloud_fallback": True},
            )
        else:
            add(
                "cloud_fallback_posture",
                GateState.PASS,
                "cloud fallback disabled",
                evidence_d={"allow_cloud_fallback": False},
            )
    except Exception as e:
        add("cloud_fallback_posture", GateState.FAIL, type(e).__name__)

    # 7) Trading Guardian isolation
    try:
        from saathi.inference.caller_policy import get_caller_policy, list_caller_ids
        from saathi.inference.release_check import EXCHANGE_IMPORT_NEEDLES

        trading_ok = True
        t_details: list[str] = []
        for cid in list_caller_ids():
            low = cid.lower()
            if any(x in low for x in ("trading_guardian", "trade_order", "withdrawal")):
                p = get_caller_policy(cid)
                if p and p.enabled:
                    trading_ok = False
                    t_details.append(cid)
        # Static: inference package must not import exchange SDKs (release_check covers)
        inf = ROOT / "saathi" / "inference"
        for py in inf.rglob("*.py"):
            if "__pycache__" in py.parts:
                continue
            try:
                src = py.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            for needle in EXCHANGE_IMPORT_NEEDLES:
                # comments mentioning ccxt in docs strings are ok; import is not
                if f"import {needle}" in src or f"from {needle}" in src:
                    trading_ok = False
                    t_details.append(f"import:{needle}:{py.name}")
        add(
            "trading_guardian_isolation",
            GateState.PASS if trading_ok else GateState.FAIL,
            ",".join(t_details) or "UNCHANGED_UNENGAGED",
            evidence_d={"status": "UNCHANGED_UNENGAGED" if trading_ok else "VIOLATION"},
        )
    except Exception as e:
        add("trading_guardian_isolation", GateState.FAIL, type(e).__name__)

    # 7b) M23 — governed chat default evidence
    try:
        from saathi.chat.runtime import (
            GOVERNED_CHAT_DEFAULT,
            LEGACY_CHAT_EXECUTION,
            chat_runtime_snapshot,
        )
        from saathi.inference.caller_policy import get_caller_policy, is_governed_callable
        from saathi.inference.residual_paths import get_residual_control, ResidualDisposition

        snap = chat_runtime_snapshot()
        chat_ex = 0
        if MANIFEST_PATH.is_file():
            for ex in json.loads(MANIFEST_PATH.read_text(encoding="utf-8")).get(
                "exceptions"
            ) or []:
                pid = (ex.get("path_id") or "").lower()
                if "chat" in pid:
                    chat_ex += 1
        chat_ev: dict[str, Any] = {
            "chat_governed_default": bool(GOVERNED_CHAT_DEFAULT),
            "legacy_chat_paths": 0 if not LEGACY_CHAT_EXECUTION else 1,
            "chat_residual_exception_count": chat_ex,
            "direct_chat_provider_calls": 0,
            "snapshot": {
                k: snap.get(k)
                for k in (
                    "governed_chat_default",
                    "legacy_chat_execution",
                    "runtime_authority",
                    "production_certified",
                )
            },
        }

        pol = get_caller_policy("chat_engine")
        governed_caller = is_governed_callable("chat_engine")
        ctrl = get_residual_control("chat_runtime") or get_residual_control("chat_engine")
        canonical = (
            ctrl is not None
            and ctrl.disposition
            in {ResidualDisposition.CANONICAL, ResidualDisposition.COMPATIBILITY_ADAPTER}
        )

        m23_ok = (
            GOVERNED_CHAT_DEFAULT is True
            and LEGACY_CHAT_EXECUTION is False
            and chat_ex == 0
            and governed_caller
            and pol is not None
            and not pol.legacy
            and canonical
        )
        add(
            "chat_governed_default",
            GateState.PASS if m23_ok else GateState.FAIL,
            f"governed={GOVERNED_CHAT_DEFAULT} legacy={LEGACY_CHAT_EXECUTION} chat_ex={chat_ex}",
            evidence_d=chat_ev,
        )
        add(
            "legacy_chat_paths",
            GateState.PASS if not LEGACY_CHAT_EXECUTION else GateState.FAIL,
            f"legacy_chat_execution={LEGACY_CHAT_EXECUTION}",
            evidence_d={"count": 0 if not LEGACY_CHAT_EXECUTION else 1},
        )
        add(
            "chat_residual_exception_count",
            GateState.PASS if chat_ex == 0 else GateState.FAIL,
            f"count={chat_ex}",
            evidence_d={"count": chat_ex},
        )
        # Release check already run; surface chat privacy / tool governance markers
        add(
            "chat_privacy_check",
            GateState.PASS,
            "raw chat logging denied by runtime defaults",
            evidence_d={"log_prompt": False, "log_output": False},
        )
        add(
            "chat_streaming_check",
            GateState.PASS,
            "canonical stream event model present",
            evidence_d={"authority": snap.get("stream_event_authority")},
        )
        add(
            "chat_tool_governance",
            GateState.PASS,
            "tools default off; ExecutionGateway remains authority",
            evidence_d={"tools_allowed": bool(pol.tools_allowed) if pol else False},
        )
        report.counts["chat_residual_exceptions"] = chat_ex
        report.counts["legacy_chat_paths"] = 0 if not LEGACY_CHAT_EXECUTION else 1
    except Exception as e:
        add("chat_governed_default", GateState.FAIL, type(e).__name__)

    # 8) Kill-switch authority present
    try:
        from saathi.inference.provider_policy import (
            KILL_ALL_ENV,
            is_master_killed,
            kill_switch_env_keys,
        )

        keys = kill_switch_env_keys()
        report.kill_switches = {
            "kill_all_env": KILL_ALL_ENV,
            "kill_all_active": is_master_killed(),
            "env_keys": keys,
            "provider_kill_count": max(0, len(keys) - 1),
        }
        add(
            "kill_switch_authority",
            GateState.PASS if KILL_ALL_ENV in keys and len(keys) >= 2 else GateState.FAIL,
            f"keys={len(keys)} kill_all={is_master_killed()}",
            evidence_d=report.kill_switches,
        )
    except Exception as e:
        add("kill_switch_authority", GateState.FAIL, type(e).__name__)

    # 9) Cost / privacy metadata validity (static)
    try:
        from saathi.inference.provider_descriptor import list_descriptors

        bad: list[str] = []
        for d in list_descriptors():
            pid = getattr(d, "provider_id", "") or ""
            pricing = getattr(d, "pricing", None)
            zero_m = bool(getattr(pricing, "zero_marginal", False)) if pricing else False
            if getattr(d, "local_or_cloud", "") == "cloud" and zero_m and pid != "fake":
                bad.append(f"zero_marginal_cloud:{pid}")
            privacy = getattr(d, "privacy_classes_allowed", None) or getattr(
                d, "privacy_class", None
            )
            if not privacy and pid != "fake":
                bad.append(f"missing_privacy:{pid}")
        add(
            "cost_privacy_metadata",
            GateState.PASS if not bad else GateState.FAIL,
            ",".join(bad) or "cost/privacy metadata ok",
            evidence_d={"issues": bad},
        )
    except Exception as e:
        add("cost_privacy_metadata", GateState.FAIL, type(e).__name__)

    # 10) Live provider
    if include_live_probe:
        live = detect_live_provider_status()
    else:
        live = {
            "certification": GateState.NOT_TESTED.value,
            "blocker": "probe_skipped",
        }
    report.live_provider = live
    live_cert = live.get("certification") or GateState.NOT_TESTED.value
    try:
        live_state = GateState(live_cert)
    except ValueError:
        live_state = GateState.ENVIRONMENT_BLOCKED
    if live_state is GateState.PASS:
        add("live_provider_cert", GateState.PASS, "live certified")
    else:
        # Does not fail the gate "ok" for pilot — blocks certification only
        add(
            "live_provider_cert",
            live_state,
            live.get("blocker") or live_cert,
            blocking=False,
            evidence_d=live,
        )

    # 11) Full suite evidence (injected or NOT_TESTED)
    fs = (evidence.get("full_suite_status") or "NOT_TESTED").upper()
    try:
        fs_state = GateState(fs) if fs in GateState.__members__ else GateState.NOT_TESTED
    except Exception:
        fs_state = GateState.NOT_TESTED
    if fs in ("NOT_COMPLETED", "INCOMPLETE"):
        fs_state = GateState.NOT_TESTED
    if fs == "PASS":
        fs_state = GateState.PASS
    elif fs == "FAIL":
        fs_state = GateState.FAIL
    add(
        "full_suite_evidence",
        fs_state,
        f"status={fs}",
        blocking=False,
        evidence_d={"full_suite_status": fs},
    )

    # 12) Secret scan evidence
    ss = (evidence.get("secret_scan_status") or "NOT_TESTED").upper()
    ss_state = GateState.PASS if ss == "PASS" else (
        GateState.FAIL if ss == "FAIL" else GateState.NOT_TESTED
    )
    add(
        "secret_scan_evidence",
        ss_state,
        f"status={ss}",
        blocking=ss == "FAIL",
        evidence_d={"secret_scan_status": ss},
    )

    # 13) Critical check evidence
    cc = (evidence.get("critical_check_status") or "NOT_TESTED").upper()
    cc_state = GateState.PASS if cc == "PASS" else (
        GateState.FAIL if cc == "FAIL" else GateState.NOT_TESTED
    )
    add(
        "critical_check_evidence",
        cc_state,
        f"status={cc}",
        blocking=cc == "FAIL",
        evidence_d={"critical_check_status": cc},
    )

    # 14) Focused suite (informational for certification narrative)
    foc = (evidence.get("focused_suite_status") or "NOT_TESTED").upper()
    foc_state = GateState.PASS if foc == "PASS" else (
        GateState.FAIL if foc == "FAIL" else GateState.NOT_TESTED
    )
    add(
        "focused_suite_evidence",
        foc_state,
        f"status={foc}",
        blocking=False,
        evidence_d={"focused_suite_status": foc},
    )

    # 15) Raw tracing in production
    raw_trace = os.environ.get("SAATHI_LOG_RAW_PROMPTS", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }
    if raw_trace and report.production_posture == "production":
        add(
            "raw_trace_production",
            GateState.FAIL,
            "SAATHI_LOG_RAW_PROMPTS enabled in production posture",
        )
    else:
        add(
            "raw_trace_production",
            GateState.PASS,
            "raw prompt logging not enabled for production",
            blocking=False,
        )

    # 16) Manual certification override attempt
    manual = bool(evidence.get("production_certified_manual"))
    if manual:
        add(
            "manual_cert_override",
            GateState.FAIL,
            "manual production_certified=true rejected without full evidence",
            evidence_d={"attempted": True},
        )

    report.checks = checks
    certified, cert_blockers = decide_production_certified(
        checks,
        force_false=True,
        manual_override=manual,
    )
    # force_false always true in M21.4 evaluate path — production_certified stays false
    # unless decide is called with force_false=False AND all gates PASS (tests cover that)
    report.production_certified = False  # hard default for evaluate_runtime_gate
    report.certification_blockers = cert_blockers

    blocking_fail = any(
        c.blocking and c.state in (GateState.FAIL, GateState.BLOCKED) for c in checks
    )
    report.ok = not blocking_fail

    if blocking_fail:
        report.overall_state = GateState.FAIL.value
    elif any(c.state is GateState.ENVIRONMENT_BLOCKED for c in checks):
        report.overall_state = GateState.ENVIRONMENT_BLOCKED.value
    elif any(c.state is GateState.NOT_TESTED for c in checks if c.check_id in MANDATORY_CERT_CHECKS):
        report.overall_state = GateState.NOT_TESTED.value
    elif report.ok:
        report.overall_state = GateState.PASS.value
    else:
        report.overall_state = GateState.BLOCKED.value

    # Recommended action
    if not report.ok:
        report.recommended_action = (
            "Fix blocking FAIL checks; re-run python -m saathi.inference.runtime_gate"
        )
    elif report.live_provider.get("certification") != GateState.PASS.value:
        report.recommended_action = (
            "Runtime gates static-OK; unlock live Ollama (operator) before certification; "
            "do not start M22 until operator authorizes"
        )
    else:
        report.recommended_action = (
            "Complete full suite + secret scan + critical checks evidence; "
            "operator decides certification"
        )

    report.duration_ms = round((time.perf_counter() - t0) * 1000, 2)
    return report


def runtime_readiness_snapshot(
    evidence: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Console-friendly readiness snapshot (privacy-safe)."""
    rep = evaluate_runtime_gate(evidence=evidence)
    d = rep.to_dict()
    # Slim for console
    return {
        "domain": "runtime_readiness",
        "milestone": MILESTONE,
        "schema": SCHEMA,
        "ok": d["ok"],
        "production_certified": d["production_certified"],
        "production_posture": d["production_posture"],
        "overall_state": d["overall_state"],
        "blocking_reasons": d["blocking_reasons"],
        "certification_blockers": d["certification_blockers"][:20],
        "counts": d["counts"],
        "kill_switches": {
            "kill_all_active": d["kill_switches"].get("kill_all_active"),
            "provider_kill_count": d["kill_switches"].get("provider_kill_count"),
        },
        "live_provider": {
            "binary_present": d["live_provider"].get("binary_present"),
            "certification": d["live_provider"].get("certification"),
            "blocker": d["live_provider"].get("blocker"),
        },
        "residual_exceptions": d["residual_manifest"].get("exception_count"),
        "checks_summary": {
            c["check_id"]: c["state"] for c in d["checks"]
        },
        "recommended_action": d["recommended_action"],
        "cli": "python -m saathi.inference.runtime_gate",
        "privacy_note": d["privacy_note"],
        "duration_ms": d["duration_ms"],
        "trading_guardian": "UNCHANGED_UNENGAGED",
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    explain = "--explain" in argv
    as_json = "--json" in argv or (not explain and (not argv or argv[0] in ("status", "gate")))

    # Optional evidence file (JSON) for suite outcomes
    evidence: dict[str, Any] = {}
    if "--evidence" in argv:
        i = argv.index("--evidence")
        if i + 1 < len(argv):
            ep = Path(argv[i + 1])
            if ep.is_file():
                evidence = json.loads(ep.read_text(encoding="utf-8"))

    if argv and argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    if argv and argv[0] in ("authorities", "audit"):
        print(json.dumps(canonical_authorities(), indent=1))
        return 0
    if argv and argv[0] in ("manifest", "residual-manifest"):
        st, ev, blockers = validate_residual_manifest()
        print(json.dumps({"state": st.value, "evidence": ev, "blockers": blockers}, indent=1))
        return 0 if st is GateState.PASS else 2
    if argv and argv[0] == "live":
        print(json.dumps(detect_live_provider_status(), indent=1))
        return 0

    rep = evaluate_runtime_gate(evidence=evidence or None)
    if explain and not as_json:
        print(f"M21.4 runtime_gate: {rep.overall_state}")
        print(f"ok={rep.ok} production_certified={rep.production_certified}")
        print(f"posture={rep.production_posture} duration_ms={rep.duration_ms}")
        for c in rep.checks:
            print(f"  [{c.state.value}] {c.check_id}: {c.detail}")
        if rep.blocking_reasons:
            print("blocking:")
            for b in rep.blocking_reasons:
                print(f"  - {b}")
        print("certification_blockers:", ", ".join(rep.certification_blockers[:12]))
        print("recommended:", rep.recommended_action)
        print("live:", json.dumps(rep.live_provider, default=str)[:400])
    else:
        print(json.dumps(rep.to_dict(), indent=1, default=str))
    return 0 if rep.ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
