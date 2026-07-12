"""M17.3 harness trust lifecycle + source pinning.

Trust advances only forward through the pipeline; promotion to APPROVED/TRUSTED
requires evidence (deterministic + security tests + license + exact source
commit) and is a HUMAN decision — an agent may discover but never self-promote.
Any source change resets trust. Terminal states (rejected/quarantined/revoked/
compromised) block execution.
"""
from __future__ import annotations

from saathi.application_harness.models import HarnessDefinition, TrustStatus

# allowed forward transitions (order of the lifecycle)
_ORDER = [
    TrustStatus.DISCOVERED, TrustStatus.METADATA_INSPECTED,
    TrustStatus.LICENSE_VERIFIED, TrustStatus.SOURCE_PINNED,
    TrustStatus.DEPENDENCY_SCANNED, TrustStatus.STATIC_SCANNED,
    TrustStatus.SANDBOX_INSTALLED, TrustStatus.DETERMINISTIC_TESTED,
    TrustStatus.APPLICATION_TESTED, TrustStatus.SECURITY_REVIEWED,
    TrustStatus.APPROVED, TrustStatus.TRUSTED,
]
_INDEX = {s: i for i, s in enumerate(_ORDER)}
_TERMINAL = {TrustStatus.REJECTED, TrustStatus.QUARANTINED, TrustStatus.DEPRECATED,
             TrustStatus.REVOKED, TrustStatus.INCOMPATIBLE, TrustStatus.COMPROMISED}


class TrustError(Exception):
    pass


def can_execute(defn: HarnessDefinition) -> tuple[bool, str]:
    st = TrustStatus(defn.trust_status)
    if st in _TERMINAL:
        return False, f"HARNESS_QUARANTINED:{st.value}"
    if st not in (TrustStatus.APPROVED, TrustStatus.TRUSTED):
        return False, f"HARNESS_NOT_APPROVED:{st.value}"
    # external harnesses MUST be source-pinned
    if defn.source_type != "local" and not defn.source_commit:
        return False, "HARNESS_SOURCE_CHANGED:missing source_commit"
    return True, "ok"


def advance(defn: HarnessDefinition, to: TrustStatus, *, actor: str,
            evidence: dict | None = None) -> HarnessDefinition:
    cur = TrustStatus(defn.trust_status)
    if cur in _TERMINAL:
        raise TrustError(f"cannot advance from terminal {cur.value}")
    if to in _TERMINAL:
        defn.trust_status = to.value      # quarantine/revoke always allowed
        return defn
    if to not in _INDEX or cur not in _INDEX:
        raise TrustError(f"unknown trust state {cur}->{to}")
    if _INDEX[to] <= _INDEX[cur]:
        raise TrustError("trust cannot move backward or stall")
    if _INDEX[to] - _INDEX[cur] != 1:
        raise TrustError("trust must advance one stage at a time (no skipping)")
    # promotion to APPROVED requires evidence + a human actor
    if to == TrustStatus.APPROVED:
        ev = evidence or {}
        if not (ev.get("deterministic_passed") and ev.get("security_passed")
                and ev.get("license_ok") and ev.get("source_commit")):
            raise TrustError("APPROVED requires deterministic+security+license+source evidence")
        if actor.startswith("agent"):
            raise TrustError("agents cannot promote a harness to APPROVED")
    defn.trust_status = to.value
    return defn


def revalidate_source(defn: HarnessDefinition, *, new_commit: str) -> HarnessDefinition:
    """A source change RESETS trust — a previously trusted harness is no longer
    trusted after its source moves."""
    if new_commit != defn.source_commit:
        defn.source_commit = new_commit
        defn.trust_status = TrustStatus.SOURCE_PINNED.value  # back to review
        defn.validation_status = "unverified"
    return defn


def quarantine(defn: HarnessDefinition, reason: str = "") -> HarnessDefinition:
    defn.trust_status = TrustStatus.QUARANTINED.value
    defn.validation_status = f"quarantined:{reason}"[:120]
    return defn
