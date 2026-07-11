"""M17 Computer Agent runner.

A thin orchestrator: it perceives, decides a step, then executes that step
through the M15 integration funnel (ExecutionEngine → gateway → risk/approval →
evidence). It NEVER actuates directly — every action is a connector tool call.
Destructive/side-effect ops surface as approval_required until a bound approval
exists. Each step is recorded in a sanitized Replay.
"""
from __future__ import annotations

from typing import Optional

from saathi.connectors.platform import integration as I
from saathi.connectors.platform.execution import ExecutionEngine
from saathi.computer_agent.replay import Replay
from saathi.computer_agent import operations  # noqa: F401  (registers connectors)


class ComputerAgent:
    def __init__(self, *, owner: str, workflow_id: str = "wf",
                 engine: Optional[ExecutionEngine] = None):
        self.owner = owner
        self.engine = engine
        self.replay = Replay(workflow_id=workflow_id, owner=owner)

    def step(self, *, tool_id: str, args: Optional[dict] = None,
             approval_id: str = "", actor_type: str = "agent") -> dict:
        """Execute one computer action through the gateway. Returns the
        normalized result dict; records a sanitized replay step."""
        r = I.run(owner=self.owner, tool_id=tool_id, args=args or {},
                  approval_id=approval_id, actor_type=actor_type, engine=self.engine)
        verified = bool((r.get("data") or {}).get("verification", {}).get("verified")) \
            if isinstance(r.get("data"), dict) else False
        self.replay.record(tool_id=tool_id, args=args or {}, status=r.get("status", ""),
                           verified=verified)
        return r

    def describe(self, *, tool_id: str, args: Optional[dict] = None) -> dict:
        """What would this action require (risk/approval)? For explain-before-act."""
        return I.describe_action(tool_id=tool_id, args=args or {}, owner=self.owner)

    def timeline(self) -> list[str]:
        return self.replay.timeline()
