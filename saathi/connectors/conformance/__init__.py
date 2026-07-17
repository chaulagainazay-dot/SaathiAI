"""M30 — Connector conformance, sandbox validation, and certification.

Determines whether a registered connector behaves according to its M29 manifest
and M25–M29 governance guarantees. Credential-free; no live SaaS.

Canonical path:

    registry → conformance specification → sandbox harness
    → check results → fingerprint → certification decision → runtime eligibility
"""
from __future__ import annotations

from saathi.connectors.conformance.models import (
    CONFORMANCE_SPEC_VERSION,
    CertificationResult,
    CertificationState,
    CheckCategory,
    CheckResult,
    CheckSeverity,
    CheckStatus,
    EligibilityDecision,
)
from saathi.connectors.conformance.assessor import assess_all, assess_connector, status_report
from saathi.connectors.conformance.drift import check_drift, verify_conformance
from saathi.connectors.conformance.eligibility import resolve_eligibility
from saathi.connectors.conformance.fingerprint import compute_certification_fingerprint
from saathi.connectors.conformance.store import (
    CertificationStore,
    get_certification_store,
    install_test_certification,
    reset_certification_store,
)

__all__ = [
    "CONFORMANCE_SPEC_VERSION",
    "CertificationResult",
    "CertificationState",
    "CertificationStore",
    "CheckCategory",
    "CheckResult",
    "CheckSeverity",
    "CheckStatus",
    "EligibilityDecision",
    "assess_all",
    "assess_connector",
    "check_drift",
    "compute_certification_fingerprint",
    "get_certification_store",
    "install_test_certification",
    "reset_certification_store",
    "resolve_eligibility",
    "status_report",
    "verify_conformance",
]
