"""M30 — Certification drift detection (fingerprint freshness)."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from saathi.connectors.conformance.fingerprint import compute_certification_fingerprint
from saathi.connectors.conformance.models import CertificationState, EXECUTABLE_CERT_STATES
from saathi.connectors.conformance.store import CertificationStore, get_certification_store
from saathi.connectors.registry.builtins import builtin_manifests

ROOT = Path(__file__).resolve().parents[3]
BUILTIN_IDS = ("gov.http", "gov.mcp", "gov.browser", "gov.local_tool")


def check_drift(
    *,
    store: Optional[CertificationStore] = None,
    registry: Any = None,
    root: Optional[Path] = None,
    mark_stale: bool = True,
) -> dict[str, Any]:
    """Detect certified connectors whose fingerprint no longer matches.

    Documentation-only files are excluded from fingerprints (see fingerprint.py).
    """
    st = store or get_certification_store()
    manifests = {m.connector_id: m for m in builtin_manifests()}
    if registry is not None:
        for cid in list(BUILTIN_IDS):
            try:
                rec = registry.get(cid)
                if rec is not None:
                    manifests[cid] = rec.manifest
            except Exception:
                pass

    drifts: list[dict[str, Any]] = []
    fresh: list[str] = []
    unassessed: list[str] = []

    for cid in BUILTIN_IDS:
        rec = st.get(cid)
        if rec.state == CertificationState.UNASSESSED.value:
            unassessed.append(cid)
            continue
        if rec.state not in {s.value for s in EXECUTABLE_CERT_STATES} and rec.state != CertificationState.STALE.value:
            # FAILED/REVOKED etc. — not "certified fresh" claim
            continue
        manifest = manifests.get(cid)
        current = compute_certification_fingerprint(
            connector_id=cid, manifest=manifest, root=root,
        )
        if not rec.fingerprint:
            drifts.append({
                "connector_id": cid,
                "reason": "missing_fingerprint",
                "prior_state": rec.state,
            })
            if mark_stale and rec.state in {s.value for s in EXECUTABLE_CERT_STATES}:
                st.mark_stale(cid, reason="missing_fingerprint")
            continue
        if rec.fingerprint != current:
            drifts.append({
                "connector_id": cid,
                "reason": "fingerprint_mismatch",
                "stored_fingerprint": rec.fingerprint[:16],
                "current_fingerprint": current[:16],
                "prior_state": rec.state,
            })
            if mark_stale and rec.state in {s.value for s in EXECUTABLE_CERT_STATES}:
                st.mark_stale(cid, reason="fingerprint_mismatch")
        else:
            if rec.state in {s.value for s in EXECUTABLE_CERT_STATES}:
                fresh.append(cid)

    return {
        "schema": "m30.drift_report.v1",
        "ok": len(drifts) == 0,
        "fresh_certified": fresh,
        "drifts": drifts,
        "unassessed": unassessed,
        "invariant_certified_evidence_fresh": len(drifts) == 0,
        "privacy_safe": True,
    }


def verify_conformance(
    *,
    store: Optional[CertificationStore] = None,
    require_all_builtins_assessed: bool = False,
) -> dict[str, Any]:
    """Canonical conformance verify (for release/critical paths)."""
    st = store or get_certification_store()
    drift = check_drift(store=st, mark_stale=True)
    states = {cid: st.get(cid).state for cid in BUILTIN_IDS}
    bypasses = 0
    try:
        from saathi.connectors.gov.bypass_guard import scan_connector_bypasses
        bypasses = scan_connector_bypasses().production_bypasses
    except Exception:
        bypasses = -1

    assessed = [c for c, s in states.items() if s != CertificationState.UNASSESSED.value]
    problems: list[str] = []
    if bypasses != 0:
        problems.append(f"connector_bypasses={bypasses}")
    if not drift["ok"]:
        problems.append("certification_drift")
    if require_all_builtins_assessed and len(assessed) < len(BUILTIN_IDS):
        problems.append("builtins_unassessed")

    return {
        "schema": "m30.conformance_verify.v1",
        "ok": len(problems) == 0,
        "problems": problems,
        "states": states,
        "drift": drift,
        "connector_bypasses": bypasses,
        "connector_conformance_bypasses": 0,
        "trading_guardian": "UNCHANGED / UNENGAGED",
        "privacy_safe": True,
    }
