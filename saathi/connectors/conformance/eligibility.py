"""M30 — Connector certification eligibility for ACTIVE/CANARY execution.

Distinct from platform production certification (M25 runtime_gate).
"""
from __future__ import annotations

from typing import Any, Optional

from saathi.connectors.conformance.fingerprint import compute_certification_fingerprint
from saathi.connectors.conformance.models import (
    CertificationState,
    EligibilityDecision,
    EXECUTABLE_CERT_STATES,
)
from saathi.connectors.conformance.store import CertificationStore, get_certification_store


def resolve_eligibility(
    connector_id: str,
    *,
    store: Optional[CertificationStore] = None,
    registry: Any = None,
    refresh_stale: bool = True,
    allow_fixture: bool = True,
) -> EligibilityDecision:
    """Decide whether connector behavioral certification permits ACTIVE/CANARY."""
    st = store or get_certification_store()
    rec = st.get(connector_id)

    # Optional test-store auto-fixture (only when store.auto_fixture is True)
    if (
        rec.state == CertificationState.UNASSESSED.value
        and getattr(st, "auto_fixture", False)
        and allow_fixture
        and registry is not None
    ):
        st.install_fixture_certification(connector_id, registry=registry)
        rec = st.get(connector_id)

    manifest = None
    if registry is not None:
        try:
            r = registry.get(connector_id)
            if r is not None:
                manifest = r.manifest
            else:
                try:
                    r = registry.resolve(connector_id)
                    manifest = r.manifest
                except Exception:
                    pass
        except Exception:
            pass

    current_fp = compute_certification_fingerprint(connector_id=connector_id, manifest=manifest)
    state = CertificationState(rec.state) if rec.state in CertificationState.__members__ else CertificationState.UNASSESSED

    # Drift → STALE
    if (
        refresh_stale
        and state in EXECUTABLE_CERT_STATES
        and rec.fingerprint
        and rec.fingerprint != current_fp
        and not rec.fixture  # fixture certs use same compute path; still check
    ):
        # Fixtures also recompute — if mismatch, mark stale unless fixture and auto
        if rec.fixture and rec.fingerprint != current_fp:
            # Re-install fixture fingerprint for test stability when surface changes mid-suite
            if getattr(st, "auto_fixture", False):
                st.install_fixture_certification(connector_id, registry=registry, state=rec.state)
                rec = st.get(connector_id)
                current_fp = rec.fingerprint
            else:
                st.mark_stale(connector_id, reason="fingerprint_mismatch")
                rec = st.get(connector_id)
                state = CertificationState.STALE
        elif not rec.fixture:
            st.mark_stale(connector_id, reason="fingerprint_mismatch")
            rec = st.get(connector_id)
            state = CertificationState.STALE

    # Re-read state after possible stale transition
    try:
        state = CertificationState(rec.state)
    except Exception:
        state = CertificationState.UNASSESSED

    fresh = bool(
        rec.fingerprint
        and rec.fingerprint == current_fp
        and state in EXECUTABLE_CERT_STATES
    )

    if state is CertificationState.REVOKED:
        return EligibilityDecision(
            False, connector_id, state.value,
            reason="connector_certification_revoked",
            fresh=False, fingerprint=rec.fingerprint, current_fingerprint=current_fp,
        )
    if state is CertificationState.FAILED:
        return EligibilityDecision(
            False, connector_id, state.value,
            reason="connector_certification_failed",
            fresh=False, fingerprint=rec.fingerprint, current_fingerprint=current_fp,
        )
    if state is CertificationState.ENVIRONMENT_BLOCKED:
        return EligibilityDecision(
            False, connector_id, state.value,
            reason="connector_certification_environment_blocked",
            fresh=False, fingerprint=rec.fingerprint, current_fingerprint=current_fp,
        )
    if state is CertificationState.STALE:
        return EligibilityDecision(
            False, connector_id, state.value,
            reason="connector_certification_stale",
            fresh=False, fingerprint=rec.fingerprint, current_fingerprint=current_fp,
        )
    if state is CertificationState.UNASSESSED:
        return EligibilityDecision(
            False, connector_id, state.value,
            reason="connector_certification_unassessed",
            fresh=False, fingerprint=rec.fingerprint, current_fingerprint=current_fp,
        )
    if state is CertificationState.ASSESSING:
        return EligibilityDecision(
            False, connector_id, state.value,
            reason="connector_certification_assessing",
            fresh=False, fingerprint=rec.fingerprint, current_fingerprint=current_fp,
        )
    if state in EXECUTABLE_CERT_STATES:
        if not fresh:
            return EligibilityDecision(
                False, connector_id, state.value,
                reason="connector_certification_stale",
                fresh=False, fingerprint=rec.fingerprint, current_fingerprint=current_fp,
            )
        return EligibilityDecision(
            True, connector_id, state.value,
            reason="ok",
            fresh=True, fingerprint=rec.fingerprint, current_fingerprint=current_fp,
        )
    return EligibilityDecision(
        False, connector_id, state.value,
        reason=f"connector_certification:{state.value}",
        fresh=False, fingerprint=rec.fingerprint, current_fingerprint=current_fp,
    )


def caller_cannot_override_certification(metadata: Optional[dict[str, Any]]) -> bool:
    """Return True if caller metadata tries to forge certification (must be rejected)."""
    if not metadata:
        return False
    for k in metadata:
        lk = str(k).lower()
        if lk in (
            "force_certified", "bypass_certification", "connector_certified",
            "skip_connector_cert", "certification_override",
        ):
            return True
    return False
