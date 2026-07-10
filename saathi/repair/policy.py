"""Repair policy engine — decides whether an incident may be auto-repaired.

Maps FailureCategory + confidence + attempt history to one of:
DIAGNOSE_ONLY / AUTO_REPAIR_ALLOWED / APPROVAL_REQUIRED / MANUAL_ONLY.

Hard rule: connector-auth failures and dependency changes are never
auto-repaired as code. External auth is a human/setup action, not a code bug.
"""
from __future__ import annotations

from saathi.repair.incident import (
    RepairIncident, FailureCategory, PolicyDecision,
)

MIN_CONFIDENCE = 0.6

_AUTO_CATEGORIES = {
    FailureCategory.IMPORT_ERROR,
    FailureCategory.COLLECTION_ERROR,
    FailureCategory.ASYNC_ERROR,
    FailureCategory.EVENT_BUS_ERROR,
}

_APPROVAL_CATEGORIES = {
    FailureCategory.API_CONTRACT_MISMATCH,   # may change a public contract
    FailureCategory.DATABASE_ERROR,          # may touch migrations
    FailureCategory.CONFIGURATION_ERROR,
    FailureCategory.CAPABILITY_NOT_REGISTERED,
    FailureCategory.EXECUTION_BYPASS,        # wiring a side-effect path
    FailureCategory.INTENT_ERROR,
    FailureCategory.ROUTING_ERROR,
}

_MANUAL_CATEGORIES = {
    FailureCategory.CONNECTOR_AUTH_ERROR,    # external credential / OAuth
    FailureCategory.DEPENDENCY_ERROR,        # dependency upgrade
    FailureCategory.SECURITY_ERROR,
}


def decide(inc: RepairIncident, *, prior_attempts: int = 0,
           max_attempts: int = 2) -> PolicyDecision:
    # Attempt-limit escalation — never loop forever on one fingerprint.
    if prior_attempts >= max_attempts:
        return PolicyDecision.MANUAL_ONLY

    if inc.category in _MANUAL_CATEGORIES:
        return PolicyDecision.MANUAL_ONLY

    if inc.category in _APPROVAL_CATEGORIES:
        return PolicyDecision.APPROVAL_REQUIRED

    if inc.category in _AUTO_CATEGORIES and inc.confidence >= MIN_CONFIDENCE:
        # only if a vetted strategy exists for it
        from saathi.repair.strategies import has_strategy
        if has_strategy(inc.category):
            return PolicyDecision.AUTO_REPAIR_ALLOWED
        return PolicyDecision.DIAGNOSE_ONLY

    return PolicyDecision.DIAGNOSE_ONLY
