"""M17.25 — Governed interactive browser actions, sessions, and human handoffs.

All interactive work enters through InteractiveBrowser → session ownership →
action classification → (optional pre-commit) → GovernedBrowser.execute →
ExecutionGateway. Navigation approval does not authorize submit/click/type.
"""
from __future__ import annotations

import hashlib
import re
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from saathi.browser.gov_session import (
    ACTIONABLE_SESSION,
    BrowserSessionStore,
    GovernedBrowserSession,
    SessionError,
    SessionStatus,
    default_session_store,
    reset_session_store,
)
from saathi.browser.governed import (
    BrowserAdapter,
    GovernedBrowser,
    redact_text,
    reset_browser_metrics,
    reset_governed_browser,
)
from saathi.browser.policy import (
    BrowserAction,
    PROHIBITED_ACTIONS,
    check_domain,
    classify_risk,
    origin_of,
    parse_action,
    path_is_inside,
)
from saathi.execution.execution_state import ExecutionState
from saathi.execution.record import ExecutionRecord, safe_summary
from saathi.execution.store import ExecutionStore
from saathi.execution.universal import UniversalBoundary, reset_boundary

# ── Action taxonomy ──────────────────────────────────────────────────────────


class ActionClass(str, Enum):
    READ_ONLY = "read_only"
    LOW_INTERACTIVE = "low_interactive"
    SENSITIVE_INPUT = "sensitive_input"
    EXTERNAL_EFFECT = "external_effect"
    FINANCIAL = "financial"
    PROHIBITED = "prohibited"
    HANDOFF = "handoff"
    LIFECYCLE = "lifecycle"


# Maps BrowserAction (and string aliases) → class
_ACTION_CLASS_MAP: dict[str, ActionClass] = {
    # read-only
    "navigate": ActionClass.READ_ONLY,
    "open": ActionClass.READ_ONLY,
    "read": ActionClass.READ_ONLY,
    "extract": ActionClass.READ_ONLY,
    "screenshot": ActionClass.READ_ONLY,
    "scroll": ActionClass.READ_ONLY,
    "wait": ActionClass.READ_ONLY,
    "inspect_dom": ActionClass.READ_ONLY,
    "snapshot": ActionClass.READ_ONLY,
    "read_metadata": ActionClass.READ_ONLY,
    # low interactive
    "click": ActionClass.LOW_INTERACTIVE,
    "hover": ActionClass.LOW_INTERACTIVE,
    "expand": ActionClass.LOW_INTERACTIVE,
    "open_menu": ActionClass.LOW_INTERACTIVE,
    "switch_tab": ActionClass.LOW_INTERACTIVE,
    "select_filter": ActionClass.LOW_INTERACTIVE,
    "dismiss_dialog": ActionClass.LOW_INTERACTIVE,
    "select": ActionClass.LOW_INTERACTIVE,
    "select_option": ActionClass.LOW_INTERACTIVE,
    "check": ActionClass.LOW_INTERACTIVE,
    "uncheck": ActionClass.LOW_INTERACTIVE,
    "type": ActionClass.LOW_INTERACTIVE,
    "fill": ActionClass.LOW_INTERACTIVE,
    # sensitive
    "enter_credentials": ActionClass.SENSITIVE_INPUT,
    "enter_pii": ActionClass.SENSITIVE_INPUT,
    "enter_payment_info": ActionClass.SENSITIVE_INPUT,
    "upload": ActionClass.SENSITIVE_INPUT,
    "paste_clipboard": ActionClass.SENSITIVE_INPUT,
    "grant_permissions": ActionClass.SENSITIVE_INPUT,
    "change_account_settings": ActionClass.SENSITIVE_INPUT,
    # external effect
    "submit": ActionClass.EXTERNAL_EFFECT,
    "send_message": ActionClass.EXTERNAL_EFFECT,
    "publish": ActionClass.EXTERNAL_EFFECT,
    "create_account": ActionClass.EXTERNAL_EFFECT,
    "book": ActionClass.EXTERNAL_EFFECT,
    "confirm": ActionClass.EXTERNAL_EFFECT,
    "accept_terms": ActionClass.EXTERNAL_EFFECT,
    "download": ActionClass.EXTERNAL_EFFECT,
    "delete_external": ActionClass.EXTERNAL_EFFECT,
    "workflow": ActionClass.EXTERNAL_EFFECT,
    # financial
    "checkout": ActionClass.FINANCIAL,
    "purchase": ActionClass.FINANCIAL,
    "payment": ActionClass.FINANCIAL,
    "money_transfer": ActionClass.FINANCIAL,
    "trade": ActionClass.FINANCIAL,
    "cancel_order": ActionClass.FINANCIAL,
    "modify_stop_loss": ActionClass.FINANCIAL,
    "change_leverage": ActionClass.FINANCIAL,
    "withdrawal": ActionClass.FINANCIAL,
    # prohibited
    "eval_js": ActionClass.PROHIBITED,
    "mfa_bypass": ActionClass.PROHIBITED,
    "captcha_solve": ActionClass.PROHIBITED,
    "password_change": ActionClass.PROHIBITED,
    "account_delete": ActionClass.PROHIBITED,
    # handoff / lifecycle
    "request_handoff": ActionClass.HANDOFF,
    "complete_handoff": ActionClass.HANDOFF,
    "close_session": ActionClass.LIFECYCLE,
    "checkpoint": ActionClass.LIFECYCLE,
    "resume": ActionClass.LIFECYCLE,
}

# Which classes require approval by default (outside pure staging auto)
_APPROVAL_REQUIRED_CLASSES = frozenset({
    ActionClass.SENSITIVE_INPUT,
    ActionClass.EXTERNAL_EFFECT,
    ActionClass.FINANCIAL,
})

# External-effect / commit boundary actions
COMMIT_ACTIONS = frozenset({
    "submit", "send_message", "publish", "create_account", "book", "confirm",
    "accept_terms", "purchase", "checkout", "payment", "trade", "withdrawal",
    "delete_external", "money_transfer",
})

_SENSITIVE_SELECTOR_RE = re.compile(
    r"(?i)(password|passwd|otp|ssn|card|cvv|iban|credential|secret|token|pin)"
)
_COORD_RE = re.compile(r"^\s*\d+\s*,\s*\d+\s*$")


