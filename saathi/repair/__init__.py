"""SaathiOS Auto-Repair Loop — production-safe autonomous repair.

Detect -> collect evidence -> classify -> root cause -> rollback point ->
minimal repair -> focused tests -> regression -> verify runtime -> local commit
-> report. Never pushes, never fabricates success, never patches external-auth
as code, never exposes secrets.
"""
from saathi.repair.incident import (
    RepairIncident, RepairEvidence, PatchPlan,
    RepairLevel, FailureCategory, PolicyDecision, RepairStatus,
)
from saathi.repair.loop import AutoRepairLoop, RepairLimits, RepairOutcome
from saathi.repair.history import RepairHistory
from saathi.repair.grounding import (
    ExpectedBehavior, GroundingVerdict, expected_behavior, verify_grounding,
)

__all__ = [
    "RepairIncident", "RepairEvidence", "PatchPlan",
    "RepairLevel", "FailureCategory", "PolicyDecision", "RepairStatus",
    "AutoRepairLoop", "RepairLimits", "RepairOutcome", "RepairHistory",
    "ExpectedBehavior", "GroundingVerdict", "expected_behavior", "verify_grounding",
]
