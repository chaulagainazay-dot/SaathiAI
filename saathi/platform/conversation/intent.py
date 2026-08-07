"""Authority-safe tool intent detection — propose only, never execute."""
from __future__ import annotations

import re
from typing import Any

from .models import ActionKind

# Patterns that suggest the user wants an action (not direct execution).
_ACTION_PATTERNS = (
    (re.compile(r"\b(run|execute|start|launch)\b.*\b(mission|task|pipeline)\b", re.I), "mission_run"),
    (re.compile(r"\b(approve|deny)\b.*\b(approval|request)\b", re.I), "approval_decide"),
    (re.compile(r"\b(open|show|navigate)\b.*\b(mission|dashboard|ielts|trading)\b", re.I), "navigate"),
    (re.compile(r"\b(create|new)\b.*\b(project|mission|task)\b", re.I), "create_entity"),
    (re.compile(r"\b(buy|sell|place order|leverage|go live)\b", re.I), "trading_blocked"),
)


class ToolIntentRouter:
    """Detects possible intents. Never calls ExecutionGateway itself."""

    def analyze(self, user_text: str, assistant_text: str = "") -> dict[str, Any]:
        text = f"{user_text or ''}\n{assistant_text or ''}"
        for pattern, intent_id in _ACTION_PATTERNS:
            if pattern.search(text):
                if intent_id == "trading_blocked":
                    return {
                        "action_kind": ActionKind.BLOCKED.value,
                        "intent_id": intent_id,
                        "summary": "Trading execution is blocked; guidance only under Trading Guardian.",
                        "requires_approval": True,
                        "executable_by_model": False,
                        "route": "TradingGuardian+ApprovalCenter",
                    }
                if intent_id in {"mission_run", "approval_decide", "create_entity"}:
                    return {
                        "action_kind": ActionKind.APPROVAL_REQUIRED.value,
                        "intent_id": intent_id,
                        "summary": "Suggested platform action requires PlatformAgentRuntime → ExecutionGateway and approvals.",
                        "requires_approval": True,
                        "executable_by_model": False,
                        "route": "PlatformAgentRuntime→ExecutionGateway",
                    }
                return {
                    "action_kind": ActionKind.SUGGESTED_ACTION.value,
                    "intent_id": intent_id,
                    "summary": "Suggested navigation or non-mutating action; user must confirm in shell.",
                    "requires_approval": False,
                    "executable_by_model": False,
                    "route": "shell_navigation",
                }
        return {
            "action_kind": ActionKind.INFORMATIONAL.value,
            "intent_id": "informational",
            "summary": "Informational response only.",
            "requires_approval": False,
            "executable_by_model": False,
            "route": "none",
        }

    def deny_direct_execution(self) -> dict[str, Any]:
        return {
            "allowed": False,
            "reason": "Models may not execute tools; PlatformAgentRuntime and ExecutionGateway remain sole authorities.",
        }
