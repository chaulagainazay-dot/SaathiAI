"""Typed pilot results (structured, no raw provider dump)."""
from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any


def _rid() -> str:
    return uuid.uuid4().hex[:16]


@dataclass
class OperationResult:
    ok: bool
    operation: str
    request_id: str = field(default_factory=_rid)
    provider: str = "insforge"
    data: dict = field(default_factory=dict)
    error_category: str = ""
    detail: str = ""
    duration_ms: float = 0.0
    audited: bool = False
    evidence_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "operation": self.operation,
            "request_id": self.request_id,
            "provider": self.provider,
            "data": self.data,
            "error_category": self.error_category,
            "detail": self.detail[:300],
            "duration_ms": round(self.duration_ms, 2),
            "audited": self.audited,
            "evidence_id": self.evidence_id,
        }


@dataclass
class HealthData:
    status: str  # ok | degraded | down | disabled | auth | unknown
    version: str = ""
    service: str = ""
    reachable: bool = False
    detail: str = ""

    def to_dict(self) -> dict:
        return asdict(self)
