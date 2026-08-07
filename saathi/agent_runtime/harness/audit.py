"""Bounded in-process audit/evidence hooks for FM-I1 (no external sinks required)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Mapping, Optional
import time


@dataclass(frozen=True)
class HarnessAuditRecord:
    action: str
    timestamp: float
    session_id: str = ""
    run_id: str = ""
    correlation_id: str = ""
    detail: Mapping[str, Any] = field(default_factory=dict)

    def safe_dict(self) -> dict:
        banned = {"password", "secret", "token", "api_key", "authorization"}
        safe_detail = {
            k: v for k, v in dict(self.detail).items()
            if not any(b in str(k).lower() for b in banned)
        }
        return {
            "action": self.action,
            "timestamp": self.timestamp,
            "session_id": self.session_id,
            "run_id": self.run_id,
            "correlation_id": self.correlation_id,
            "detail": safe_detail,
        }


class HarnessAuditLog:
    """Append-only in-memory audit log for deterministic tests and evidence."""

    def __init__(self) -> None:
        self._records: List[HarnessAuditRecord] = []

    def record(
        self,
        action: str,
        *,
        session_id: str = "",
        run_id: str = "",
        correlation_id: str = "",
        detail: Optional[Mapping[str, Any]] = None,
    ) -> HarnessAuditRecord:
        rec = HarnessAuditRecord(
            action=action,
            timestamp=time.time(),
            session_id=session_id,
            run_id=run_id,
            correlation_id=correlation_id,
            detail=dict(detail or {}),
        )
        self._records.append(rec)
        return rec

    def all(self) -> List[HarnessAuditRecord]:
        return list(self._records)

    def by_session(self, session_id: str) -> List[HarnessAuditRecord]:
        return [r for r in self._records if r.session_id == session_id]

    def actions(self) -> List[str]:
        return [r.action for r in self._records]

    def clear(self) -> None:
        self._records.clear()
