"""Core data model for the Auto-Repair Loop: incidents, evidence, enums, policy.

Everything downstream (classifier, policy engine, rollback, verify, history)
operates on these structures. Evidence is sanitized on ingest — raw captures
are redacted for secrets before they are ever stored.
"""
from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Optional

from saathi.repair.secrets_scan import redact


class RepairLevel(str, Enum):
    """Safety levels from the spec."""
    DIAGNOSE_ONLY = "diagnose_only"      # Level 0 — read only
    SAFE_LOCAL = "safe_local"            # Level 1 — edit + local commit
    APPROVAL_REQUIRED = "approval_required"  # Level 2 — wait for human
    PROHIBITED = "prohibited"            # Level 3 — never autonomous


class FailureCategory(str, Enum):
    IMPORT_ERROR = "IMPORT_ERROR"
    COLLECTION_ERROR = "COLLECTION_ERROR"
    TEST_FAILURE = "TEST_FAILURE"
    ASYNC_ERROR = "ASYNC_ERROR"
    ROUTING_ERROR = "ROUTING_ERROR"
    INTENT_ERROR = "INTENT_ERROR"
    CAPABILITY_NOT_REGISTERED = "CAPABILITY_NOT_REGISTERED"
    EXECUTION_BYPASS = "EXECUTION_BYPASS"
    CONNECTOR_AUTH_ERROR = "CONNECTOR_AUTH_ERROR"
    CONNECTOR_RUNTIME_ERROR = "CONNECTOR_RUNTIME_ERROR"
    TOOL_RESULT_NOT_GROUNDED = "TOOL_RESULT_NOT_GROUNDED"
    AGENT_HALLUCINATION = "AGENT_HALLUCINATION"
    API_CONTRACT_MISMATCH = "API_CONTRACT_MISMATCH"
    EVENT_BUS_ERROR = "EVENT_BUS_ERROR"
    DATABASE_ERROR = "DATABASE_ERROR"
    CONFIGURATION_ERROR = "CONFIGURATION_ERROR"
    DEPENDENCY_ERROR = "DEPENDENCY_ERROR"
    FRONTEND_BACKEND_MISMATCH = "FRONTEND_BACKEND_MISMATCH"
    SERVER_STARTUP_ERROR = "SERVER_STARTUP_ERROR"
    SECURITY_ERROR = "SECURITY_ERROR"
    UNKNOWN = "UNKNOWN"


class PolicyDecision(str, Enum):
    DIAGNOSE_ONLY = "DIAGNOSE_ONLY"
    AUTO_REPAIR_ALLOWED = "AUTO_REPAIR_ALLOWED"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    MANUAL_ONLY = "MANUAL_ONLY"


class RepairStatus(str, Enum):
    OPEN = "open"
    DIAGNOSED = "diagnosed"
    REPAIRED = "repaired"
    FAILED = "failed"
    MANUAL_REQUIRED = "manual_required"
    SECURITY_BLOCKED = "security_blocked"


@dataclass
class RepairEvidence:
    """Structured evidence — secrets redacted on assignment via `sanitize()`."""
    stack_trace: str = ""
    failed_tests: list[str] = field(default_factory=list)
    test_output_tail: str = ""
    logs_tail: str = ""
    api_response_body: str = ""
    affected_routes: list[str] = field(default_factory=list)
    request_id: str = ""
    intent_classification: str = ""
    selected_capability: str = ""
    execution_gateway_status: str = ""
    connector_status: str = ""
    evidence_id: str = ""
    git_branch: str = ""
    git_head: str = ""
    git_dirty_files: list[str] = field(default_factory=list)
    recent_commits: list[str] = field(default_factory=list)
    route_count: Optional[int] = None
    server_import_ok: Optional[bool] = None
    health_overall: str = ""
    # env presence flags only — never values, e.g. {"HF_TOKEN_PRESENT": True}
    env_presence: dict[str, bool] = field(default_factory=dict)
    execution_trace: list[str] = field(default_factory=list)

    def sanitize(self) -> "RepairEvidence":
        """Redact any secret-looking substrings from free-text fields."""
        for f in ("stack_trace", "test_output_tail", "logs_tail",
                  "api_response_body"):
            setattr(self, f, redact(getattr(self, f) or ""))
        return self


@dataclass
class PatchPlan:
    root_cause: str = ""
    files: list[str] = field(default_factory=list)
    intended_change: str = ""
    test_plan: list[str] = field(default_factory=list)
    risk: str = "low"
    rollback_method: str = ""
    forbidden_scope: list[str] = field(default_factory=list)
    strategy: str = ""   # name of the vetted repair strategy, if any


@dataclass
class RepairIncident:
    incident_id: str = field(default_factory=lambda: "inc_" + uuid.uuid4().hex[:12])
    source: str = "user_report"   # pytest|runtime|healthcheck|user_report|ci|scheduled
    timestamp: float = field(default_factory=time.time)
    command: str = ""
    expected_behavior: str = ""
    actual_behavior: str = ""
    exception_type: Optional[str] = None
    stack_trace: Optional[str] = None
    failed_tests: list[str] = field(default_factory=list)
    affected_routes: list[str] = field(default_factory=list)
    logs: list[str] = field(default_factory=list)
    severity: str = "medium"
    repair_level: RepairLevel = RepairLevel.DIAGNOSE_ONLY

    # populated by the pipeline
    category: FailureCategory = FailureCategory.UNKNOWN
    confidence: float = 0.0
    suspected_files: list[str] = field(default_factory=list)
    subsystem: str = ""
    policy: PolicyDecision = PolicyDecision.DIAGNOSE_ONLY
    status: RepairStatus = RepairStatus.OPEN
    evidence: RepairEvidence = field(default_factory=RepairEvidence)
    patch_plan: Optional[PatchPlan] = None
    rollback_ref: str = ""
    repair_commit: str = ""
    notes: str = ""

    def __post_init__(self):
        # Sanitize inbound free-text at construction — never keep raw secrets.
        if self.stack_trace:
            self.stack_trace = redact(self.stack_trace)
        self.logs = [redact(x) for x in self.logs]

    def fingerprint(self) -> str:
        """Stable identity for recurring failures (dedup + attempt limits).

        Based on category + normalized failing tests + exception type — not on
        the volatile incident_id or timestamp.
        """
        basis = "|".join([
            self.category.value,
            self.exception_type or "",
            ",".join(sorted(self.failed_tests)),
            ",".join(sorted(self.affected_routes)),
        ])
        return hashlib.sha1(basis.encode()).hexdigest()[:16]

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        # enums -> str
        for k in ("repair_level", "category", "policy", "status"):
            v = d.get(k)
            if hasattr(v, "value"):
                d[k] = v.value
            elif isinstance(v, str):
                d[k] = v
        return d
