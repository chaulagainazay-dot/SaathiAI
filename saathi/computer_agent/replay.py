"""M17 replayable execution timeline.

Every computer-agent workflow is a sequence of gateway-executed steps. A replay
is the ordered, sanitized record of those steps (never secrets/passwords/OTP) so
a workflow can be reviewed and re-run through the SAME ExecutionEngine.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

# never record these keys into a replay step
_SENSITIVE = {"password", "passwd", "token", "secret", "otp", "code", "pin",
              "api_key", "cookie", "authorization"}


def _sanitize(args: dict) -> dict:
    out = {}
    for k, v in (args or {}).items():
        if any(s in k.lower() for s in _SENSITIVE):
            out[k] = "[REDACTED]"
        elif isinstance(v, str) and len(v) > 200:
            out[k] = v[:200] + "…"
        else:
            out[k] = v
    return out


@dataclass
class ReplayStep:
    seq: int
    tool_id: str
    args: dict
    status: str
    verified: bool = False
    at: float = 0.0

    def to_dict(self) -> dict:
        return {"seq": self.seq, "tool_id": self.tool_id, "args": _sanitize(self.args),
                "status": self.status, "verified": self.verified, "at": self.at}


@dataclass
class Replay:
    workflow_id: str
    owner: str
    steps: list = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    def record(self, *, tool_id: str, args: dict, status: str, verified: bool = False) -> ReplayStep:
        step = ReplayStep(seq=len(self.steps) + 1, tool_id=tool_id, args=args,
                          status=status, verified=verified, at=time.time())
        self.steps.append(step)
        return step

    def to_dict(self) -> dict:
        return {"workflow_id": self.workflow_id, "owner": self.owner,
                "created_at": self.created_at,
                "steps": [s.to_dict() for s in self.steps]}

    def timeline(self) -> list[str]:
        return [f"{s.seq}. {s.tool_id} → {s.status}"
                + (" ✓" if s.verified else "") for s in self.steps]
