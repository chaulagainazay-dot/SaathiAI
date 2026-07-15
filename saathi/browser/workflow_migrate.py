"""M17.26 — Browser workflow-step schema and migration onto InteractiveBrowser.act.

Production-reachable browser workflow steps must use InteractiveBrowser.act
(or fail closed). Arbitrary script bodies / raw selectors that bypass the
governed action schema are rejected.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from saathi.browser.interactive import (
    ActionClass,
    InteractiveBrowser,
    InteractiveResult,
    action_class_of,
)

# Allowed workflow step fields
ALLOWED_STEP_FIELDS = frozenset({
    "step_id", "session_id", "action_id", "action_type", "action_class",
    "target", "selector", "role", "name", "test_id", "url", "text",
    "file_path", "expected_page_state", "expected_effect", "approval_id",
    "approval_requirement", "idempotency_key", "timeout", "retry_policy",
    "handoff_policy", "evidence_policy", "redaction_policy",
    "on_success", "on_failure", "on_uncertain", "reconciliation_strategy",
    "actor_id", "mission_id", "mission_run_id", "payload",
})

# Reject these legacy bypass fields
FORBIDDEN_STEP_FIELDS = frozenset({
    "script", "raw_script", "javascript", "eval", "osascript",
    "playwright_code", "page_object", "raw_selector_bypass",
    "storage_state", "cookies_export",
})


class WorkflowStepError(RuntimeError):
    def __init__(self, code: str, message: str, *, details: Optional[dict] = None):
        self.code = code
        self.message = message
        self.details = dict(details or {})
        super().__init__(f"{code}: {message}")


@dataclass
class BrowserWorkflowStep:
    step_id: str
    action_type: str
    session_id: str = ""
    action_id: str = ""
    action_class: str = ""
    target: str = ""
    selector: str = ""
    role: str = ""
    name: str = ""
    test_id: str = ""
    url: str = ""
    text: str = ""
    file_path: str = ""
    expected_page_state: str = ""
    expected_effect: str = ""
    approval_id: str = ""
    approval_requirement: str = ""
    idempotency_key: str = ""
    timeout: int = 30
    retry_policy: str = "none"  # none | read_only_bounded
    handoff_policy: str = "request_on_captcha_mfa"
    evidence_policy: str = "default"
    redaction_policy: str = "default"
    on_success: str = "continue"
    on_failure: str = "fail"
    on_uncertain: str = "reconcile"
    reconciliation_strategy: str = "manual_review"
    actor_id: str = ""
    mission_id: str = ""
    mission_run_id: str = ""
    payload: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "step_id": self.step_id,
            "session_id": self.session_id,
            "action_id": self.action_id,
            "action_type": self.action_type,
            "action_class": self.action_class,
            "target": self.target,
            "selector": self.selector,
            "url": self.url,
            "expected_page_state": self.expected_page_state,
            "expected_effect": self.expected_effect,
            "approval_id": self.approval_id,
            "idempotency_key": self.idempotency_key,
            "timeout": self.timeout,
            "retry_policy": self.retry_policy,
            "handoff_policy": self.handoff_policy,
            "evidence_policy": self.evidence_policy,
            "redaction_policy": self.redaction_policy,
            "on_success": self.on_success,
            "on_failure": self.on_failure,
            "on_uncertain": self.on_uncertain,
            "reconciliation_strategy": self.reconciliation_strategy,
            "actor_id": self.actor_id,
            "mission_id": self.mission_id,
            "mission_run_id": self.mission_run_id,
        }


def parse_workflow_step(raw: dict) -> BrowserWorkflowStep:
    if not isinstance(raw, dict):
        raise WorkflowStepError("INVALID_STEP", "step must be a dict")
    unknown = set(raw.keys()) - ALLOWED_STEP_FIELDS
    forbidden = set(raw.keys()) & FORBIDDEN_STEP_FIELDS
    if forbidden:
        raise WorkflowStepError(
            "FORBIDDEN_FIELD",
            f"workflow step contains forbidden bypass fields: {sorted(forbidden)}",
            details={"fields": sorted(forbidden)},
        )
    if unknown:
        raise WorkflowStepError(
            "UNKNOWN_FIELD",
            f"workflow step has unsupported fields: {sorted(unknown)}",
            details={"fields": sorted(unknown)},
        )
    action_type = str(raw.get("action_type") or "").strip().lower()
    if not action_type:
        raise WorkflowStepError("MISSING_ACTION", "action_type required")
    aclass = raw.get("action_class") or action_class_of(action_type).value
    step_id = str(raw.get("step_id") or f"wfs-{uuid.uuid4().hex[:10]}")
    return BrowserWorkflowStep(
        step_id=step_id,
        action_type=action_type,
        session_id=str(raw.get("session_id") or ""),
        action_id=str(raw.get("action_id") or ""),
        action_class=str(aclass),
        target=str(raw.get("target") or raw.get("selector") or ""),
        selector=str(raw.get("selector") or raw.get("target") or ""),
        role=str(raw.get("role") or ""),
        name=str(raw.get("name") or ""),
        test_id=str(raw.get("test_id") or ""),
        url=str(raw.get("url") or ""),
        text=str(raw.get("text") or ""),
        file_path=str(raw.get("file_path") or ""),
        expected_page_state=str(raw.get("expected_page_state") or ""),
        expected_effect=str(raw.get("expected_effect") or ""),
        approval_id=str(raw.get("approval_id") or ""),
        approval_requirement=str(raw.get("approval_requirement") or ""),
        idempotency_key=str(raw.get("idempotency_key") or ""),
        timeout=int(raw.get("timeout") or 30),
        retry_policy=str(raw.get("retry_policy") or "none"),
        handoff_policy=str(raw.get("handoff_policy") or "request_on_captcha_mfa"),
        evidence_policy=str(raw.get("evidence_policy") or "default"),
        redaction_policy=str(raw.get("redaction_policy") or "default"),
        on_success=str(raw.get("on_success") or "continue"),
        on_failure=str(raw.get("on_failure") or "fail"),
        on_uncertain=str(raw.get("on_uncertain") or "reconcile"),
        reconciliation_strategy=str(raw.get("reconciliation_strategy") or "manual_review"),
        actor_id=str(raw.get("actor_id") or ""),
        mission_id=str(raw.get("mission_id") or ""),
        mission_run_id=str(raw.get("mission_run_id") or ""),
        payload=dict(raw.get("payload") or {}),
    )


def execute_workflow_step(
    ib: InteractiveBrowser,
    step: BrowserWorkflowStep | dict,
    *,
    session_id: str = "",
    actor_id: str = "",
    captcha_detected: bool = False,
    mfa_detected: bool = False,
) -> InteractiveResult:
    """Execute one workflow step through InteractiveBrowser.act."""
    if isinstance(step, dict):
        step = parse_workflow_step(step)
    sid = session_id or step.session_id
    actor = actor_id or step.actor_id
    if not sid:
        return InteractiveResult(
            status="denied", failure_category="session_required",
            summary="workflow step requires session_id",
        )
    if not actor:
        return InteractiveResult(
            status="denied", failure_category="missing_actor",
            summary="workflow step requires actor_id",
        )

    # CAPTCHA / MFA → governed handoff
    if captcha_detected or mfa_detected or step.action_type in ("captcha_solve", "mfa_bypass"):
        if step.action_type in ("captcha_solve", "mfa_bypass"):
            return InteractiveResult(
                status="denied", session_id=sid,
                action_type=step.action_type,
                action_class=ActionClass.PROHIBITED.value,
                failure_category="prohibited_action",
                summary="CAPTCHA/MFA solve is prohibited; use human handoff",
            )
        reason = "captcha" if captcha_detected else "mfa"
        return ib.request_handoff(
            sid, actor_id=actor,
            reason=reason,
            required_human_action=f"complete_{reason}",
            allowed_scope=["human_confirm", reason],
        )

    # Map retry policy — external effects never blind-retry
    retry_authorized = True
    retry_attempt = int(step.payload.get("retry_attempt") or 0)
    aclass = action_class_of(step.action_type)
    if retry_attempt > 0:
        if step.retry_policy == "none":
            retry_authorized = False
        elif aclass in (ActionClass.EXTERNAL_EFFECT, ActionClass.FINANCIAL):
            retry_authorized = False
        elif step.retry_policy != "read_only_bounded" and aclass != ActionClass.READ_ONLY:
            retry_authorized = False

    res = ib.act(
        session_id=sid,
        action=step.action_type,
        actor_id=actor,
        url=step.url,
        selector=step.selector or step.target,
        role=step.role,
        name=step.name,
        test_id=step.test_id,
        text=step.text,
        file_path=step.file_path,
        payload={
            **step.payload,
            "workflow_step_id": step.step_id,
            "evidence_policy": step.evidence_policy,
            "redaction_policy": step.redaction_policy,
        },
        expected_effect=step.expected_effect,
        expected_page_state=step.expected_page_state,
        approval_id=step.approval_id,
        idempotency_key=step.idempotency_key,
        action_id=step.action_id or f"wfs-act-{uuid.uuid4().hex[:12]}",
        timeout=step.timeout,
        retry_attempt=retry_attempt,
        retry_authorized=retry_authorized,
    )
    res.details = {
        **(res.details or {}),
        "workflow_step_id": step.step_id,
        "on_success": step.on_success,
        "on_failure": step.on_failure,
        "on_uncertain": step.on_uncertain,
        "uses_interactive_browser_act": True,
    }
    return res


def fail_closed_legacy_workflow(source: str, action: str = "") -> dict:
    """Standard denial for unmigrated raw browser workflow paths."""
    return {
        "error": "browser_governance",
        "code": "WORKFLOW_REQUIRES_INTERACTIVE_BROWSER",
        "message": (
            f"Legacy browser workflow path {source!r} is fail-closed. "
            "Migrate to InteractiveBrowser.act / execute_workflow_step."
        ),
        "action": action,
        "migration": "saathi.browser.workflow_migrate.execute_workflow_step",
    }


# Registry of migrated production-reachable workflow entry points
MIGRATED_WORKFLOWS: dict[str, dict] = {
    "agent_browser.click": {
        "entry": "saathi.tools.agent_browser.ab_click",
        "uses_interactive_browser_act": True,
        "disposition": "MIGRATED",
    },
    "agent_browser.fill": {
        "entry": "saathi.tools.agent_browser.ab_fill",
        "uses_interactive_browser_act": True,
        "disposition": "MIGRATED",
    },
    "agent_browser.type": {
        "entry": "saathi.tools.agent_browser.ab_type",
        "uses_interactive_browser_act": True,
        "disposition": "MIGRATED",
    },
    "workflow_step.execute": {
        "entry": "saathi.browser.workflow_migrate.execute_workflow_step",
        "uses_interactive_browser_act": True,
        "disposition": "MIGRATED",
    },
    "human_browser.workflow_raw": {
        "entry": "saathi.infrastructure.human_browser.workflows",
        "uses_interactive_browser_act": False,
        "disposition": "FAIL_CLOSED_OR_ISOLATED_QUEUE",
        "note": "Signed isolated queue remains; generic autonomy blocked",
    },
}
