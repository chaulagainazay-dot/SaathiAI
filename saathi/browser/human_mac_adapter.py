"""M17.26 — Human Mac browser adapter under the same governed session contract.

Human Mac actions must originate from a governed session with action IDs.
Raw AppleScript remains blocked outside the low-level chrome_backend allowlist.
Human control is bounded to the approved browser session/task — not full desktop.
Human actions do not count as approval unless the approval service records them.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from saathi.browser.adapter_contract import (
    AdapterActionResult,
    AdapterError,
    AdapterErrorCode,
    AdapterHealth,
    AdapterHealthState,
    BrowserSessionAdapter,
    GovernedActionRequest,
    heartbeat,
)
from saathi.browser.production_adapter import ProductionBrowserAdapter


class HumanControlMode(str):
    AUTOMATED = "automated_governed"
    HUMAN_TAKEOVER = "human_takeover"
    HUMAN_COMPLETION = "human_completion"
    HUMAN_DECLINE = "human_decline"
    ADAPTER_DISCONNECT = "adapter_disconnect"


@dataclass
class HumanMacState:
    session_id: str
    mode: str = HumanControlMode.AUTOMATED
    assigned_human: str = ""
    handoff_id: str = ""
    bounded_app: str = "browser"  # never full desktop
    allow_app_switch: bool = False
    last_event: str = ""
    sensitive_input_logged: bool = False  # must stay False


class HumanMacAdapter(BrowserSessionAdapter):
    """Governed Human Mac adapter — delegates automation to ProductionBrowserAdapter
    and tracks human takeover/completion without granting desktop control.
    """

    adapter_id = "human-mac"
    adapter_type = "human_mac"

    def __init__(
        self,
        *,
        production: ProductionBrowserAdapter | None = None,
        allow_unrestricted_desktop: bool = False,
    ):
        if allow_unrestricted_desktop:
            raise AdapterError(
                AdapterErrorCode.CONTEXT_MISSING,
                "unrestricted desktop control is prohibited",
            )
        self.production = production or ProductionBrowserAdapter(allow_live=False)
        self.adapter_id = f"human-mac-{uuid.uuid4().hex[:8]}"
        self._human: dict[str, HumanMacState] = {}
        self._osascript_blocked = True  # product path never runs raw osascript

    def attach_session(
        self, session_id: str, *, endpoint: str = "", metadata: dict | None = None,
        **kwargs,
    ) -> AdapterHealth:
        h = self.production.attach_session(
            session_id, endpoint=endpoint, metadata=metadata, **kwargs,
        )
        self._human[session_id] = HumanMacState(session_id=session_id)
        h.adapter_id = self.adapter_id
        h.adapter_type = self.adapter_type
        h.supported_capabilities = list(h.supported_capabilities) + [
            "human_takeover", "human_complete", "human_decline",
        ]
        return h

    def validate_session(self, session_id: str, **kwargs) -> bool:
        return self.production.validate_session(session_id, **kwargs)

    def health(self, session_id: str = "") -> AdapterHealth:
        h = self.production.health(session_id)
        h.adapter_id = self.adapter_id
        h.adapter_type = self.adapter_type
        st = self._human.get(session_id)
        if st:
            h.details = {
                **h.details,
                "human_mode": st.mode,
                "assigned_human": st.assigned_human,
                "bounded_app": st.bounded_app,
                "allow_app_switch": st.allow_app_switch,
            }
        return h

    def navigate(self, request: GovernedActionRequest) -> AdapterActionResult:
        return self.act(request)

    def inspect(self, request: GovernedActionRequest) -> AdapterActionResult:
        return self.production.inspect(request)

    def act(self, request: GovernedActionRequest) -> AdapterActionResult:
        st = self._human.get(request.session_id)
        if st and st.mode == HumanControlMode.HUMAN_TAKEOVER:
            if not request.payload.get("human_action"):
                return AdapterActionResult(
                    status="denied",
                    action_id=request.action_id,
                    action_type=request.action_type,
                    summary="human takeover active; concurrent agent control denied",
                    error_category=AdapterErrorCode.HUMAN_CONCURRENT.value.lower(),
                )
            # Human-driven governed action — still session-bound, no secrets logged
            if request.payload.get("sensitive_manual_input"):
                st.sensitive_input_logged = False  # enforce
            if request.payload.get("app_switch") and not st.allow_app_switch:
                return AdapterActionResult(
                    status="denied",
                    action_id=request.action_id,
                    action_type=request.action_type,
                    summary="unexpected app switch requires separate permission",
                    error_category="app_switch_denied",
                )
            # Record as human-originated; does NOT count as approval
            result = self.production.act(
                GovernedActionRequest(
                    **{
                        **request.__dict__,
                        "payload": {
                            **request.payload,
                            "human_action": True,
                            "text": "***REDACTED***",
                        },
                        "text_redacted": True,
                    }
                )
            )
            result.details = {
                **result.details,
                "human_originated": True,
                "counts_as_approval": False,
                "mode": st.mode,
            }
            return result
        return self.production.act(request)

    def capture_evidence(self, request: GovernedActionRequest, *, kind: str = "screenshot") -> AdapterActionResult:
        return self.production.capture_evidence(request, kind=kind)

    def pause(self, session_id: str, *, reason: str = "") -> AdapterHealth:
        return self.production.pause(session_id, reason=reason)

    def resume(self, session_id: str, *, checkpoint: dict | None = None) -> AdapterHealth:
        st = self._human.get(session_id)
        if st and st.mode == HumanControlMode.HUMAN_TAKEOVER:
            raise AdapterError(
                AdapterErrorCode.HUMAN_CONCURRENT,
                "complete or decline human handoff before automated resume",
            )
        return self.production.resume(session_id, checkpoint=checkpoint)

    def reconcile(self, session_id: str, *, action_id: str = "") -> AdapterActionResult:
        return self.production.reconcile(session_id, action_id=action_id)

    def close_session(self, session_id: str, *, detach_only: bool = True) -> AdapterHealth:
        self._human.pop(session_id, None)
        return self.production.close_session(session_id, detach_only=detach_only)

    # ── human handoff integration (M17.25 state) ───────────────────────────

    def begin_human_takeover(
        self,
        session_id: str,
        *,
        human_id: str,
        handoff_id: str = "",
        allow_app_switch: bool = False,
    ) -> AdapterHealth:
        if not self.production.validate_session(session_id):
            raise AdapterError(AdapterErrorCode.SESSION_REQUIRED, "session not attached")
        st = self._human.setdefault(session_id, HumanMacState(session_id=session_id))
        st.mode = HumanControlMode.HUMAN_TAKEOVER
        st.assigned_human = human_id
        st.handoff_id = handoff_id
        st.allow_app_switch = bool(allow_app_switch)
        st.last_event = "human_takeover"
        self.production.set_human_control(session_id, True)
        h = self.production.pause(session_id, reason="human_takeover")
        h.adapter_id = self.adapter_id
        h.details["human_mode"] = st.mode
        h.details["assigned_human"] = human_id
        return h

    def complete_human(
        self,
        session_id: str,
        *,
        human_id: str,
        decline: bool = False,
        resolution: str = "completed",
    ) -> AdapterActionResult:
        st = self._human.get(session_id)
        if not st:
            return AdapterActionResult(
                status="denied", error_category="session_required",
                summary="no human mac state",
            )
        if st.assigned_human and st.assigned_human != human_id:
            return AdapterActionResult(
                status="denied", error_category="handoff_owner",
                summary="handoff claimed by another human",
            )
        if decline:
            st.mode = HumanControlMode.HUMAN_DECLINE
            st.last_event = resolution
            self.production.set_human_control(session_id, False)
            return AdapterActionResult(
                status="denied",
                action_type="human_decline",
                summary=resolution,
                error_category="handoff_declined",
                details={"counts_as_approval": False},
            )
        st.mode = HumanControlMode.HUMAN_COMPLETION
        st.last_event = resolution
        self.production.set_human_control(session_id, False)
        # Automated resume still requires InteractiveBrowser.resume + policy
        return AdapterActionResult(
            status="succeeded",
            action_type="human_completion",
            summary=resolution,
            details={
                "counts_as_approval": False,
                "requires_policy_resume": True,
                "mode": st.mode,
            },
        )

    def mark_disconnect(self, session_id: str) -> AdapterHealth:
        st = self._human.setdefault(session_id, HumanMacState(session_id=session_id))
        st.mode = HumanControlMode.ADAPTER_DISCONNECT
        st.last_event = "adapter_disconnect"
        self.production.simulate_disconnect(session_id)
        return self.health(session_id)

    def run_osascript(self, *args: Any) -> None:
        """Blocked at product boundary — raw AppleScript only inside allowlisted backend."""
        raise AdapterError(
            AdapterErrorCode.RAW_FALLBACK_DENIED,
            "raw AppleScript/osascript blocked outside allowlisted adapter backend",
        )


_HM: HumanMacAdapter | None = None


def default_human_mac_adapter(**kwargs) -> HumanMacAdapter:
    global _HM
    if kwargs:
        return HumanMacAdapter(**kwargs)
    if _HM is None:
        _HM = HumanMacAdapter()
    return _HM


def reset_human_mac_adapter() -> None:
    global _HM
    _HM = None