class TargetError(RuntimeError):
    def __init__(self, code: str, message: str, *, details: Optional[dict] = None):
        self.code = code
        self.message = message
        self.details = dict(details or {})
        super().__init__(f"{code}: {message}")


def action_class_of(action: str | BrowserAction) -> ActionClass:
    if isinstance(action, BrowserAction):
        key = action.value
    else:
        key = str(action).strip().lower().replace("-", "_")
    if key in _ACTION_CLASS_MAP:
        return _ACTION_CLASS_MAP[key]
    # try parse as BrowserAction
    try:
        ba = parse_action(key)
        return _ACTION_CLASS_MAP.get(ba.value, ActionClass.LOW_INTERACTIVE)
    except Exception:
        return ActionClass.LOW_INTERACTIVE


def requires_approval_for_class(
    aclass: ActionClass, *, environment: str = "dev", sensitive_field: bool = False,
) -> bool:
    if aclass == ActionClass.PROHIBITED:
        return True
    if aclass == ActionClass.FINANCIAL:
        return True
    if aclass in _APPROVAL_REQUIRED_CLASSES:
        if environment in ("dev", "test", "staging") and aclass == ActionClass.SENSITIVE_INPUT:
            return sensitive_field  # non-sensitive fill may auto on staging
        if environment in ("dev", "test") and aclass == ActionClass.EXTERNAL_EFFECT:
            return True  # always for external even in dev for commit boundary tests
        return True
    if sensitive_field:
        return True
    return False


def is_sensitive_target(selector: str = "", field_name: str = "") -> bool:
    blob = f"{selector} {field_name}"
    return bool(_SENSITIVE_SELECTOR_RE.search(blob))


@dataclass
class TargetSpec:
    """Bounded target resolution result (never holds secret values)."""
    selector: str = ""
    role: str = ""
    name: str = ""
    test_id: str = ""
    resolved_count: int = 1
    resolved_label: str = ""
    ambiguous: bool = False
    sensitive: bool = False
    origin: str = ""
    page_fingerprint: str = ""
    digest: str = ""

    def compute_digest(self) -> str:
        raw = f"{self.selector}|{self.role}|{self.name}|{self.test_id}|{self.origin}|{self.page_fingerprint}"
        self.digest = hashlib.sha256(raw.encode()).hexdigest()[:24]
        return self.digest


def resolve_target(
    *,
    selector: str = "",
    role: str = "",
    name: str = "",
    test_id: str = "",
    origin: str = "",
    page_fingerprint: str = "",
    page_elements: Optional[list[dict]] = None,
    allow_coordinates: bool = False,
) -> TargetSpec:
    """Resolve a target with ambiguity / sensitive / coordinate checks."""
    if not allow_coordinates and selector and _COORD_RE.match(selector):
        raise TargetError(
            "COORDINATE_TARGET_BLOCKED",
            "raw mouse coordinates are restricted; use role/label/test_id/selector",
        )
    if not any((selector, role, name, test_id)):
        # some actions (scroll/wait) have no target
        t = TargetSpec(origin=origin, page_fingerprint=page_fingerprint)
        t.compute_digest()
        return t

    preferred = bool(role or name or test_id)
    sensitive = is_sensitive_target(selector, name)
    resolved = 1
    label = name or test_id or selector or role
    ambiguous = False

    if page_elements is not None:
        matches = []
        for el in page_elements:
            if test_id and el.get("test_id") == test_id:
                matches.append(el)
            elif role and name and el.get("role") == role and el.get("name") == name:
                matches.append(el)
            elif selector and el.get("selector") == selector:
                matches.append(el)
            elif name and el.get("name") == name:
                matches.append(el)
        resolved = len(matches)
        if resolved == 0:
            raise TargetError("TARGET_MISSING", "target element not found",
                              details={"selector": selector, "role": role, "name": name})
        if resolved > 1:
            ambiguous = True
            if sensitive:
                raise TargetError(
                    "AMBIGUOUS_SENSITIVE_TARGET",
                    "selector resolves to multiple sensitive targets",
                    details={"count": resolved},
                )
            raise TargetError(
                "AMBIGUOUS_TARGET",
                f"selector resolves to {resolved} elements",
                details={"count": resolved},
            )
        label = matches[0].get("name") or matches[0].get("label") or label
        sensitive = sensitive or bool(matches[0].get("sensitive"))

    t = TargetSpec(
        selector=selector, role=role, name=name, test_id=test_id,
        resolved_count=resolved, resolved_label=redact_text(label, maxlen=80),
        ambiguous=ambiguous, sensitive=sensitive, origin=origin,
        page_fingerprint=page_fingerprint,
    )
    t.compute_digest()
    if not preferred and selector.startswith("//") or selector.startswith("xpath="):
        # xpath allowed but recorded
        pass
    return t


@dataclass
class InteractiveResult:
    status: str  # succeeded | denied | failed | approval_required | handoff | uncertain
    session_id: str = ""
    action_id: str = ""
    action_type: str = ""
    action_class: str = ""
    execution_id: str = ""
    handoff_id: str = ""
    checkpoint_id: str = ""
    summary: str = ""
    failure_category: str = ""
    evidence_id: str = ""
    page_url: str = ""
    page_origin: str = ""
    details: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "status": self.status,
            "session_id": self.session_id,
            "action_id": self.action_id,
            "action_type": self.action_type,
            "action_class": self.action_class,
            "execution_id": self.execution_id,
            "handoff_id": self.handoff_id,
            "checkpoint_id": self.checkpoint_id,
            "summary": self.summary,
            "failure_category": self.failure_category,
            "evidence_id": self.evidence_id,
            "page_url": self.page_url,
            "page_origin": self.page_origin,
            "details": self.details,
        }


