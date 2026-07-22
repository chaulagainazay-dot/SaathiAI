"""Typed migration contract for InsForge governed write pilot (M18.4)."""
from __future__ import annotations

import hashlib
import json
import re
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class MigrationRisk(str, Enum):
    LOW = "low"
    ELEVATED = "elevated"
    PROHIBITED = "prohibited"


class PreflightStrength(str, Enum):
    LOCAL_POLICY_ONLY = "LOCAL_POLICY_ONLY"
    PROVIDER_VALIDATED = "PROVIDER_VALIDATED"
    TRANSACTION_ROLLBACK_VERIFIED = "TRANSACTION_ROLLBACK_VERIFIED"
    ISOLATED_ENVIRONMENT_VERIFIED = "ISOLATED_ENVIRONMENT_VERIFIED"


class ExecutionOutcome(str, Enum):
    APPLIED_AND_VERIFIED = "APPLIED_AND_VERIFIED"
    APPLIED_VERIFICATION_FAILED = "APPLIED_VERIFICATION_FAILED"
    NOT_APPLIED = "NOT_APPLIED"
    OUTCOME_UNKNOWN = "OUTCOME_UNKNOWN"
    DUPLICATE_ALREADY_APPLIED = "DUPLICATE_ALREADY_APPLIED"


# Structured ops only — no free SQL console
ALLOWED_OPS = frozenset({"create_table", "add_column", "create_index"})

# Identifier: simple SQL-safe names
_IDENT_RE = re.compile(r"^[a-z][a-z0-9_]{0,62}$")

ALLOWED_COL_TYPES = frozenset({
    "text", "integer", "bigint", "boolean", "real", "double precision",
    "timestamptz", "timestamp", "uuid", "jsonb", "date",
})

MAX_OPS = 8
MAX_BODY_CHARS = 12_000
MAX_COLUMNS = 32
MAX_INDEX_COLS = 8

# Approval levels map to SaathiOS ToolIntent
RISK_TO_APPROVAL = {
    MigrationRisk.LOW: "L3",
    MigrationRisk.ELEVATED: "L4",
    MigrationRisk.PROHIBITED: "L4",
}

RISK_TO_GATEWAY = {
    MigrationRisk.LOW: "HIGH",       # still write → high
    MigrationRisk.ELEVATED: "CRITICAL",
    MigrationRisk.PROHIBITED: "CRITICAL",
}


@dataclass
class ColumnSpec:
    name: str
    type: str = "text"
    nullable: bool = True
    primary_key: bool = False

    def canonical(self) -> dict:
        return {
            "name": self.name.lower(),
            "type": self.type.lower().strip(),
            "nullable": bool(self.nullable),
            "primary_key": bool(self.primary_key),
        }


@dataclass
class MigrationOp:
    op: str
    table: str
    columns: list[ColumnSpec] = field(default_factory=list)
    column: ColumnSpec | None = None
    index_name: str = ""
    index_columns: list[str] = field(default_factory=list)
    unique: bool = False

    def canonical(self) -> dict:
        d: dict[str, Any] = {
            "op": self.op,
            "table": self.table.lower(),
        }
        if self.op == "create_table":
            d["columns"] = [c.canonical() for c in self.columns]
        elif self.op == "add_column" and self.column:
            d["column"] = self.column.canonical()
        elif self.op == "create_index":
            d["index_name"] = self.index_name.lower()
            d["index_columns"] = [c.lower() for c in self.index_columns]
            d["unique"] = bool(self.unique)
        return d


@dataclass
class MigrationRequest:
    provider: str = "insforge"
    project_id: str = "pilot"
    environment: str = "dev"  # dev | staging only in pilot
    migration_name: str = ""
    version: str = "1"
    operations: list[MigrationOp] = field(default_factory=list)
    # optional raw body for fingerprint only after normalization from ops
    expected_preconditions: dict = field(default_factory=dict)
    expected_postconditions: dict = field(default_factory=dict)
    rollback_ops: list[dict] = field(default_factory=list)
    irreversible: bool = False
    requestor: str = "system"
    mission_id: str = ""
    run_id: str = ""
    idempotency_key: str = ""
    approval_id: str = ""
    max_duration_sec: float = 30.0
    metadata: dict = field(default_factory=dict)

    def canonical_dict(self) -> dict:
        """Security-relevant fields for fingerprint (stable key order)."""
        return {
            "provider": self.provider,
            "project_id": self.project_id,
            "environment": self.environment,
            "migration_name": self.migration_name,
            "version": str(self.version),
            "operations": [o.canonical() for o in self.operations],
            "expected_preconditions": _canon_json(self.expected_preconditions),
            "expected_postconditions": _canon_json(self.expected_postconditions),
            "rollback_ops": self.rollback_ops,
            "irreversible": bool(self.irreversible),
        }

    def fingerprint(self) -> str:
        payload = json.dumps(self.canonical_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def ensure_idempotency_key(self) -> str:
        if self.idempotency_key and len(self.idempotency_key) == 64:
            return self.idempotency_key
        self.idempotency_key = self.fingerprint()
        return self.idempotency_key


@dataclass
class MigrationPlan:
    ok: bool
    fingerprint: str
    risk: MigrationRisk
    approval_level: str
    operations: list[dict]
    affected_objects: list[str]
    reversible: bool
    rollback_ops: list[dict]
    denied_reason: str = ""
    warnings: list[str] = field(default_factory=list)
    requestor: str = ""
    environment: str = ""
    project_id: str = ""
    migration_name: str = ""
    provider: str = "insforge"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["risk"] = self.risk.value
        return d


@dataclass
class PreflightResult:
    ok: bool
    strength: PreflightStrength
    fingerprint: str
    risk: MigrationRisk
    approval_level: str
    provider_contacted: bool
    warnings: list[str] = field(default_factory=list)
    denied_reason: str = ""
    plan: dict = field(default_factory=dict)
    evidence_id: str = ""

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "strength": self.strength.value,
            "fingerprint": self.fingerprint,
            "risk": self.risk.value,
            "approval_level": self.approval_level,
            "provider_contacted": self.provider_contacted,
            "warnings": self.warnings,
            "denied_reason": self.denied_reason,
            "plan": self.plan,
            "evidence_id": self.evidence_id,
        }


@dataclass
class MigrationExecutionResult:
    ok: bool
    outcome: ExecutionOutcome
    fingerprint: str
    approval_id: str = ""
    execution_id: str = ""
    verified: bool = False
    verification_detail: str = ""
    rollback_guidance: dict = field(default_factory=dict)
    error_category: str = ""
    detail: str = ""
    duration_ms: float = 0.0
    evidence_id: str = ""
    duplicate: bool = False

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "outcome": self.outcome.value,
            "fingerprint": self.fingerprint,
            "approval_id": self.approval_id,
            "execution_id": self.execution_id,
            "verified": self.verified,
            "verification_detail": self.verification_detail[:300],
            "rollback_guidance": self.rollback_guidance,
            "error_category": self.error_category,
            "detail": self.detail[:300],
            "duration_ms": round(self.duration_ms, 2),
            "evidence_id": self.evidence_id,
            "duplicate": self.duplicate,
        }


def _canon_json(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): _canon_json(obj[k]) for k in sorted(obj.keys())}
    if isinstance(obj, list):
        return [_canon_json(x) for x in obj]
    return obj


def new_request_id() -> str:
    return uuid.uuid4().hex[:16]


def valid_ident(name: str) -> bool:
    return bool(name and _IDENT_RE.match(name.lower()))
