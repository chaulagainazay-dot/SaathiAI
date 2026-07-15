"""M17.22 durable ExecutionRecord — one record per governed execution.

Never log secrets. result_summary is always redacted / bounded.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from saathi.execution.execution_state import ExecutionState
from saathi.execution.toolintent import ToolIntent, _redact_secrets

_SECRET_RE = re.compile(
    r"(?i)(token|secret|password|api[_-]?key|bearer|authorization)\s*[=:]\s*\S+"
)


def tool_intent_digest(intent: ToolIntent) -> str:
    """Stable digest of ToolIntent *action* content for approval + idempotency.

    Excludes intent_id, timestamps, and approval *state* flags so the same
    external action shares one digest whether it is still awaiting approval or
    already pre-resolved. Changing actor/target/params/risk invalidates
    prior approval for that digest.
    """
    meta = intent.metadata or {}
    payload = {
        "actor_id": intent.actor_id,
        "actor_type": getattr(intent.actor_type, "value", intent.actor_type),
        "business_unit": getattr(intent.business_unit, "value", intent.business_unit),
        "capability": intent.capability,
        "connector_id": intent.connector_id,
        "operation": intent.operation,
        "parameters": intent.parameters,
        "risk_level": getattr(intent.risk_level, "value", intent.risk_level),
        "mission_id": intent.mission_id or "",
        "target": meta.get("target", ""),
        "account_id": meta.get("account_id", ""),
        "environment": meta.get("environment", ""),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


def safe_summary(text: Any, *, maxlen: int = 240) -> str:
    """Bounded, secret-free summary for durable storage / observability."""
    if text is None:
        return ""
    if isinstance(text, dict):
        text = json.dumps(_redact_secrets(text), sort_keys=True, default=str)
    s = str(text)
    s = _SECRET_RE.sub(r"\1=[redacted]", s)
    if len(s) > maxlen:
        s = s[: maxlen - 3] + "..."
    return s


@dataclass
class ExecutionRecord:
    """One durable execution through the universal gateway."""

    execution_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    tool_intent_digest: str = ""
    intent_id: str = ""
    actor: str = ""
    target: str = ""  # e.g. connector:git.local:status / local:echo / mcp:server.tool
    family: str = "connector"  # connector | cli | local | mcp
    created: float = field(default_factory=time.time)
    started: Optional[float] = None
    finished: Optional[float] = None
    status: str = ExecutionState.REQUESTED.value
    approval: str = "none"  # none | automatic | required | approved | rejected | expired
    risk: str = "medium"
    evidence_id: str = ""
    result_summary: str = ""
    failure_category: str = ""
    retry_count: int = 0
    retryable: bool = False
    next_retry_at: Optional[float] = None
    ledger_run_id: str = ""
    security_event_id: str = ""
    approval_id: str = ""
    idempotency_key: str = ""
    correlation_id: str = ""
    transition_log: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def runtime_sec(self) -> Optional[float]:
        if self.started is None:
            return None
        end = self.finished if self.finished is not None else time.time()
        return max(0.0, end - self.started)

    def to_safe_dict(self) -> dict:
        """Owner-safe projection — never includes parameters/secrets."""
        return {
            "execution_id": self.execution_id,
            "tool_intent_digest": self.tool_intent_digest,
            "intent_id": self.intent_id,
            "actor": self.actor,
            "target": self.target,
            "family": self.family,
            "created": self.created,
            "started": self.started,
            "finished": self.finished,
            "status": self.status,
            "approval": self.approval,
            "risk": self.risk,
            "evidence_id": self.evidence_id,
            "result_summary": safe_summary(self.result_summary),
            "failure_category": self.failure_category,
            "retry_count": self.retry_count,
            "retryable": self.retryable,
            "next_retry_at": self.next_retry_at,
            "ledger_run_id": self.ledger_run_id,
            "security_event_id": self.security_event_id,
            "approval_id": self.approval_id,
            "idempotency_key": self.idempotency_key[:16] + "…" if self.idempotency_key else "",
            "correlation_id": self.correlation_id,
            "runtime_sec": self.runtime_sec(),
            "transition_count": len(self.transition_log or []),
        }

    def to_row_payload(self) -> dict:
        d = asdict(self)
        d["result_summary"] = safe_summary(d.get("result_summary"))
        # Never persist raw secret-bearing metadata keys
        d["metadata"] = _redact_secrets(d.get("metadata") or {})
        return d

    @staticmethod
    def from_row(row: dict) -> "ExecutionRecord":
        log = row.get("transition_log") or []
        if isinstance(log, str):
            try:
                log = json.loads(log)
            except Exception:
                log = []
        meta = row.get("metadata") or {}
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except Exception:
                meta = {}
        return ExecutionRecord(
            execution_id=row.get("execution_id", ""),
            tool_intent_digest=row.get("tool_intent_digest", ""),
            intent_id=row.get("intent_id", ""),
            actor=row.get("actor", ""),
            target=row.get("target", ""),
            family=row.get("family", "connector"),
            created=float(row.get("created") or 0),
            started=row.get("started"),
            finished=row.get("finished"),
            status=row.get("status", ExecutionState.REQUESTED.value),
            approval=row.get("approval", "none"),
            risk=row.get("risk", "medium"),
            evidence_id=row.get("evidence_id", "") or "",
            result_summary=row.get("result_summary", "") or "",
            failure_category=row.get("failure_category", "") or "",
            retry_count=int(row.get("retry_count") or 0),
            retryable=bool(row.get("retryable") or False),
            next_retry_at=row.get("next_retry_at"),
            ledger_run_id=row.get("ledger_run_id", "") or "",
            security_event_id=row.get("security_event_id", "") or "",
            approval_id=row.get("approval_id", "") or "",
            idempotency_key=row.get("idempotency_key", "") or "",
            correlation_id=row.get("correlation_id", "") or "",
            transition_log=list(log),
            metadata=dict(meta),
        )
