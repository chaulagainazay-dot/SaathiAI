"""M30 — Connector conformance and certification models."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Optional


CONFORMANCE_SPEC_VERSION = "m30.conformance.v1"


class CheckCategory(str, Enum):
    MANIFEST = "MANIFEST"
    IDENTITY = "IDENTITY"
    CAPABILITIES = "CAPABILITIES"
    TRUST = "TRUST"
    POLICY = "POLICY"
    APPROVAL = "APPROVAL"
    ROLLOUT = "ROLLOUT"
    ADAPTER_CONTRACT = "ADAPTER_CONTRACT"
    INPUT_VALIDATION = "INPUT_VALIDATION"
    OUTPUT_VALIDATION = "OUTPUT_VALIDATION"
    TIMEOUT = "TIMEOUT"
    RETRY = "RETRY"
    RATE_LIMIT = "RATE_LIMIT"
    IDEMPOTENCY = "IDEMPOTENCY"
    HEALTH = "HEALTH"
    READINESS = "READINESS"
    DEPENDENCIES = "DEPENDENCIES"
    EVIDENCE = "EVIDENCE"
    REDACTION = "REDACTION"
    INCIDENTS = "INCIDENTS"
    FAILURE_RECOVERY = "FAILURE_RECOVERY"
    DIRECT_ACCESS = "DIRECT_ACCESS"
    SIDE_EFFECT_SAFETY = "SIDE_EFFECT_SAFETY"
    RESOURCE_SAFETY = "RESOURCE_SAFETY"


class CheckStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"
    SKIPPED = "SKIPPED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class CheckSeverity(str, Enum):
    CRITICAL = "CRITICAL"  # safety — must pass for any certification
    MANDATORY = "MANDATORY"  # required for CERTIFIED
    LIMITATION = "LIMITATION"  # non-critical; may yield CERTIFIED_WITH_LIMITATIONS
    INFORMATIONAL = "INFORMATIONAL"


class CertificationState(str, Enum):
    UNASSESSED = "UNASSESSED"
    ASSESSING = "ASSESSING"
    CERTIFIED = "CERTIFIED"
    CERTIFIED_WITH_LIMITATIONS = "CERTIFIED_WITH_LIMITATIONS"
    FAILED = "FAILED"
    ENVIRONMENT_BLOCKED = "ENVIRONMENT_BLOCKED"
    STALE = "STALE"
    REVOKED = "REVOKED"


# States that permit ACTIVE/CANARY execution (when fresh + production cert + policy)
EXECUTABLE_CERT_STATES = frozenset({
    CertificationState.CERTIFIED,
    CertificationState.CERTIFIED_WITH_LIMITATIONS,
})


@dataclass
class CheckResult:
    check_id: str
    connector_id: str
    category: str
    severity: str
    required: bool
    status: str
    safe_summary: str = ""
    evidence_refs: list[str] = field(default_factory=list)
    failure_code: str = ""
    duration_ms: float = 0.0
    step_count: int = 1

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def is_pass(self) -> bool:
        return self.status == CheckStatus.PASS.value

    @property
    def is_mandatory_failure(self) -> bool:
        if self.status in (CheckStatus.PASS.value, CheckStatus.SKIPPED.value, CheckStatus.NOT_APPLICABLE.value):
            return False
        if self.status == CheckStatus.BLOCKED.value:
            return self.required
        return self.required or self.severity in (
            CheckSeverity.CRITICAL.value,
            CheckSeverity.MANDATORY.value,
        )


@dataclass
class CertificationResult:
    schema: str = "m30.certification_result.v1"
    connector_id: str = ""
    state: str = CertificationState.UNASSESSED.value
    fingerprint: str = ""
    prior_fingerprint: str = ""
    spec_version: str = CONFORMANCE_SPEC_VERSION
    checks: list[CheckResult] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    failure_codes: list[str] = field(default_factory=list)
    assessed_at: str = ""
    lease_id: str = ""
    evidence_dir: str = ""
    privacy_safe: bool = True
    bypass: bool = False
    trading_guardian: str = "UNCHANGED / UNENGAGED"
    live_credentials_used: int = 0
    live_external_accounts: int = 0
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["checks"] = [c.to_dict() if isinstance(c, CheckResult) else c for c in self.checks]
        return d

    @property
    def mandatory_passed(self) -> bool:
        for c in self.checks:
            if isinstance(c, CheckResult) and c.is_mandatory_failure:
                return False
            if isinstance(c, dict) and c.get("required") and c.get("status") not in (
                "PASS", "SKIPPED", "NOT_APPLICABLE",
            ):
                return False
        return True


@dataclass
class CertificationRecord:
    """Persisted certification view for a connector."""

    connector_id: str
    state: str = CertificationState.UNASSESSED.value
    fingerprint: str = ""
    assessed_at: str = ""
    revoked_at: str = ""
    revoke_reason: str = ""
    limitations: list[str] = field(default_factory=list)
    failure_codes: list[str] = field(default_factory=list)
    evidence_dir: str = ""
    lease_id: str = ""
    lease_expires_at: float = 0.0
    fixture: bool = False  # True only for isolated test fixtures
    history: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CertificationRecord":
        return cls(
            connector_id=str(data.get("connector_id") or ""),
            state=str(data.get("state") or CertificationState.UNASSESSED.value),
            fingerprint=str(data.get("fingerprint") or ""),
            assessed_at=str(data.get("assessed_at") or ""),
            revoked_at=str(data.get("revoked_at") or ""),
            revoke_reason=str(data.get("revoke_reason") or ""),
            limitations=list(data.get("limitations") or []),
            failure_codes=list(data.get("failure_codes") or []),
            evidence_dir=str(data.get("evidence_dir") or ""),
            lease_id=str(data.get("lease_id") or ""),
            lease_expires_at=float(data.get("lease_expires_at") or 0.0),
            fixture=bool(data.get("fixture")),
            history=list(data.get("history") or []),
        )


@dataclass
class EligibilityDecision:
    """Whether a connector may enter ACTIVE/CANARY execution."""

    allowed: bool
    connector_id: str
    state: str
    reason: str = ""
    fresh: bool = False
    fingerprint: str = ""
    current_fingerprint: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
