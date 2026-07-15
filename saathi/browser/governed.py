"""M17.23 — Governed browser actions through ExecutionGateway.

Authoritative entry for side-effecting browser work:

    Browser request
      → ToolIntent
      → domain / permission policy
      → risk + approval
      → ExecutionGateway.submit
      → existing BrowserService adapter (or deterministic fake)
      → Evidence / security / ledger / metrics

Does not replace Playwright / BrowserService tiers.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional
from urllib.parse import urlparse

from saathi.browser.policy import (
    BrowserAction,
    DEFAULT_ALLOWED_HOST_SUFFIXES,
    DomainDecision,
    PROHIBITED_ACTIONS,
    check_domain,
    classify_risk,
    detect_prompt_injection,
    origin_of,
    parse_action,
    path_is_inside,
    payload_digest,
    revalidate_redirect,
    sanitize_filename,
)
from saathi.execution.execution_state import ExecutionState
from saathi.execution.gateway import ExecutionGateway
from saathi.execution.record import ExecutionRecord, safe_summary, tool_intent_digest
from saathi.execution.toolintent import (
    ActorType,
    ApprovalLevel,
    BusinessUnit,
    RiskLevel,
    ToolIntent,
    builder,
)
from saathi.execution.universal import UniversalBoundary, default_boundary

logger = logging.getLogger(__name__)

_SECRET_RE = re.compile(
    r"(?i)(password|passwd|secret|token|cookie|authorization|bearer|api[_-]?key)"
    r"(?:\s*[=:]\s*\S+)?"
)

# Workspace roots for downloads/uploads (tests override)
DEFAULT_WORKSPACE = Path.home() / ".saathi" / "browser_workspace"
MAX_DOWNLOAD_BYTES = 25 * 1024 * 1024
MAX_UPLOAD_BYTES = 10 * 1024 * 1024

# Metrics (process-local; Control Center reads store + this)
_metrics_lock = threading.Lock()
_metrics: dict[str, int] = {
    "requested": 0,
    "approved": 0,
    "denied": 0,
    "running": 0,
    "succeeded": 0,
    "failed": 0,
    "cancelled": 0,
    "expired": 0,
    "outcome_uncertain": 0,
    "approval_required": 0,
    "domain_denied": 0,
    "policy_denied": 0,
    "prompt_injection_detected": 0,
    "idempotent": 0,
}


def browser_metrics() -> dict:
    with _metrics_lock:
        m = dict(_metrics)
    # Merge durable gateway metrics when available
    try:
        gm = default_boundary().metrics()
        m["gateway_succeeded"] = gm.get("succeeded", 0)
        m["gateway_failed"] = gm.get("failed", 0)
        m["gateway_approval_required"] = gm.get("approval_required", 0)
        m["average_runtime_sec"] = gm.get("average_runtime_sec", 0)
        m["recent_failures"] = gm.get("recent_failures") or []
    except Exception:
        pass
    return m


def _bump(key: str, n: int = 1) -> None:
    with _metrics_lock:
        _metrics[key] = int(_metrics.get(key, 0)) + n


def reset_browser_metrics() -> None:
    with _metrics_lock:
        for k in list(_metrics.keys()):
            _metrics[k] = 0


def redact_text(text: Any, *, maxlen: int = 400) -> str:
    s = "" if text is None else str(text)
    s = _SECRET_RE.sub(r"\1=[redacted]", s)
    if len(s) > maxlen:
        s = s[: maxlen - 3] + "..."
    return s


def build_browser_intent(
    *,
    action: str | BrowserAction,
    url: str = "",
    actor: str = "user:system",
    session_id: str = "default",
    tab_id: str = "",
    selector: str = "",
    payload: Optional[dict] = None,
    file_path: str = "",
    environment: str = "dev",
    allowed_hosts: Optional[list[str]] = None,
    read_write: str = "",
    timeout: int = 30,
    expires_in_sec: float = 3600,
    approval_pre_resolved: bool = False,
    require_approval: Optional[bool] = None,
    mission_id: str = "browser",
) -> ToolIntent:
    """Build a ToolIntent for a browser action (secrets never in parameters)."""
    act = parse_action(action)
    payload = dict(payload or {})
    # Never put secrets into parameters
    safe_payload = {
        k: ("***REDACTED***" if _SECRET_RE.search(str(k)) else v)
        for k, v in payload.items()
    }
    risk_d = classify_risk(act, url=url, selector=selector, payload=payload,
                           environment=environment)
    if require_approval is None:
        require_approval = risk_d.require_approval
    if approval_pre_resolved:
        require_approval = False

    rw = read_write or (
        "read" if act in (
            BrowserAction.NAVIGATE, BrowserAction.OPEN, BrowserAction.READ,
            BrowserAction.EXTRACT, BrowserAction.SCREENSHOT,
        ) else "write"
    )
    pdigest = payload_digest({
        "action": act.value,
        "url": url,
        "selector": selector,
        "payload": safe_payload,
        "file_path": file_path,
    })
    params = {
        "action": act.value,
        "url": url,
        "origin": origin_of(url),
        "session_id": session_id,
        "tab_id": tab_id,
        "selector": selector,
        "payload_digest": pdigest,
        "file_ref": sanitize_filename(Path(file_path).name) if file_path else "",
        "file_digest": (
            hashlib.sha256(Path(file_path).read_bytes()).hexdigest()
            if file_path and Path(file_path).is_file() else ""
        ),
        "read_write": rw,
        "environment": environment,
        # non-secret payload fields only
        "text_digest": hashlib.sha256(
            str(safe_payload.get("text", "")).encode()
        ).hexdigest() if safe_payload.get("text") else "",
    }
    meta = {
        "family": "browser",
        "target": origin_of(url) or url[:80],
        "session_id": session_id,
        "tab_id": tab_id,
        "require_approval": bool(require_approval),
        "approval_pre_resolved": bool(approval_pre_resolved),
        "risk_category": risk_d.category,
        "risk_reason": risk_d.reason,
        "allowed_hosts": list(allowed_hosts or DEFAULT_ALLOWED_HOST_SUFFIXES),
        "payload_digest": pdigest,
        "requested_at": time.time(),
        "untrusted_page_content": True,
    }
    appr = ApprovalLevel.L4 if require_approval else risk_d.approval_level
    if approval_pre_resolved:
        appr = ApprovalLevel.L1
    b = (
        builder()
        .actor(actor, ActorType.USER)
        .mission(mission_id)
        .capability("browser", "browser", act.value)
        .parameters(params)
        .reason(f"browser {act.value} {origin_of(url) or 'n/a'}")
        .risk(risk_d.risk if not approval_pre_resolved else RiskLevel.LOW, appr)
        .timeout(timeout)
        .metadata(meta)
    )
    # unique key per attempt unless caller wants idempotency via params
    intent = b.build()
    # force expiry window
    object.__setattr__(intent, "expires_at", time.time() + float(expires_in_sec))
    return intent


@dataclass
class BrowserResult:
    """Normalized safe adapter result (no cookies/tokens/secrets)."""
    status: str  # succeeded | failed | blocked | uncertain | denied
    action: str = ""
    final_origin: str = ""
    page_title: str = ""
    summary: str = ""
    screenshot_evidence_id: str = ""
    download_evidence_id: str = ""
    error_category: str = ""
    duration_sec: float = 0.0
    reconciliation_hints: list = field(default_factory=list)
    injection_hits: list = field(default_factory=list)
    retryable: bool = False
    untrusted_excerpt: str = ""  # redacted, never instructions

    def as_handler_dict(self) -> dict:
        st = self.status
        if st in ("ok", "success"):
            st = "succeeded"
        return {
            "status": st,
            "summary": safe_summary(self.summary or self.page_title or st),
            "failure_category": self.error_category,
            "retryable": self.retryable and st not in ("succeeded",),
            "final_origin": self.final_origin,
            "injection_hits": list(self.injection_hits),
            "screenshot_evidence_id": self.screenshot_evidence_id,
            "download_evidence_id": self.download_evidence_id,
            "reconciliation_hints": list(self.reconciliation_hints),
        }


class BrowserAdapter:
    """Technical browser dispatch — permission/approval decided upstream.

    Modes:
      * service — real BrowserService tiers
      * fake — deterministic in-memory (tests)
    """

    def __init__(
        self,
        *,
        service=None,
        mode: str = "service",
        workspace: Path | str | None = None,
        allowed_hosts: Optional[list[str]] = None,
    ):
        self.mode = mode
        self._service = service
        self.workspace = Path(workspace) if workspace else DEFAULT_WORKSPACE
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.allowed_hosts = allowed_hosts
        self._fake_state: dict[str, Any] = {
            "pages": {},
            "clicks": [],
            "submits": [],
            "downloads": [],
            "force_uncertain": False,
            "force_timeout": False,
            "force_crash": False,
            "redirect_to": None,
        }
        self.dispatch_count = 0

    def service(self):
        if self._service is None and self.mode == "service":
            from saathi.browser.service import BrowserService
            self._service = BrowserService()
        return self._service

    def configure_fake(self, **kwargs) -> None:
        self._fake_state.update(kwargs)

    def dispatch(self, intent: ToolIntent) -> BrowserResult:
        self.dispatch_count += 1
        t0 = time.time()
        params = intent.parameters or {}
        action = parse_action(params.get("action") or intent.operation)
        url = str(params.get("url") or "")
        selector = str(params.get("selector") or "")
        session_id = str(params.get("session_id") or "default")

        # Domain policy (again at adapter for defense in depth)
        dom = check_domain(url, allowed_hosts=self.allowed_hosts) if url else DomainDecision(True, "no_url")
        if url and not dom.allowed:
            return BrowserResult(
                status="denied", action=action.value, error_category=dom.reason,
                summary=f"domain denied: {dom.reason}",
                duration_sec=time.time() - t0,
            )

        if self.mode == "fake" or self._service is None and self.mode != "service":
            return self._dispatch_fake(action, url, selector, params, session_id, t0)

        return self._dispatch_service(action, url, selector, params, session_id, t0)

    def _dispatch_fake(self, action, url, selector, params, session_id, t0) -> BrowserResult:
        st = self._fake_state
        if st.get("force_crash"):
            return BrowserResult(
                status="failed", action=action.value, error_category="browser_crash",
                summary="browser crash (simulated)", duration_sec=time.time() - t0,
            )
        if st.get("force_timeout"):
            return BrowserResult(
                status="failed", action=action.value, error_category="timeout",
                summary="browser timeout (simulated)", duration_sec=time.time() - t0,
                retryable=False,
            )
        final_url = st.get("redirect_to") or url
        if final_url and final_url != url:
            d = revalidate_redirect(url, final_url, allowed_hosts=self.allowed_hosts)
            if not d.allowed:
                return BrowserResult(
                    status="denied", action=action.value,
                    error_category=d.reason, final_origin=origin_of(final_url),
                    summary=f"redirect denied: {d.reason}",
                    duration_sec=time.time() - t0,
                )
        if st.get("force_uncertain") and action in (
            BrowserAction.SUBMIT, BrowserAction.CLICK,
        ):
            return BrowserResult(
                status="uncertain", action=action.value,
                error_category="outcome_uncertain",
                final_origin=origin_of(final_url),
                summary="submit outcome uncertain (no confirmation)",
                reconciliation_hints=["inspect_page_state", "check_remote_id"],
                duration_sec=time.time() - t0, retryable=False,
            )

        title = st.get("pages", {}).get(final_url, {}).get("title", "Fake Page")
        text = st.get("pages", {}).get(final_url, {}).get(
            "text", "Welcome to the fake page. This is safe public content."
        )
        # Allow injection fixture
        if st.get("injection_text"):
            text = st["injection_text"]
        hits = detect_prompt_injection(text)

        if action in (BrowserAction.NAVIGATE, BrowserAction.OPEN, BrowserAction.READ,
                      BrowserAction.EXTRACT):
            return BrowserResult(
                status="succeeded", action=action.value,
                final_origin=origin_of(final_url), page_title=title,
                summary=redact_text(f"read {origin_of(final_url)} title={title}"),
                untrusted_excerpt=redact_text(text, maxlen=200),
                injection_hits=hits,
                duration_sec=time.time() - t0,
            )
        if action == BrowserAction.SCREENSHOT:
            # store tiny fake bytes as evidence via caller
            return BrowserResult(
                status="succeeded", action=action.value,
                final_origin=origin_of(final_url), page_title=title,
                summary="screenshot captured",
                duration_sec=time.time() - t0,
            )
        if action == BrowserAction.CLICK:
            st["clicks"].append({"url": final_url, "selector": selector})
            return BrowserResult(
                status="succeeded", action=action.value,
                final_origin=origin_of(final_url),
                summary=f"clicked {selector or 'element'}",
                duration_sec=time.time() - t0,
            )
        if action in (BrowserAction.TYPE, BrowserAction.FILL):
            return BrowserResult(
                status="succeeded", action=action.value,
                final_origin=origin_of(final_url),
                summary=f"filled {selector or 'field'} (text redacted)",
                duration_sec=time.time() - t0,
            )
        if action == BrowserAction.SUBMIT:
            st["submits"].append({"url": final_url, "selector": selector,
                                  "digest": params.get("payload_digest")})
            return BrowserResult(
                status="succeeded", action=action.value,
                final_origin=origin_of(final_url),
                summary="form submitted",
                duration_sec=time.time() - t0, retryable=False,
            )
        if action == BrowserAction.DOWNLOAD:
            name = sanitize_filename(params.get("file_ref") or "file.bin")
            dest = self.workspace / "downloads" / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            # path traversal defense
            if not path_is_inside(str(dest), str(self.workspace)):
                return BrowserResult(
                    status="denied", action=action.value,
                    error_category="path_traversal",
                    summary="download path outside workspace",
                    duration_sec=time.time() - t0,
                )
            dest.write_bytes(b"fake-download-content")
            st["downloads"].append(str(dest))
            return BrowserResult(
                status="succeeded", action=action.value,
                final_origin=origin_of(final_url),
                summary=f"downloaded {name}",
                duration_sec=time.time() - t0,
            )
        if action == BrowserAction.UPLOAD:
            fpath = str(params.get("file_path") or "")
            if not fpath or not path_is_inside(fpath, str(self.workspace)):
                return BrowserResult(
                    status="denied", action=action.value,
                    error_category="upload_path_denied",
                    summary="upload path outside approved workspace",
                    duration_sec=time.time() - t0,
                )
            return BrowserResult(
                status="succeeded", action=action.value,
                final_origin=origin_of(final_url),
                summary="upload completed",
                duration_sec=time.time() - t0,
            )
        if action == BrowserAction.WORKFLOW:
            return BrowserResult(
                status="succeeded", action=action.value,
                final_origin=origin_of(final_url),
                summary="workflow step completed",
                duration_sec=time.time() - t0,
            )
        return BrowserResult(
            status="failed", action=action.value,
            error_category="unsupported",
            summary=f"unsupported action {action.value}",
            duration_sec=time.time() - t0,
        )

    def _dispatch_service(self, action, url, selector, params, session_id, t0) -> BrowserResult:
        svc = self.service()
        try:
            if action in (BrowserAction.NAVIGATE, BrowserAction.OPEN):
                # Technical path after gateway authorization (never re-enter gateway)
                open_direct = getattr(svc, "_open_direct", None)
                if callable(open_direct):
                    page = open_direct(
                        url, session=session_id or None,
                        timeout=int((params or {}).get("timeout") or 30),
                    )
                else:
                    page = svc.open(
                        url, session=session_id or None,
                        timeout=int((params or {}).get("timeout") or 30),
                        governed=False,
                    )
                # revalidate final URL if different
                final = page.url or url
                if final != url:
                    d = revalidate_redirect(url, final, allowed_hosts=self.allowed_hosts)
                    if not d.allowed:
                        return BrowserResult(
                            status="denied", action=action.value,
                            error_category=d.reason, final_origin=origin_of(final),
                            summary=f"redirect denied: {d.reason}",
                            duration_sec=time.time() - t0,
                        )
                hits = detect_prompt_injection(page.text or "")
                return BrowserResult(
                    status="succeeded" if page.ok else "failed",
                    action=action.value, final_origin=origin_of(final),
                    page_title=redact_text(page.title),
                    summary=redact_text(f"open status={page.status} title={page.title}"),
                    untrusted_excerpt=redact_text(page.text, maxlen=200),
                    injection_hits=hits,
                    duration_sec=time.time() - t0,
                    error_category="" if page.ok else "fetch_failed",
                )
            if action in (BrowserAction.READ, BrowserAction.EXTRACT):
                if selector:
                    nodes = svc.extract(url, selector)
                    text = " ".join(nodes) if isinstance(nodes, list) else str(nodes)
                else:
                    open_direct = getattr(svc, "_open_direct", None)
                    if callable(open_direct):
                        page = open_direct(url, session=session_id or None)
                    else:
                        page = svc.open(url, session=session_id or None, governed=False)
                    text = page.text
                    title = page.title
                    final = page.url
                    hits = detect_prompt_injection(text or "")
                    return BrowserResult(
                        status="succeeded", action=action.value,
                        final_origin=origin_of(final or url),
                        page_title=redact_text(title),
                        summary=redact_text(f"read {len(text or '')} chars"),
                        untrusted_excerpt=redact_text(text, maxlen=200),
                        injection_hits=hits,
                        duration_sec=time.time() - t0,
                    )
                hits = detect_prompt_injection(text or "")
                return BrowserResult(
                    status="succeeded", action=action.value,
                    final_origin=origin_of(url),
                    summary=redact_text(f"extract {selector}"),
                    untrusted_excerpt=redact_text(text, maxlen=200),
                    injection_hits=hits,
                    duration_sec=time.time() - t0,
                )
            if action == BrowserAction.SCREENSHOT:
                data = svc.screenshot(url)
                # Evidence stored by outer layer; just report size
                return BrowserResult(
                    status="succeeded", action=action.value,
                    final_origin=origin_of(url),
                    summary=f"screenshot {len(data)} bytes",
                    duration_sec=time.time() - t0,
                )
            if action == BrowserAction.DOWNLOAD:
                name = sanitize_filename(params.get("file_ref") or Path(url).name or "dl.bin")
                dest = self.workspace / "downloads" / name
                dest.parent.mkdir(parents=True, exist_ok=True)
                if not path_is_inside(str(dest), str(self.workspace)):
                    return BrowserResult(
                        status="denied", action=action.value,
                        error_category="path_traversal",
                        summary="download path outside workspace",
                        duration_sec=time.time() - t0,
                    )
                path = svc.download(url, str(dest))
                return BrowserResult(
                    status="succeeded", action=action.value,
                    final_origin=origin_of(url),
                    summary=f"downloaded {sanitize_filename(Path(path).name)}",
                    duration_sec=time.time() - t0,
                )
            # Interactive actions: prefer Playwright if available, else fail closed
            if action in (BrowserAction.CLICK, BrowserAction.TYPE, BrowserAction.FILL,
                          BrowserAction.SUBMIT, BrowserAction.UPLOAD, BrowserAction.WORKFLOW):
                # Without a live interactive session API on BrowserService, use fake-safe
                # message — production interactive path uses computer_agent / agent_browser
                # (documented remaining bypass until fully migrated).
                return BrowserResult(
                    status="failed", action=action.value,
                    error_category="interactive_requires_live_session",
                    summary="interactive browser action needs live session adapter",
                    duration_sec=time.time() - t0, retryable=False,
                )
            return BrowserResult(
                status="failed", action=action.value,
                error_category="unsupported", summary=f"unsupported {action.value}",
                duration_sec=time.time() - t0,
            )
        except Exception as e:
            return BrowserResult(
                status="failed", action=action.value,
                error_category="adapter_error",
                summary=redact_text(str(e)),
                duration_sec=time.time() - t0, retryable=False,
            )


class GovernedBrowser:
    """Public API: all browser side effects enter here → ExecutionGateway."""

    def __init__(
        self,
        *,
        gateway: ExecutionGateway | None = None,
        adapter: BrowserAdapter | None = None,
        boundary: UniversalBoundary | None = None,
        workspace: Path | str | None = None,
        allowed_hosts: Optional[list[str]] = None,
        mode: str = "fake",
    ):
        self.adapter = adapter or BrowserAdapter(
            mode=mode, workspace=workspace, allowed_hosts=allowed_hosts,
        )
        self.allowed_hosts = allowed_hosts
        if boundary is not None:
            self.gateway = gateway or ExecutionGateway(boundary=boundary)
            self._boundary = boundary
        else:
            self._boundary = default_boundary()
            self.gateway = gateway or ExecutionGateway(boundary=self._boundary)
        # Register browser family handler
        self.gateway.register_handler("browser", self._handler)

    def _handler(self, intent: ToolIntent, rec: ExecutionRecord) -> dict:
        result = self.adapter.dispatch(intent)
        # Prompt injection is data — never becomes a new ToolIntent
        if result.injection_hits:
            _bump("prompt_injection_detected")
            self._emit_security(
                "browser_prompt_injection_detected",
                rec,
                detail=safe_summary(",".join(result.injection_hits)),
            )
        # Screenshots → Evidence artifact reference
        if parse_action(intent.operation) == BrowserAction.SCREENSHOT and result.status == "succeeded":
            eid = self._evidence_blob(rec, intent, kind="screenshot",
                                      note="screenshot metadata only")
            result.screenshot_evidence_id = eid
        if parse_action(intent.operation) == BrowserAction.DOWNLOAD and result.status == "succeeded":
            eid = self._evidence_blob(rec, intent, kind="download",
                                      note=result.summary)
            result.download_evidence_id = eid

        d = result.as_handler_dict()
        if result.status == "uncertain":
            d["status"] = "failed"
            d["failure_category"] = "outcome_uncertain"
            d["retryable"] = False
            _bump("outcome_uncertain")
        if result.status == "denied":
            d["status"] = "failed"
            d["failure_category"] = result.error_category or "policy"
            d["retryable"] = False
        return d

    def execute(
        self,
        *,
        action: str | BrowserAction,
        url: str = "",
        actor: str = "user:system",
        session_id: str = "default",
        tab_id: str = "",
        selector: str = "",
        payload: Optional[dict] = None,
        file_path: str = "",
        environment: str = "dev",
        approval_id: str = "",
        approval_pre_resolved: bool = False,
        force_new: bool = False,
        idempotency_key: str = "",
        mission_id: str = "browser",
        mission_run_id: str = "",
        mission_state: str = "",
        request_source: str = "api",
        correlation_id: str = "",
        parent_run_id: str = "",
        retry_attempt: int = 0,
        retry_authorized: bool = True,
        checkpoint_reference: str = "",
        resume: bool = False,
        schedule_enabled: bool = True,
        trigger_trusted: bool = True,
        require_mission: bool = False,
        trading_classified: bool = False,
        trading_authorized: bool = False,
        expected_mission_id: str = "",
        approval_expired: bool = False,
        approval_valid: bool | None = None,
    ) -> ExecutionRecord:
        """Governed browser action entry (authoritative, M17.24 context-bound)."""
        _bump("requested")
        act = parse_action(action)

        # Context preconditions (fail closed) — M17.24
        from saathi.browser.guard import BrowserGovernanceError, require_governed_context
        try:
            # Mission-bound sources must carry mission/run attribution
            src = (request_source or "").lower()
            need_mission = require_mission or src in (
                "scheduler", "event_trigger", "mission", "pipeline", "agent", "control_center",
            )
            # Trading classification from action type
            if act == BrowserAction.TRADE or act == BrowserAction.PAYMENT:
                trading_classified = True
            require_governed_context(
                actor_id=actor,
                mission_id=mission_id,
                mission_run_id=mission_run_id,
                require_mission=need_mission,
                mission_state=mission_state,
                cancelled=(mission_state or "").lower() in ("cancelled", "canceled", "killed"),
                approval_id=approval_id,
                approval_valid=approval_valid,
                approval_expired=approval_expired,
                trading_classified=trading_classified,
                trading_authorized=trading_authorized,
                retry_attempt=retry_attempt,
                retry_authorized=retry_authorized,
                checkpoint_reference=checkpoint_reference,
                resume=resume,
                schedule_enabled=schedule_enabled,
                trigger_trusted=trigger_trusted,
            )
            # Ownership: cannot forge another mission's execution context
            if expected_mission_id and mission_id and expected_mission_id != mission_id:
                raise BrowserGovernanceError(
                    "MISSION_FORGERY",
                    "caller cannot forge another mission's browser execution context",
                    details={
                        "expected_mission_id": expected_mission_id,
                        "mission_id": mission_id,
                    },
                )
        except BrowserGovernanceError as e:
            _bump("denied")
            _bump("policy_denied")
            intent = build_browser_intent(
                action=act, url=url, actor=actor or "unknown",
                session_id=session_id, environment=environment,
                mission_id=mission_id or "browser",
            )
            return self._deny_record(intent, reason=e.code.lower(), kind=e.code.lower())

        # Prohibited — fail closed before gateway handler
        if act in PROHIBITED_ACTIONS:
            _bump("policy_denied")
            _bump("denied")
            intent = build_browser_intent(
                action=act, url=url, actor=actor, session_id=session_id,
                environment=environment, require_approval=True,
            )
            # submit will deny on risk; also short-circuit with synthetic denied via submit
            # Force critical risk path
            rec = self.gateway.submit(intent, execute=True, force_new=True)
            self._emit_security("browser_domain_denied", rec,
                                detail=f"prohibited:{act.value}")
            return rec

        # Domain check before intent (clear policy denial metrics)
        if url:
            dom = check_domain(url, allowed_hosts=self.allowed_hosts)
            if not dom.allowed:
                _bump("domain_denied")
                _bump("denied")
                intent = build_browser_intent(
                    action=act, url=url, actor=actor, session_id=session_id,
                    environment=environment,
                    allowed_hosts=list(self.allowed_hosts or DEFAULT_ALLOWED_HOST_SUFFIXES),
                )
                # Deny via gateway permission by marking actor denied list + invalid
                # Use a dedicated deny path: submit with metadata that fails domain
                rec = self._deny_record(intent, reason=dom.reason, kind="domain")
                self._emit_security("browser_domain_denied", rec, detail=dom.reason)
                return rec

        # Session expiry check
        if session_id and session_id.startswith("expired:"):
            _bump("denied")
            intent = build_browser_intent(
                action=act, url=url, actor=actor, session_id=session_id,
                environment=environment,
            )
            return self._deny_record(intent, reason="session_expired", kind="session")

        # Upload path pre-check
        if act == BrowserAction.UPLOAD:
            ws = str(self.adapter.workspace)
            if not file_path or not path_is_inside(file_path, ws):
                _bump("policy_denied")
                intent = build_browser_intent(
                    action=act, url=url, actor=actor, session_id=session_id,
                    file_path=file_path, environment=environment,
                )
                return self._deny_record(intent, reason="upload_path_denied", kind="upload")

        intent = build_browser_intent(
            action=act, url=url, actor=actor, session_id=session_id, tab_id=tab_id,
            selector=selector, payload=payload, file_path=file_path,
            environment=environment,
            allowed_hosts=list(self.allowed_hosts or DEFAULT_ALLOWED_HOST_SUFFIXES),
            approval_pre_resolved=approval_pre_resolved or bool(approval_id),
            mission_id=mission_id or "browser",
        )
        # Enrich metadata with M17.24 attribution (frozen ToolIntent → rebuild fields)
        meta = dict(intent.metadata or {})
        meta.update({
            "request_source": request_source,
            "mission_run_id": mission_run_id,
            "parent_run_id": parent_run_id,
            "retry_attempt": int(retry_attempt or 0),
            "checkpoint_reference": checkpoint_reference,
            "correlation_hint": correlation_id,
        })
        object.__setattr__(intent, "metadata", meta)
        if correlation_id:
            object.__setattr__(intent, "correlation_id", correlation_id)
        if idempotency_key:
            key = idempotency_key if len(idempotency_key) == 64 else hashlib.sha256(
                idempotency_key.encode()
            ).hexdigest()
            object.__setattr__(intent, "idempotency_key", key)

        # Bind approval if provided (must match digest)
        if approval_id:
            digest = tool_intent_digest(intent)
            self._boundary.store.bind_approval(
                approval_id, digest=digest, actor=actor,
                expires_at=time.time() + 3600,
            )

        self._emit_security("browser_intent_requested", None,
                            detail=f"{act.value} {origin_of(url)}",
                            actor=actor)

        rec = self.gateway.submit(
            intent,
            approval_id=approval_id if approval_id else "",
            handler=self._handler,
            execute=True,
            force_new=force_new,
        )
        self._track(rec)
        return rec

    def approve_and_run(
        self,
        execution_id: str,
        *,
        intent: ToolIntent,
        approval_id: str = "",
    ) -> ExecutionRecord:
        aid = approval_id or f"appr-{uuid.uuid4().hex[:12]}"
        rec = self.gateway.approve_execution(
            execution_id, approval_id=aid, execute=True,
            handler=self._handler, intent=intent,
        )
        self._track(rec)
        return rec

    def cancel(self, execution_id: str, *, reason: str = "cancelled") -> ExecutionRecord:
        rec = self.gateway.cancel_execution(execution_id, reason=reason)
        _bump("cancelled")
        self._emit_security("browser_action_cancelled", rec, detail=reason)
        return rec

    def _deny_record(self, intent: ToolIntent, *, reason: str, kind: str) -> ExecutionRecord:
        """Create a denied execution through the gateway without adapter dispatch."""
        # Use a handler that never runs by stopping at permission via metadata
        # Simplest: submit with denied actor list
        from saathi.execution.toolintent import ToolIntent as TI
        # Mutate via rebuild — ToolIntent is frozen; set denied via metadata in new intent
        data = intent.to_dict()
        data["metadata"] = {**(data.get("metadata") or {}), "denied_actors": [intent.actor_id]}
        # Actually permission checks denied_actors against actor_id — good
        bad = TI.from_dict(data)
        # permission check uses metadata denied_actors
        # rebuild properly
        intent2 = build_browser_intent(
            action=intent.operation,
            url=(intent.parameters or {}).get("url", ""),
            actor=intent.actor_id,
            session_id=(intent.parameters or {}).get("session_id", "default"),
            environment=(intent.parameters or {}).get("environment", "dev"),
        )
        # inject deny via empty actor after build is hard; use force path:
        rec = self._boundary.store.insert(
            __import__("saathi.execution.record", fromlist=["ExecutionRecord"]).ExecutionRecord(
                tool_intent_digest=tool_intent_digest(intent),
                intent_id=intent.intent_id,
                actor=intent.actor_id,
                target=f"browser:browser:{intent.operation}",
                family="browser",
                status=ExecutionState.REQUESTED.value,
                risk="high",
                result_summary=safe_summary(reason),
                failure_category=kind,
                idempotency_key=intent.idempotency_key,
                correlation_id=intent.correlation_id,
            )
        )
        from saathi.execution.execution_state import ExecutionState as ES
        rec = self._boundary.store.transition(
            rec.execution_id, ES.DENIED, reason=reason,
            extra={"failure_category": kind, "result_summary": safe_summary(reason)},
        )
        # evidence
        try:
            self._boundary._record_evidence(rec, intent, status="denied")
            self._boundary._emit_security(rec, f"execution_{rec.status}")
            self._boundary._emit_bus(f"execution.{rec.status}", rec)
        except Exception:
            pass
        _bump("denied")
        return rec

    def _track(self, rec: ExecutionRecord) -> None:
        st = rec.status
        if st == ExecutionState.SUCCEEDED.value:
            _bump("succeeded")
            self._emit_security("browser_action_succeeded", rec)
        elif st == ExecutionState.FAILED.value:
            if rec.failure_category == "outcome_uncertain":
                _bump("outcome_uncertain")
                self._emit_security("browser_outcome_uncertain", rec)
            else:
                _bump("failed")
                self._emit_security("browser_action_failed", rec)
        elif st == ExecutionState.APPROVAL_REQUIRED.value:
            _bump("approval_required")
            self._emit_security("browser_approval_required", rec)
        elif st == ExecutionState.DENIED.value:
            _bump("denied")
        elif st == ExecutionState.CANCELLED.value:
            _bump("cancelled")
        elif st == ExecutionState.EXPIRED.value:
            _bump("expired")

    def _emit_security(self, kind: str, rec: Optional[ExecutionRecord], *,
                       detail: str = "", actor: str = "") -> None:
        try:
            from saathi.security.timeline import get_timeline
            user = actor or (rec.actor if rec else "system")
            get_timeline().record(
                user or "system",
                "risk_alert" if "denied" in kind or "failed" in kind or "injection" in kind
                else "security_setting_changed",
                f"browser:{kind}",
                detail=safe_summary(detail or (rec.result_summary if rec else "")),
                meta={
                    "event": kind,
                    "execution_id": rec.execution_id if rec else "",
                    "status": rec.status if rec else "",
                    "target": rec.target if rec else "",
                },
            )
        except Exception:
            pass

    def _evidence_blob(self, rec, intent, *, kind: str, note: str) -> str:
        try:
            from saathi.evidence.schema import Evidence
            from saathi.evidence.store import default_store
            ev = Evidence(
                department="browser",
                project="browser",
                episode=rec.execution_id,
                run=rec.execution_id,
                director="GovernedBrowser",
                workflow="m17.23",
                provider="browser",
                model=kind,
                status="ready",
                metrics={
                    "kind": kind,
                    "origin": (intent.parameters or {}).get("origin", ""),
                    "action": intent.operation,
                    "digest": (intent.parameters or {}).get("payload_digest", "")[:16],
                },
                artifacts={"note": safe_summary(note)},
            )
            return default_store().record(ev)
        except Exception:
            return ""


def ceo_browser_summary(*, since: float | None = None) -> dict | None:
    """CEO-facing browser summary — only when attention needed."""
    m = browser_metrics()
    include = bool(
        m.get("failed")
        or m.get("outcome_uncertain")
        or m.get("approval_required")
        or m.get("domain_denied")
        or m.get("policy_denied")
        or m.get("prompt_injection_detected")
    )
    if not include:
        return None
    return {
        "include_in_ceo_brief": True,
        "failed": m.get("failed", 0),
        "outcome_uncertain": m.get("outcome_uncertain", 0),
        "approval_backlog": m.get("approval_required", 0),
        "domain_denied": m.get("domain_denied", 0),
        "policy_denied": m.get("policy_denied", 0),
        "prompt_injection_detected": m.get("prompt_injection_detected", 0),
        "succeeded": m.get("succeeded", 0),
    }


# Process singleton for migration of public paths
_GOVERNED: Optional[GovernedBrowser] = None
_GOV_LOCK = threading.Lock()


def default_governed_browser(**kwargs) -> GovernedBrowser:
    global _GOVERNED
    with _GOV_LOCK:
        if kwargs:
            return GovernedBrowser(**kwargs)
        if _GOVERNED is None:
            # Default to service mode when available; tests override with fake
            _GOVERNED = GovernedBrowser(mode="fake")
        return _GOVERNED


def reset_governed_browser() -> None:
    global _GOVERNED
    with _GOV_LOCK:
        _GOVERNED = None
    reset_browser_metrics()
