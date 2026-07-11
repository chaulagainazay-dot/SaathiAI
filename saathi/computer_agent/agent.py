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
                 engine: Optional[ExecutionEngine] = None, session=None):
        self.owner = owner
        self.engine = engine
        self.session = session          # ComputerSession (consent boundary)
        self.replay = Replay(workflow_id=workflow_id, owner=owner)

    def emergency_stop(self) -> dict:
        if self.session:
            return self.session.emergency_stop_now()
        return {"stopped": True, "state": "no_session"}

    def step(self, *, tool_id: str, args: Optional[dict] = None,
             approval_id: str = "", actor_type: str = "agent",
             app: str = "", origin: str = "", sensitive_target: bool = False) -> dict:
        """Execute one computer action through the gateway. Requires an active
        session (consent boundary); enforces app/origin allow-list; refuses to
        record/type into sensitive fields. Records a sanitized replay step."""
        args = args or {}
        # 1) active-session requirement — no control without live consent
        if self.session is not None:
            from saathi.computer_agent.session import SessionInactive
            try:
                self.session.require_active()
            except SessionInactive as e:
                return self._blocked(tool_id, args, f"session_inactive:{e.state}")
            # 2) app / origin allow-list
            from saathi.computer_agent import policy
            try:
                if origin:
                    policy.check_origin(self.session, origin)
                if app:
                    policy.check_app(self.session, app)
            except policy.PolicyDenied as e:
                return self._blocked(tool_id, args, f"policy_denied:{e.code}")
        # 3) sensitive field → pause for user, never type/record a secret
        if sensitive_target:
            from saathi.computer_agent.sensitive import sensitive_pause_plan
            plan = sensitive_pause_plan("sensitive_field")
            self.replay.record(tool_id=tool_id,
                               args={"note": plan["replay_marker"]},
                               status="paused_for_user", verified=False)
            return {"status": "paused_for_user", "plan": plan, "tool_id": tool_id}
        r = I.run(owner=self.owner, tool_id=tool_id, args=args,
                  approval_id=approval_id, actor_type=actor_type, engine=self.engine)
        verified = bool((r.get("data") or {}).get("verification", {}).get("verified")) \
            if isinstance(r.get("data"), dict) else False
        self.replay.record(tool_id=tool_id, args=args or {}, status=r.get("status", ""),
                           verified=verified)
        return r

    def _blocked(self, tool_id, args, reason) -> dict:
        self.replay.record(tool_id=tool_id, args=args, status="blocked", verified=False)
        return {"status": "blocked", "tool_id": tool_id, "reason": reason}

    def describe(self, *, tool_id: str, args: Optional[dict] = None) -> dict:
        """What would this action require (risk/approval)? For explain-before-act."""
        return I.describe_action(tool_id=tool_id, args=args or {}, owner=self.owner)

    def timeline(self) -> list[str]:
        return self.replay.timeline()
