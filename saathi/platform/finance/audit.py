"""Financial-browser audit log — records agent reads WITHOUT secrets. In-memory, bounded."""
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field

from saathi.platform.finance.policy import redact

_MAX = 500


@dataclass(frozen=True)
class AuditRecord:
    ts: float
    provider: str
    actor: str
    capability: str          # e.g. READ_PORTFOLIO / OBSERVE_PUBLIC_PAGE / AGENT_ACTION_BLOCKED
    result: str              # OK / BLOCKED / ERROR
    session_id: str = ""
    detail: str = ""         # redacted free text (never secrets)

    def to_public(self) -> dict:
        return {"ts": self.ts, "provider": self.provider, "actor": self.actor,
                "capability": self.capability, "result": self.result,
                "session_id": self.session_id, "detail": self.detail}


_LOG: deque = deque(maxlen=_MAX)


def record(*, provider: str, actor: str, capability: str, result: str,
           session_id: str = "", detail: str = "") -> AuditRecord:
    rec = AuditRecord(ts=time.time(), provider=str(provider), actor=str(actor),
                      capability=str(capability), result=str(result),
                      session_id=session_id, detail=redact(detail)[:200])
    _LOG.append(rec)
    return rec


def tail(n: int = 50) -> list[dict]:
    return [r.to_public() for r in list(_LOG)[-n:]]


def clear() -> int:
    n = len(_LOG)
    _LOG.clear()
    return n
