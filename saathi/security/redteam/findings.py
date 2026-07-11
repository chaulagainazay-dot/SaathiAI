"""M15.2 normalized security finding model + severity.

A finding separates DETERMINISTIC evidence (authoritative) from JUDGE assessment
(advisory). A vulnerability is CONFIRMED only when deterministic evidence proves
the boundary failed — a judge opinion alone never confirms or clears a finding.
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional

from saathi.security.redteam.config import redact_obj


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


RELEASE_BLOCKING = {Severity.CRITICAL, Severity.HIGH}


class FindingState(str, Enum):
    NEW = "new"
    CONFIRMED = "confirmed"
    FALSE_POSITIVE = "false_positive"
    ACCEPTED_RISK = "accepted_risk"
    IN_REMEDIATION = "in_remediation"
    RESOLVED = "resolved"
    REGRESSED = "regressed"
    BLOCKED = "blocked"
    ENVIRONMENT_BLOCKED = "environment_blocked"


class Evidence(str, Enum):
    """How a security claim was established (honesty labels)."""
    DETERMINISTIC = "deterministically_verified"
    ADVERSARIAL_MODEL = "adversarial_model_tested"
    CONFIRMED_VULN = "confirmed_vulnerability"
    SUSPECTED_VULN = "suspected_vulnerability"
    REMEDIATED = "remediated_and_regression_tested"
    ENVIRONMENT_BLOCKED = "environment_blocked"
    UNVERIFIED = "unverified"
    NOT_APPLICABLE = "not_applicable"


@dataclass
class Finding:
    attack_id: str
    requirement_id: str
    category: str
    target: str
    severity: str
    # deterministic result: did the boundary HOLD (safe) or FAIL (vulnerable)?
    boundary_held: bool
    deterministic_evidence: dict = field(default_factory=dict)
    judge_assessment: Optional[dict] = None       # advisory only
    expected_behavior: str = ""
    actual_behavior: str = ""
    component: str = ""
    state: str = FindingState.NEW.value
    evidence_class: str = Evidence.DETERMINISTIC.value
    regression_test: str = ""
    finding_id: str = ""
    first_seen: float = 0.0
    last_seen: float = 0.0

    def __post_init__(self):
        now = time.time()
        self.first_seen = self.first_seen or now
        self.last_seen = now
        # a boundary that HELD is not a vulnerability; state reflects that
        if self.boundary_held:
            self.state = FindingState.RESOLVED.value if False else FindingState.NEW.value
        self.finding_id = self.finding_id or self.fingerprint()

    def fingerprint(self) -> str:
        basis = f"{self.attack_id}|{self.requirement_id}|{self.target}|{self.component}"
        return "f_" + hashlib.sha256(basis.encode()).hexdigest()[:16]

    def is_confirmed_vuln(self) -> bool:
        return not self.boundary_held

    def to_dict(self) -> dict:
        d = asdict(self)
        # never let a secret leak into a stored/reported finding
        return redact_obj(d)


def summarize(findings: list[Finding]) -> dict:
    confirmed = [f for f in findings if f.is_confirmed_vuln()]
    by_sev: dict = {}
    for f in confirmed:
        by_sev[f.severity] = by_sev.get(f.severity, 0) + 1
    blocking = [f for f in confirmed if Severity(f.severity) in RELEASE_BLOCKING]
    return {
        "total_attacks": len(findings),
        "boundaries_held": sum(1 for f in findings if f.boundary_held),
        "confirmed_vulnerabilities": len(confirmed),
        "confirmed_by_severity": by_sev,
        "release_blocking": len(blocking),
        "release_blocking_ids": [f.finding_id for f in blocking],
    }