class InteractiveBrowser:
    """Canonical interactive browser API (sessions + actions + handoffs)."""

    def __init__(
        self,
        *,
        store: BrowserSessionStore | None = None,
        governed: GovernedBrowser | None = None,
        boundary: UniversalBoundary | None = None,
        workspace: Path | str | None = None,
        allowed_hosts: Optional[list[str]] = None,
        mode: str = "fake",
        environment: str = "dev",
        production_adapter=None,
        evidence_pipeline=None,
        human_mac_adapter=None,
        browser_monitor=None,
    ):
        self.store = store or default_session_store()
        self.environment = environment
        self.allowed_hosts = allowed_hosts
        # M17.26 production adapter (sandbox by default — never live user browser in tests)
        if production_adapter is not None:
            self.production_adapter = production_adapter
        else:
            from saathi.browser.production_adapter import ProductionBrowserAdapter
            from saathi.browser.domain_policy import DomainPolicyService
            self.production_adapter = ProductionBrowserAdapter(
                allow_live=False,
                domain_policy=DomainPolicyService.for_environment(
                    environment, allowed_hosts=allowed_hosts,
                ),
            )
        if evidence_pipeline is not None:
            self.evidence = evidence_pipeline
        else:
            from saathi.browser.evidence_redaction import EvidenceRedactionPipeline
            self.evidence = EvidenceRedactionPipeline()
        self.human_mac = human_mac_adapter
        if browser_monitor is not None:
            self.monitor = browser_monitor
        else:
            from saathi.browser.adapter_monitor import default_browser_monitor
            self.monitor = default_browser_monitor()
        if governed is not None:
            self.gb = governed
            # Ensure interactive path can use production adapter when bound
            if getattr(self.gb.adapter, "bind_production_adapter", None):
                self.gb.adapter.bind_production_adapter(self.production_adapter)
            elif getattr(self.gb.adapter, "_production_adapter", None) is None:
                try:
                    self.gb.adapter._production_adapter = self.production_adapter
                except Exception:
                    pass
        else:
            adapter = BrowserAdapter(
                mode=mode, workspace=workspace, allowed_hosts=allowed_hosts,
                production_adapter=self.production_adapter,
            )
            if boundary is not None:
                self.gb = GovernedBrowser(
                    boundary=boundary, adapter=adapter, mode=mode,
                    workspace=workspace, allowed_hosts=allowed_hosts,
                )
            else:
                self.gb = GovernedBrowser(
                    adapter=adapter, mode=mode, workspace=workspace,
                    allowed_hosts=allowed_hosts,
                )
        # page element registry for fake target resolution
        self._page_elements: dict[str, list[dict]] = {}

    def set_page_elements(self, session_id: str, elements: list[dict]) -> None:
        self._page_elements[session_id] = list(elements)

    # ── session lifecycle ─────────────────────────────────────────────────
    def open_session(
        self,
        *,
        actor_id: str,
        mission_id: str = "",
        mission_run_id: str = "",
        request_source: str = "api",
        allowed_domains: list[str] | None = None,
        allowed_action_classes: list[str] | None = None,
        url: str = "",
        ttl_sec: float = 3600,
        worker: str = "",
        approval_scope: list[str] | None = None,
        risk_tier: str = "low",
    ) -> GovernedBrowserSession:
        domains = list(allowed_domains or self.allowed_hosts or [
            "example.com", "localhost", "127.0.0.1",
        ])
        classes = list(allowed_action_classes or [
            "read_only", "low_interactive", "sensitive_input", "external_effect",
        ])
        sess = self.store.create_session(
            actor_id=actor_id,
            mission_id=mission_id,
            mission_run_id=mission_run_id,
            request_source=request_source,
            browser_adapter=getattr(self.production_adapter, "adapter_type", None)
            or self.gb.adapter.mode,
            allowed_domains=domains,
            allowed_action_classes=classes,
            risk_tier=risk_tier,
            approval_scope=list(approval_scope or []),
            ttl_sec=ttl_sec,
            target_scope=origin_of(url) if url else "",
            lease_owner=worker or actor_id,
        )
        # M17.26: bind production adapter to governed session (sandbox attach)
        try:
            self.production_adapter.attach_session(
                sess.session_id,
                actor_id=actor_id,
                mission_id=mission_id,
                mission_run_id=mission_run_id,
                lease_owner=worker or actor_id,
                metadata={"request_source": request_source},
            )
            if url and hasattr(self.production_adapter, "configure_sandbox_page"):
                self.production_adapter.configure_sandbox_page(
                    sess.session_id, url, title="Session start",
                )
            # Also bind to gateway adapter for interactive dispatch
            if getattr(self.gb.adapter, "bind_production_adapter", None):
                self.gb.adapter.bind_production_adapter(self.production_adapter)
            else:
                self.gb.adapter._production_adapter = self.production_adapter
        except Exception:
            pass  # attach is best-effort for fake-only harnesses
        if url:
            # initial navigate through gateway
            res = self.act(
                session_id=sess.session_id,
                action="navigate",
                actor_id=actor_id,
                url=url,
                worker=worker or actor_id,
            )
            if res.status not in ("succeeded",):
                try:
                    self.store.transition(
                        sess.session_id, SessionStatus.FAILED,
                        reason=res.failure_category or res.status,
                    )
                except SessionError:
                    pass
            sess = self.store.require(sess.session_id)
        else:
            sess = self.store.transition(sess.session_id, SessionStatus.ACTIVE, reason="opened")
        return sess

    def close_session(
        self, session_id: str, *, actor_id: str, reason: str = "closed",
    ) -> GovernedBrowserSession:
        self.store.assert_access(session_id, actor_id=actor_id)
        s = self.store.require(session_id)
        if s.status_enum == SessionStatus.CLOSED:
            return s
        # path to closed: active → completed → closed or cancel → closed
        if s.status_enum not in (
            SessionStatus.COMPLETED, SessionStatus.CANCELLED, SessionStatus.FAILED,
            SessionStatus.EXPIRED,
        ):
            try:
                if s.status_enum in ACTIONABLE_SESSION or s.status_enum in (
                    SessionStatus.PAUSED_FOR_HUMAN, SessionStatus.PAUSED_FOR_APPROVAL,
                    SessionStatus.READY,
                ):
                    self.store.transition(
                        session_id, SessionStatus.COMPLETED, reason=reason,
                    )
            except SessionError:
                try:
                    self.store.transition(
                        session_id, SessionStatus.CANCELLED, reason=reason,
                    )
                except SessionError:
                    pass
        try:
            return self.store.transition(
                session_id, SessionStatus.CLOSED, reason=reason,
            )
        except SessionError:
            return self.store.require(session_id)

    def cancel_session(
        self, session_id: str, *, actor_id: str, reason: str = "cancelled",
    ) -> GovernedBrowserSession:
        self.store.assert_access(session_id, actor_id=actor_id)
        s = self.store.require(session_id)
        if s.status_enum in (SessionStatus.CLOSED, SessionStatus.CANCELLED):
            return s
        try:
            self.store.transition(session_id, SessionStatus.CANCELLED, reason=reason)
        except SessionError:
            pass
        try:
            return self.store.transition(session_id, SessionStatus.CLOSED, reason=reason)
        except SessionError:
            return self.store.require(session_id)

    # ── checkpoint / resume ───────────────────────────────────────────────
    def checkpoint(
        self, session_id: str, *, actor_id: str, metadata: dict | None = None,
    ) -> dict:
        s = self.store.assert_access(session_id, actor_id=actor_id)
        cp = self.store.create_checkpoint(
            session_id,
            mission_id=s.mission_id,
            mission_run_id=s.mission_run_id,
            page_url=s.current_url,
            page_origin=s.current_origin,
            page_fingerprint=s.page_fingerprint,
            page_title=s.page_title,
            metadata=metadata,
        )
        if s.status_enum == SessionStatus.ACTIVE:
            try:
                self.store.transition(
                    session_id, SessionStatus.CHECKPOINTED,
                    reason="checkpoint",
                    extra={"checkpoint_reference": cp["checkpoint_id"]},
                )
            except SessionError:
                self.store.touch(session_id, checkpoint_reference=cp["checkpoint_id"])
        else:
            self.store.touch(session_id, checkpoint_reference=cp["checkpoint_id"])
        return cp

    def resume(
        self,
        session_id: str,
        *,
        actor_id: str,
        checkpoint_reference: str = "",
        worker: str = "",
        expected_origin: str = "",
        expected_fingerprint: str = "",
    ) -> InteractiveResult:
        s = self.store.assert_access(
            session_id, actor_id=actor_id, worker=worker or actor_id,
        )
        cp_id = checkpoint_reference or s.checkpoint_reference
        if not cp_id:
            return InteractiveResult(
                status="denied", session_id=session_id,
                failure_category="checkpoint_required",
                summary="resume requires a valid checkpoint_reference",
            )
        cp = self.store.get_checkpoint(cp_id)
        if not cp or not str(cp.get("status", "")).startswith("valid"):
            return InteractiveResult(
                status="denied", session_id=session_id,
                failure_category="checkpoint_invalid",
                summary="checkpoint missing or invalid",
            )
        if cp["session_id"] != session_id:
            return InteractiveResult(
                status="denied", session_id=session_id,
                failure_category="checkpoint_session_mismatch",
                summary="checkpoint does not belong to this session",
            )
        if expected_origin and cp.get("page_origin") and expected_origin != cp["page_origin"]:
            return InteractiveResult(
                status="denied", session_id=session_id,
                failure_category="page_state_mismatch",
                summary="page origin mismatch on resume",
            )
        if expected_fingerprint and cp.get("page_fingerprint") and \
                expected_fingerprint != cp["page_fingerprint"]:
            return InteractiveResult(
                status="denied", session_id=session_id,
                failure_category="page_state_mismatch",
                summary="page fingerprint mismatch on resume",
            )
        # re-evaluate policy domain still allowed
        if cp.get("page_origin"):
            dom = check_domain(
                cp["page_origin"] + "/",
                allowed_hosts=s.allowed_domains or self.allowed_hosts,
            )
            if not dom.allowed:
                return InteractiveResult(
                    status="denied", session_id=session_id,
                    failure_category=dom.reason,
                    summary=f"resume domain denied: {dom.reason}",
                )
        try:
            if s.status_enum in (
                SessionStatus.PAUSED_FOR_HUMAN, SessionStatus.CHECKPOINTED,
            ):
                self.store.transition(session_id, SessionStatus.RESUMING, reason="resume")
            self.store.acquire_lease(session_id, worker or actor_id)
            self.store.transition(session_id, SessionStatus.ACTIVE, reason="resumed")
        except SessionError as e:
            return InteractiveResult(
                status="denied", session_id=session_id,
                failure_category=e.code.lower(), summary=e.message,
            )
        return InteractiveResult(
            status="succeeded", session_id=session_id,
            checkpoint_id=cp_id, action_type="resume",
            summary="session resumed from checkpoint",
            page_url=cp.get("page_url", ""), page_origin=cp.get("page_origin", ""),
        )

    # ── human handoff ─────────────────────────────────────────────────────
    def request_handoff(
        self,
        session_id: str,
        *,
        actor_id: str,
        reason: str,
        required_human_action: str = "",
        allowed_scope: list[str] | None = None,
        ttl_sec: float = 1800,
    ) -> InteractiveResult:
        s = self.store.assert_access(session_id, actor_id=actor_id)
        # create checkpoint first
        cp = self.checkpoint(session_id, actor_id=actor_id, metadata={"handoff_reason": reason})
        try:
            self.store.release_lease(session_id, s.lease_owner or actor_id)
        except SessionError:
            pass
        if s.status_enum in ACTIONABLE_SESSION or s.status_enum == SessionStatus.CHECKPOINTED:
            try:
                self.store.transition(
                    session_id, SessionStatus.PAUSED_FOR_HUMAN,
                    reason=reason,
                    extra={
                        "checkpoint_reference": cp["checkpoint_id"],
                        "human_handoff_state": "awaiting_human",
                    },
                )
            except SessionError as e:
                return InteractiveResult(
                    status="denied", session_id=session_id,
                    failure_category=e.code.lower(), summary=e.message,
                )
        ho = self.store.create_handoff(
            session_id=session_id,
            reason=reason,
            required_human_action=required_human_action or reason,
            allowed_scope=allowed_scope or ["human_confirm"],
            requesting_actor=actor_id,
            mission_id=s.mission_id,
            mission_run_id=s.mission_run_id,
            checkpoint_reference=cp["checkpoint_id"],
            ttl_sec=ttl_sec,
        )
        return InteractiveResult(
            status="handoff",
            session_id=session_id,
            handoff_id=ho["handoff_id"],
            checkpoint_id=cp["checkpoint_id"],
            action_type="request_handoff",
            action_class=ActionClass.HANDOFF.value,
            summary=safe_summary(f"awaiting human: {reason}"),
            details={"resume_token_reference": ho.get("resume_token_reference", "")},
        )

    def claim_handoff(
        self, handoff_id: str, *, human_id: str,
    ) -> dict:
        ho = self.store.get_handoff(handoff_id)
        if not ho:
            raise SessionError("UNKNOWN_HANDOFF", f"unknown handoff {handoff_id}")
        if ho["status"] not in ("awaiting_human", "requested"):
            raise SessionError("HANDOFF_STATE", f"handoff not claimable: {ho['status']}")
        if ho["expires_at"] and time.time() > float(ho["expires_at"]):
            self.store.update_handoff(handoff_id, status="expired", resolved_at=time.time())
            raise SessionError("HANDOFF_EXPIRED", "handoff expired")
        # prevent dual claim
        active = self.store.active_handoff_for_session(ho["session_id"])
        if active and active["handoff_id"] != handoff_id and active.get("assigned_human"):
            raise SessionError("HANDOFF_CONFLICT", "another handoff is already claimed")
        return self.store.update_handoff(
            handoff_id, status="claimed", assigned_human=human_id,
        )

    def complete_handoff(
        self,
        handoff_id: str,
        *,
        human_id: str,
        resolution: str = "completed",
        decline: bool = False,
    ) -> InteractiveResult:
        ho = self.store.get_handoff(handoff_id)
        if not ho:
            return InteractiveResult(
                status="denied", failure_category="unknown_handoff",
                summary="unknown handoff",
            )
        if ho["expires_at"] and time.time() > float(ho["expires_at"]):
            self.store.update_handoff(handoff_id, status="expired", resolved_at=time.time())
            return InteractiveResult(
                status="denied", handoff_id=handoff_id,
                failure_category="handoff_expired", summary="handoff expired",
            )
        if ho.get("assigned_human") and ho["assigned_human"] != human_id:
            return InteractiveResult(
                status="denied", handoff_id=handoff_id,
                failure_category="handoff_owner",
                summary="handoff claimed by another human",
            )
        status = "declined" if decline else "completed"
        self.store.update_handoff(
            handoff_id, status=status, resolution=resolution,
            resolved_at=time.time(), assigned_human=human_id,
        )
        sid = ho["session_id"]
        if decline:
            try:
                self.store.transition(sid, SessionStatus.CANCELLED, reason="handoff_declined")
            except SessionError:
                pass
            return InteractiveResult(
                status="denied", session_id=sid, handoff_id=handoff_id,
                failure_category="handoff_declined", summary=resolution,
            )
        self.store.update_handoff(handoff_id, status="resume_pending")
        self.store.touch(sid, human_handoff_state="resume_pending")
        owner = ho.get("requesting_actor") or human_id
        # resume re-evaluates policy; return lease to owning actor after human step
        res = self.resume(
            sid,
            actor_id=owner,
            checkpoint_reference=ho.get("checkpoint_reference") or "",
            worker=owner,
        )
        try:
            self.store.acquire_lease(sid, owner, ttl_sec=300)
        except SessionError:
            pass
        self.store.update_handoff(handoff_id, status="resumed")
        res.handoff_id = handoff_id
        res.action_type = "complete_handoff"
        return res

    # ── core act() ────────────────────────────────────────────────────────
    def act(
        self,
        *,
        session_id: str,
        action: str,
        actor_id: str,
        url: str = "",
        selector: str = "",
        role: str = "",
        name: str = "",
        test_id: str = "",
        text: str = "",
        file_path: str = "",
        payload: Optional[dict] = None,
        expected_effect: str = "",
        expected_page_state: str = "",
        approval_id: str = "",
        approval_pre_resolved: bool = False,
        approval_scope_action: str = "",
        idempotency_key: str = "",
        action_id: str = "",
        worker: str = "",
        retry_attempt: int = 0,
        retry_authorized: bool = True,
        trading_authorized: bool = False,
        force_new: bool = False,
        timeout: int = 30,
    ) -> InteractiveResult:
        aid = action_id or f"bact-{uuid.uuid4().hex[:14]}"
        aclass = action_class_of(action)
        action_key = str(action).strip().lower().replace("-", "_")

        # lifecycle shortcuts
        if action_key == "close_session":
            self.close_session(session_id, actor_id=actor_id)
            return InteractiveResult(
                status="succeeded", session_id=session_id, action_id=aid,
                action_type=action_key, action_class=aclass.value,
                summary="session closed",
            )
        if action_key == "checkpoint":
            cp = self.checkpoint(session_id, actor_id=actor_id)
            return InteractiveResult(
                status="succeeded", session_id=session_id, action_id=aid,
                action_type="checkpoint", action_class=aclass.value,
                checkpoint_id=cp["checkpoint_id"], summary="checkpoint created",
            )
        if action_key == "request_handoff":
            return self.request_handoff(
                session_id, actor_id=actor_id,
                reason=(payload or {}).get("reason") or expected_effect or "human_required",
            )

        # Idempotent replay for terminal prior results (before session status gates)
        if idempotency_key:
            prior_early = self.store.find_action_by_idempotency(idempotency_key)
            if prior_early and prior_early.get("session_id") == session_id:
                if prior_early["status"] in ("succeeded", "failed", "uncertain", "denied"):
                    return InteractiveResult(
                        status=prior_early["status"],
                        session_id=session_id,
                        action_id=prior_early["action_id"],
                        action_type=prior_early["action_type"],
                        action_class=prior_early["action_class"],
                        execution_id=prior_early.get("execution_id") or "",
                        summary=prior_early.get("result_summary") or "idempotent replay",
                        failure_category=prior_early.get("failure_category") or "",
                        details={"idempotent": True},
                    )
                if prior_early["status"] in ("pending", "executing"):
                    return InteractiveResult(
                        status="uncertain",
                        session_id=session_id,
                        action_id=prior_early["action_id"],
                        action_type=action_key,
                        summary="prior attempt still pending; not re-executed",
                        failure_category="outcome_uncertain",
                        details={"idempotent": True},
                    )

        # session ownership
        try:
            s = self.store.assert_access(
                session_id, actor_id=actor_id,
                mission_id="",  # optional unless caller passes via store fields
                worker=worker or actor_id,
            )
            if s.status_enum == SessionStatus.PAUSED_FOR_HUMAN:
                return InteractiveResult(
                    status="denied", session_id=session_id, action_id=aid,
                    failure_category="paused_for_human",
                    summary="session paused for human; complete handoff before acting",
                )
            # PAUSED_FOR_APPROVAL may proceed only when a dedicated approval is supplied
            if s.status_enum == SessionStatus.PAUSED_FOR_APPROVAL:
                if not (approval_id or approval_pre_resolved):
                    return InteractiveResult(
                        status="approval_required", session_id=session_id, action_id=aid,
                        action_type=action_key, action_class=aclass.value,
                        failure_category="approval_required",
                        summary="session paused for approval; provide approval_id to continue",
                    )
                self.store.transition(
                    session_id, SessionStatus.ACTIVE, reason="approval_provided",
                )
                s = self.store.require(session_id)
            elif s.status_enum == SessionStatus.RECONCILIATION_REQUIRED:
                return InteractiveResult(
                    status="denied", session_id=session_id, action_id=aid,
                    failure_category="reconciliation_required",
                    summary="session requires reconciliation before new actions",
                )
            elif s.status_enum not in ACTIONABLE_SESSION and s.status_enum != SessionStatus.READY:
                return InteractiveResult(
                    status="denied", session_id=session_id, action_id=aid,
                    failure_category="session_not_actionable",
                    summary=f"session status {s.status} cannot accept actions",
                )
            self.store.acquire_lease(session_id, worker or actor_id)
            if s.status_enum == SessionStatus.READY:
                self.store.transition(session_id, SessionStatus.ACTIVE, reason="first_action")
        except SessionError as e:
            return InteractiveResult(
                status="denied", session_id=session_id, action_id=aid,
                action_type=action_key, action_class=aclass.value,
                failure_category=e.code.lower(), summary=e.message,
            )

        s = self.store.require(session_id)

        # class scope
        if aclass.value not in (s.allowed_action_classes or []) and aclass not in (
            ActionClass.LIFECYCLE, ActionClass.HANDOFF,
        ):
            return InteractiveResult(
                status="denied", session_id=session_id, action_id=aid,
                action_type=action_key, action_class=aclass.value,
                failure_category="action_class_not_allowed",
                summary=f"action class {aclass.value} not in session allowed_action_classes",
            )

        # prohibited
        if aclass == ActionClass.PROHIBITED:
            return InteractiveResult(
                status="denied", session_id=session_id, action_id=aid,
                action_type=action_key, action_class=aclass.value,
                failure_category="prohibited_action",
                summary=f"action {action_key} is prohibited",
            )

        # financial → Trading Guardian
        if aclass == ActionClass.FINANCIAL and not trading_authorized:
            return InteractiveResult(
                status="denied", session_id=session_id, action_id=aid,
                action_type=action_key, action_class=aclass.value,
                failure_category="trading_guardian_required",
                summary="financial browser action requires Trading Guardian authorization",
            )

        # domain (M17.26 environment-aware)
        target_url = url or s.current_url or (s.current_origin + "/" if s.current_origin else "")
        if target_url:
            dom = check_domain(
                target_url,
                allowed_hosts=s.allowed_domains or self.allowed_hosts,
                environment=self.environment,
            )
            if not dom.allowed:
                try:
                    self.monitor.record_domain_denial(
                        session_id=session_id, actor_id=actor_id,
                        mission_id=s.mission_id, mission_run_id=s.mission_run_id,
                        message=f"domain denied: {dom.reason}",
                        error_category=dom.reason,
                    )
                except Exception:
                    pass
                return InteractiveResult(
                    status="denied", session_id=session_id, action_id=aid,
                    action_type=action_key, failure_category=dom.reason,
                    summary=f"domain denied: {dom.reason}",
                )
            # session target scope — exact or subdomain-of listed root only
            if s.allowed_domains:
                host_ok = any(
                    dom.host == d.lstrip(".").rstrip(".")
                    or dom.host.endswith("." + d.lstrip(".").rstrip("."))
                    for d in s.allowed_domains
                ) if dom.host else False
                if not host_ok and dom.host:
                    return InteractiveResult(
                        status="denied", session_id=session_id, action_id=aid,
                        action_type=action_key, failure_category="outside_session_scope",
                        summary="target outside session allowed_domains",
                    )

        # target resolution
        try:
            target = resolve_target(
                selector=selector, role=role, name=name, test_id=test_id,
                origin=origin_of(target_url) if target_url else s.current_origin,
                page_fingerprint=s.page_fingerprint,
                page_elements=self._page_elements.get(session_id),
            )
        except TargetError as e:
            return InteractiveResult(
                status="denied", session_id=session_id, action_id=aid,
                action_type=action_key, failure_category=e.code.lower(),
                summary=e.message, details=e.details,
            )

        sensitive = target.sensitive or is_sensitive_target(selector, name)
        if sensitive and aclass == ActionClass.LOW_INTERACTIVE:
            aclass = ActionClass.SENSITIVE_INPUT

        # Navigation approval does NOT cover interactive/commit actions
        nav_only_scope = set(s.approval_scope or []) == {"navigate"} or (
            approval_scope_action == "navigate"
        )
        needs_appr = requires_approval_for_class(
            aclass, environment=self.environment, sensitive_field=sensitive,
        ) or action_key in COMMIT_ACTIONS

        # Explicit: navigate approval scope cannot authorize commit/sensitive
        if needs_appr and not approval_id and not approval_pre_resolved:
            if action_key in COMMIT_ACTIONS or aclass in (
                ActionClass.EXTERNAL_EFFECT, ActionClass.SENSITIVE_INPUT, ActionClass.FINANCIAL,
            ):
                # record approval pending
                try:
                    if s.status_enum == SessionStatus.ACTIVE:
                        self.store.transition(
                            session_id, SessionStatus.PAUSED_FOR_APPROVAL,
                            reason=f"approval_required:{action_key}",
                        )
                except SessionError:
                    pass
                return InteractiveResult(
                    status="approval_required",
                    session_id=session_id, action_id=aid,
                    action_type=action_key, action_class=aclass.value,
                    failure_category="approval_required",
                    summary=(
                        f"{action_key} requires dedicated approval; "
                        "navigation approval does not authorize this action"
                    ),
                )

        if approval_id and nav_only_scope and action_key in COMMIT_ACTIONS:
            return InteractiveResult(
                status="denied", session_id=session_id, action_id=aid,
                action_type=action_key, action_class=aclass.value,
                failure_category="approval_scope_mismatch",
                summary="navigate-scoped approval cannot authorize commit actions",
            )

        # idempotency for state-changing
        state_changing = aclass not in (ActionClass.READ_ONLY, ActionClass.LIFECYCLE)
        idem = idempotency_key
        if state_changing and not idem and action_key in COMMIT_ACTIONS:
            return InteractiveResult(
                status="denied", session_id=session_id, action_id=aid,
                action_type=action_key, action_class=aclass.value,
                failure_category="idempotency_required",
                summary="high-risk / commit actions require idempotency_key",
            )
        if idem:
            prior = self.store.find_action_by_idempotency(idem)
            if prior:
                if prior["status"] in ("succeeded", "failed", "uncertain", "denied"):
                    return InteractiveResult(
                        status=prior["status"] if prior["status"] != "uncertain" else "uncertain",
                        session_id=session_id,
                        action_id=prior["action_id"],
                        action_type=prior["action_type"],
                        action_class=prior["action_class"],
                        execution_id=prior.get("execution_id") or "",
                        summary=prior.get("result_summary") or "idempotent replay",
                        failure_category=prior.get("failure_category") or "",
                        details={"idempotent": True},
                    )
                if prior["status"] in ("pending", "executing"):
                    return InteractiveResult(
                        status="uncertain",
                        session_id=session_id,
                        action_id=prior["action_id"],
                        action_type=action_key,
                        summary="prior attempt still pending; not re-executed",
                        failure_category="outcome_uncertain",
                        details={"idempotent": True},
                    )

        # pre-commit checkpoint for external effects
        checkpoint_id = ""
        if action_key in COMMIT_ACTIONS:
            cp = self.checkpoint(
                session_id, actor_id=actor_id,
                metadata={"pre_commit": action_key, "target_digest": target.digest},
            )
            checkpoint_id = cp["checkpoint_id"]
            # return to active for execution
            try:
                if self.store.require(session_id).status_enum == SessionStatus.CHECKPOINTED:
                    self.store.transition(session_id, SessionStatus.ACTIVE, reason="pre_commit_exec")
            except SessionError:
                pass

        # record pending action
        safe_payload = {
            k: ("***REDACTED***" if sensitive and k in ("text", "value", "password") else v)
            for k, v in (payload or {}).items()
        }
        if text and sensitive:
            safe_payload["text_digest"] = hashlib.sha256(text.encode()).hexdigest()[:16]
        elif text:
            safe_payload["text_len"] = len(text)

        self.store.record_action(
            action_id=aid,
            session_id=session_id,
            actor_id=actor_id,
            action_type=action_key,
            action_class=aclass.value,
            status="executing",
            mission_id=s.mission_id,
            mission_run_id=s.mission_run_id,
            idempotency_key=idem or "",
            target=target.resolved_label or selector,
            target_digest=target.digest,
            expected_effect=expected_effect,
            approval_id=approval_id,
            payload_meta={
                "expected_page_state": expected_page_state,
                "sensitive": sensitive,
                **safe_payload,
            },
        )

        # Map to gateway-compatible BrowserAction where possible
        gw_action = action_key
        if action_key in ("hover", "expand", "open_menu", "switch_tab", "select_filter",
                          "dismiss_dialog", "select", "select_option", "check", "uncheck"):
            gw_action = "click" if action_key != "dismiss_dialog" else "click"
        if action_key in ("scroll", "wait", "inspect_dom", "snapshot", "read_metadata"):
            gw_action = "read"
        if action_key in ("send_message", "publish", "confirm", "accept_terms", "book"):
            gw_action = "submit"
        if action_key in ("enter_pii", "enter_payment_info"):
            gw_action = "fill"
        if action_key == "paste_clipboard":
            gw_action = "fill"

        # upload path check
        if action_key == "upload" and file_path:
            ws = str(self.gb.adapter.workspace)
            if not path_is_inside(file_path, ws):
                self.store.update_action(
                    aid, status="denied", failure_category="upload_path_denied",
                    result_summary="upload path outside workspace",
                )
                return InteractiveResult(
                    status="denied", session_id=session_id, action_id=aid,
                    action_type=action_key, failure_category="upload_path_denied",
                    summary="upload path outside workspace",
                )

        # M17.26: evidence classification before action (metadata only; no secrets)
        evidence_id = ""
        try:
            ev = self.evidence.capture(
                session_id=session_id,
                action_id=aid,
                mission_run_id=s.mission_run_id or session_id,
                evidence_type="screenshot",
                image_bytes=b"" if sensitive or aclass == ActionClass.FINANCIAL else b"pre-action-stub",
                action_type=action_key,
                action_class=aclass.value,
                selector=selector,
                field_name=name,
                page_elements=self._page_elements.get(session_id),
                mission_sensitivity=s.sensitivity_classification or "general",
                trading_classified=(aclass == ActionClass.FINANCIAL),
            )
            evidence_id = ev.evidence_id
            if ev.suppression_reason == "redaction_failed" and aclass in (
                ActionClass.SENSITIVE_INPUT, ActionClass.FINANCIAL, ActionClass.EXTERNAL_EFFECT,
            ):
                try:
                    self.monitor.record_redaction_failure(
                        session_id=session_id, actor_id=actor_id,
                        mission_id=s.mission_id, message="redaction failed; fail closed",
                        error_category="redaction_failed",
                    )
                except Exception:
                    pass
                self.store.update_action(
                    aid, status="failed", failure_category="redaction_failed",
                    result_summary="sensitive evidence redaction failed",
                )
                return InteractiveResult(
                    status="failed", session_id=session_id, action_id=aid,
                    action_type=action_key, action_class=aclass.value,
                    failure_category="redaction_failed",
                    summary="sensitive evidence redaction failed; action blocked",
                    evidence_id=evidence_id,
                )
        except Exception:
            evidence_id = ""

        # execute via governed gateway (production adapter bound for interactive)
        try:
            rec: ExecutionRecord = self.gb.execute(
                action=gw_action,
                url=target_url or "https://example.com/",
                actor=actor_id,
                session_id=session_id,  # governed session id as technical key
                selector=selector or target.resolved_label,
                payload={
                    **(payload or {}),
                    "text": "***REDACTED***" if sensitive else text,
                    "expected_effect": expected_effect,
                    "target_digest": target.digest,
                    "action_class": aclass.value,
                    "action_id": aid,
                    "actor_id": actor_id,
                    "mission_id": s.mission_id,
                    "mission_run_id": s.mission_run_id,
                    "lease_owner": worker or actor_id,
                    "page_fingerprint": s.page_fingerprint,
                    "trading_authorized": trading_authorized,
                },
                file_path=file_path,
                environment=self.environment,
                approval_id=approval_id,
                approval_pre_resolved=approval_pre_resolved or bool(approval_id),
                force_new=force_new,
                idempotency_key=idem or "",
                mission_id=s.mission_id or "browser",
                mission_run_id=s.mission_run_id or session_id,
                request_source=s.request_source or "interactive",
                retry_attempt=retry_attempt,
                retry_authorized=retry_authorized,
                checkpoint_reference=checkpoint_id or s.checkpoint_reference,
                trading_classified=(aclass == ActionClass.FINANCIAL),
                trading_authorized=trading_authorized,
            )
        except Exception as e:
            self.store.update_action(
                aid, status="failed", failure_category="gateway_error",
                result_summary=redact_text(str(e)),
            )
            return InteractiveResult(
                status="failed", session_id=session_id, action_id=aid,
                action_type=action_key, action_class=aclass.value,
                failure_category="gateway_error", summary=redact_text(str(e)),
            )

        st = rec.status
        if st == ExecutionState.SUCCEEDED.value:
            final_status = "succeeded"
        elif st == ExecutionState.APPROVAL_REQUIRED.value:
            final_status = "approval_required"
        elif st == ExecutionState.DENIED.value:
            final_status = "denied"
        elif rec.failure_category == "outcome_uncertain":
            final_status = "uncertain"
        else:
            final_status = "failed"

        # update page state from adapter fake pages when navigate
        page_url = target_url
        page_origin = origin_of(target_url) if target_url else s.current_origin
        if action_key in ("navigate", "open") and final_status == "succeeded":
            fp = hashlib.sha256((page_url or "").encode()).hexdigest()[:16]
            self.store.touch(
                session_id,
                current_url=page_url,
                current_origin=page_origin,
                page_title=redact_text(rec.result_summary or "", maxlen=80),
                page_fingerprint=fp,
                status=SessionStatus.ACTIVE.value if self.store.require(session_id).status_enum
                in (SessionStatus.READY, SessionStatus.CHECKPOINTED, SessionStatus.RESUMING,
                    SessionStatus.PAUSED_FOR_APPROVAL) else None,
            )
            # ensure active
            try:
                cur = self.store.require(session_id)
                if cur.status_enum in (SessionStatus.READY, SessionStatus.PAUSED_FOR_APPROVAL):
                    self.store.transition(session_id, SessionStatus.ACTIVE, reason="navigate_ok")
                elif cur.status_enum == SessionStatus.CHECKPOINTED:
                    self.store.transition(session_id, SessionStatus.ACTIVE, reason="navigate_ok")
            except SessionError:
                pass

        if final_status == "uncertain":
            try:
                self.store.transition(
                    session_id, SessionStatus.RECONCILIATION_REQUIRED,
                    reason="outcome_uncertain",
                    extra={"reconciliation_status": "pending"},
                )
            except SessionError:
                self.store.touch(session_id, reconciliation_status="pending")
            try:
                self.monitor.record_uncertain(
                    session_id=session_id, actor_id=actor_id,
                    mission_id=s.mission_id, mission_run_id=s.mission_run_id,
                    message="uncertain external effect; no blind retry",
                    error_category="outcome_uncertain",
                )
            except Exception:
                pass

        if final_status == "succeeded" and s.status_enum == SessionStatus.PAUSED_FOR_APPROVAL:
            try:
                self.store.transition(session_id, SessionStatus.ACTIVE, reason="approved_exec")
            except SessionError:
                pass

        # Sync page state from production adapter when available
        try:
            b = self.production_adapter.get_binding(session_id)
            if b and b.active_page_id and b.pages.get(b.active_page_id):
                pg = b.pages[b.active_page_id]
                if pg.url and action_key in ("navigate", "open") and final_status == "succeeded":
                    page_url = pg.url
                    page_origin = pg.origin or origin_of(pg.url)
        except Exception:
            pass

        self.store.update_action(
            aid,
            status=final_status,
            result_summary=safe_summary(rec.result_summary or final_status),
            failure_category=rec.failure_category or "",
            execution_id=rec.execution_id,
        )

        return InteractiveResult(
            status=final_status,
            session_id=session_id,
            action_id=aid,
            action_type=action_key,
            action_class=aclass.value,
            execution_id=rec.execution_id,
            checkpoint_id=checkpoint_id,
            summary=safe_summary(rec.result_summary or final_status),
            failure_category=rec.failure_category or "",
            evidence_id=evidence_id,
            page_url=page_url or "",
            page_origin=page_origin or "",
            details={
                "target_digest": target.digest,
                "sensitive": sensitive,
                "gateway_status": st,
                "adapter_id": getattr(self.production_adapter, "adapter_id", ""),
                "raw_page_exposed": False,
            },
        )


# ── process helpers ──────────────────────────────────────────────────────────

_IB: Optional[InteractiveBrowser] = None


def default_interactive_browser(**kwargs) -> InteractiveBrowser:
    global _IB
    if kwargs:
        return InteractiveBrowser(**kwargs)
    if _IB is None:
        _IB = InteractiveBrowser(mode="fake")
    return _IB


def reset_interactive_browser() -> None:
    global _IB
    _IB = None
    reset_session_store()
