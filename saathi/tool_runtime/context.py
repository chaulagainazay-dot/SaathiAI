"""M49.1 bounded tool execution context — no unrestricted handles."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

logger = logging.getLogger("saathi.tool_runtime")


@dataclass
class BoundedToolContext:
    """Execution context exposed to adapters — deliberately constrained.

    Does **not** expose: raw secrets, unrestricted RunStore, DB handles,
    unrestricted filesystem, unrestricted subprocess, raw approval records.
    """

    run_id: str
    call_id: str
    attempt: int
    mission_id: str = ""
    agent_id: str = ""
    tool_id: str = ""
    tool_version: str = ""
    capability: str = ""
    authority_class: str = ""
    side_effect_class: str = ""
    approval_present: bool = False
    deadline: float = 0.0
    timeout_sec: float = 30.0
    secret_handles: dict[str, str] = field(default_factory=dict)  # name → handle id only
    cancel_check: Callable[[], bool] | None = None
    event_sink: list[dict] = field(default_factory=list)
    evidence_sink: list[dict] = field(default_factory=list)
    # Optional small local scratch for reversible demo tools (tests)
    scratch: dict[str, Any] = field(default_factory=dict)

    def should_cancel(self) -> bool:
        if self.cancel_check:
            try:
                return bool(self.cancel_check())
            except Exception:
                return False
        return False

    def raise_if_cancelled(self) -> None:
        if self.should_cancel():
            raise ToolCancelledError("cancellation_requested")

    def remaining_sec(self) -> float:
        if self.deadline and self.deadline > 0:
            return max(0.0, self.deadline - time.time())
        return max(0.0, self.timeout_sec)

    def emit(self, event: str, payload: dict | None = None) -> None:
        self.event_sink.append(
            {
                "event": event,
                "ts": time.time(),
                "call_id": self.call_id,
                "run_id": self.run_id,
                "payload": payload or {},
            }
        )

    def evidence(self, kind: str, payload: dict | None = None) -> str:
        ref = f"ev_{self.call_id}_{len(self.evidence_sink)}"
        self.evidence_sink.append(
            {"ref": ref, "kind": kind, "ts": time.time(), "payload": payload or {}}
        )
        return ref

    def log_info(self, msg: str) -> None:
        logger.info("[%s/%s] %s", self.run_id, self.call_id, msg)


class ToolCancelledError(RuntimeError):
    pass


class ToolTimeoutError(RuntimeError):
    pass
