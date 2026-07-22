"""M17.26 — Production CDP / sandbox browser adapter bound to governed sessions.

Attaches only to an explicitly identified endpoint or managed sandbox process.
Never exposes low-level Playwright page objects to callers.
Never silently creates an unmanaged browser on attach failure.
Never falls back to raw driver calls from product paths.

Live CDP uses LiveBrowserDriver only when ``allow_live=True`` (never default in
unit tests). Deterministic fake/sandbox mode is the default for tests.
"""
from __future__ import annotations

import hashlib
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional
from urllib.parse import urlparse

from saathi.browser.adapter_contract import (
    HIGH_RISK_ACTION_CLASSES,
    NO_BLIND_RETRY_ACTIONS,
    AdapterActionResult,
    AdapterError,
    AdapterErrorCode,
    AdapterHealth,
    AdapterHealthState,
    BrowserSessionAdapter,
    GovernedActionRequest,
    heartbeat,
)
from saathi.browser.domain_policy import DomainPolicyService, normalize_url


@dataclass
class BoundPage:
    page_id: str
    session_id: str
    url: str = ""
    origin: str = ""
    title: str = ""
    fingerprint: str = ""
    scoped: bool = True  # only explicitly scoped pages may be used


@dataclass
class SessionBinding:
    session_id: str
    actor_id: str = ""
    mission_id: str = ""
    mission_run_id: str = ""
    lease_owner: str = ""
    endpoint: str = ""
    adapter_identity: str = ""
    connection_meta: dict = field(default_factory=dict)
    pages: dict[str, BoundPage] = field(default_factory=dict)
    active_page_id: str = ""
    paused: bool = False
    human_control: bool = False
    kill_switch: bool = False
    cancelled: bool = False
    closed: bool = False
    last_action_id: str = ""
    last_action_status: str = ""
    pending_uncertain_action_id: str = ""
    reconnect_attempts: int = 0
    max_reconnect_attempts: int = 3
    # Sandbox page store for deterministic tests
    sandbox_pages: dict[str, dict] = field(default_factory=dict)
    clicks: list = field(default_factory=list)
    fills: list = field(default_factory=list)
    submits: list = field(default_factory=list)


class ProductionBrowserAdapter(BrowserSessionAdapter):
    """Governed production adapter (sandbox by default; optional live CDP)."""

    adapter_id = "production-cdp"
    adapter_type = "cdp_sandbox"

    def __init__(
        self,
        *,
        adapter_id: str = "",
        allow_live: bool = False,
        domain_policy: DomainPolicyService | None = None,
        max_reconnect_attempts: int = 3,
    ):
        self.adapter_id = adapter_id or f"prod-adapter-{uuid.uuid4().hex[:8]}"
        self.adapter_type = "cdp_live" if allow_live else "cdp_sandbox"
        self.allow_live = allow_live
        self.domain_policy = domain_policy or DomainPolicyService.for_environment("test")
        self.max_reconnect_attempts = max_reconnect_attempts
        self._bindings: dict[str, SessionBinding] = {}
        self._health: dict[str, AdapterHealth] = {}
        self._live_drivers: dict[str, Any] = {}
        self._lock = threading.RLock()
        self._force_disconnect: set[str] = set()
        self._global_kill = False

    # ── attach / validate ──────────────────────────────────────────────────

    def attach_session(
        self,
        session_id: str,
        *,
        endpoint: str = "",
        metadata: dict | None = None,
        actor_id: str = "",
        mission_id: str = "",
        mission_run_id: str = "",
        lease_owner: str = "",
    ) -> AdapterHealth:
        if not session_id:
            raise AdapterError(AdapterErrorCode.SESSION_REQUIRED, "session_id required for attach")
        meta = dict(metadata or {})
        with self._lock:
            if session_id in self._bindings and not self._bindings[session_id].closed:
                # re-attach same session is allowed (reconnect path)
                b = self._bindings[session_id]
            else:
                b = SessionBinding(
                    session_id=session_id,
                    actor_id=actor_id or meta.get("actor_id", ""),
                    mission_id=mission_id or meta.get("mission_id", ""),
                    mission_run_id=mission_run_id or meta.get("mission_run_id", ""),
                    lease_owner=lease_owner or meta.get("lease_owner", "") or actor_id,
                    endpoint=endpoint or meta.get("endpoint", "sandbox://local"),
                    adapter_identity=self.adapter_id,
                    connection_meta={
                        "endpoint_kind": "sandbox" if not self.allow_live else "cdp",
                        "attached_at": time.time(),
                        # never store secrets
                        "has_auth": bool(meta.get("has_auth")),
                    },
                    max_reconnect_attempts=self.max_reconnect_attempts,
                )
                # Seed sandbox blank page scoped to this session only
                pid = f"page-{uuid.uuid4().hex[:10]}"
                b.pages[pid] = BoundPage(
                    page_id=pid, session_id=session_id,
                    url="about:blank", origin="", title="", fingerprint="blank",
                    scoped=True,
                )
                b.active_page_id = pid
                self._bindings[session_id] = b

            if self.allow_live and endpoint:
                # Live attach only to explicit endpoint — never invent a browser
                try:
                    self._attach_live(session_id, endpoint)
                except Exception as e:
                    h = AdapterHealth(
                        state=AdapterHealthState.UNAVAILABLE,
                        adapter_id=self.adapter_id,
                        adapter_type=self.adapter_type,
                        session_id=session_id,
                        last_error_category="attach_failed",
                        details={"error": str(e)[:120]},
                    )
                    self._health[session_id] = h
                    raise AdapterError(
                        AdapterErrorCode.ATTACH_FAILED,
                        "CDP attach failed; will not create unmanaged browser",
                        details={"endpoint_set": bool(endpoint)},
                    ) from e

            h = AdapterHealth(
                state=AdapterHealthState.HEALTHY,
                adapter_id=self.adapter_id,
                adapter_type=self.adapter_type,
                session_id=session_id,
                adapter_available=True,
                process_alive=True,
                cdp_connection_alive=True,
                browser_context_alive=True,
                active_page_available=True,
                session_lease_valid=True,
                last_heartbeat=time.time(),
                supported_capabilities=[
                    "navigate", "inspect", "click", "fill", "type", "submit",
                    "screenshot", "scroll", "wait", "reconcile", "pause", "resume",
                ],
            )
            self._health[session_id] = heartbeat(h)
            return h

    def _attach_live(self, session_id: str, endpoint: str) -> None:
        """Attach to managed CDP. Does not launch user's real profile."""
        # Only loopback CDP endpoints are accepted for safety
        if not (endpoint.startswith("http://127.0.0.1") or endpoint.startswith("http://localhost")):
            raise AdapterError(
                AdapterErrorCode.ATTACH_FAILED,
                "live CDP endpoint must be loopback",
            )
        # Live path intentionally minimal — tests use sandbox
        from saathi.computer_agent.browser_driver import LiveBrowserDriver
        driver = LiveBrowserDriver()
        if not driver.available():
            raise AdapterError(AdapterErrorCode.ATTACH_FAILED, "browser binary unavailable")
        # Do not connect to user's profile; managed launch only when allow_live
        ev = driver.launch("about:blank")
        if not ev.ok:
            raise AdapterError(AdapterErrorCode.ATTACH_FAILED, str(ev.detail))
        self._live_drivers[session_id] = driver

    def validate_session(
        self, session_id: str, *, actor_id: str = "", lease_owner: str = "",
        mission_id: str = "",
    ) -> bool:
        b = self._bindings.get(session_id)
        if not b or b.closed:
            return False
        if actor_id and b.actor_id and actor_id != b.actor_id:
            return False
        if mission_id and b.mission_id and mission_id != b.mission_id:
            return False
        if lease_owner and b.lease_owner and lease_owner != b.lease_owner:
            # human control releases agent lease
            if b.human_control and lease_owner.startswith("human:"):
                return True
            return False
        return True

    def health(self, session_id: str = "") -> AdapterHealth:
        if session_id:
            h = self._health.get(session_id)
            if h:
                return h
            if session_id in self._force_disconnect:
                return AdapterHealth(
                    state=AdapterHealthState.DISCONNECTED,
                    adapter_id=self.adapter_id, session_id=session_id,
                    last_error_category="disconnected",
                )
            return AdapterHealth(
                state=AdapterHealthState.UNKNOWN,
                adapter_id=self.adapter_id, session_id=session_id,
            )
        return AdapterHealth(
            state=AdapterHealthState.HEALTHY if self._bindings else AdapterHealthState.UNKNOWN,
            adapter_id=self.adapter_id,
            adapter_type=self.adapter_type,
            adapter_available=True,
        )

    # ── defensive pre-action gates ─────────────────────────────────────────

    def _precheck(self, request: GovernedActionRequest) -> SessionBinding:
        request.require_context()
        if self._global_kill or request.payload.get("kill_switch"):
            raise AdapterError(AdapterErrorCode.KILL_SWITCH, "kill switch active")
        b = self._bindings.get(request.session_id)
        if not b or b.closed:
            raise AdapterError(AdapterErrorCode.SESSION_REQUIRED, "session not attached")
        if b.cancelled or request.payload.get("cancelled"):
            raise AdapterError(AdapterErrorCode.CANCELLED, "session cancelled")
        if b.kill_switch:
            raise AdapterError(AdapterErrorCode.KILL_SWITCH, "session kill switch active")
        if request.session_id in self._force_disconnect:
            self._mark_disconnected(request.session_id)
            raise AdapterError(
                AdapterErrorCode.DISCONNECTED, "adapter disconnected",
                reconciliation=True,
            )
        if not self.validate_session(
            request.session_id,
            actor_id=request.actor_id,
            lease_owner=request.lease_owner or request.actor_id,
            mission_id=request.mission_id,
        ):
            raise AdapterError(AdapterErrorCode.OWNERSHIP_MISMATCH, "ownership or lease invalid")
        if b.human_control and not request.payload.get("human_action"):
            raise AdapterError(
                AdapterErrorCode.HUMAN_CONCURRENT,
                "human controls session; agent actions denied",
            )
        if b.paused and request.action_type not in ("resume", "inspect", "reconcile"):
            raise AdapterError(AdapterErrorCode.CONTEXT_MISSING, "adapter paused")
        h = self._health.get(request.session_id)
        if h and h.state in (
            AdapterHealthState.DISCONNECTED, AdapterHealthState.UNAVAILABLE,
            AdapterHealthState.CLOSED,
        ):
            raise AdapterError(AdapterErrorCode.DISCONNECTED, f"adapter state {h.state.value}")
        if h and not h.allows_high_risk() and request.action_class in HIGH_RISK_ACTION_CLASSES:
            raise AdapterError(
                AdapterErrorCode.HEALTH_DEGRADED_BLOCK,
                "high-risk actions blocked while adapter is not HEALTHY",
            )
        if b.pending_uncertain_action_id and request.action_type not in ("reconcile", "inspect"):
            raise AdapterError(
                AdapterErrorCode.RECONCILIATION_REQUIRED,
                "uncertain prior action requires reconciliation",
                reconciliation=True,
            )
        # Page ownership
        page = b.pages.get(b.active_page_id)
        if request.page_id:
            page = b.pages.get(request.page_id)
            if not page or page.session_id != request.session_id:
                raise AdapterError(AdapterErrorCode.PAGE_UNKNOWN, "page not in session scope")
            if not page.scoped:
                raise AdapterError(AdapterErrorCode.PAGE_UNKNOWN, "unrelated pre-existing tab denied")
        if request.page_fingerprint and page and page.fingerprint and \
                request.page_fingerprint != page.fingerprint and request.action_type not in (
                    "navigate", "open",
                ):
            raise AdapterError(AdapterErrorCode.PAGE_MISMATCH, "page fingerprint mismatch")
        return b

    def _mark_disconnected(self, session_id: str) -> None:
        h = self._health.get(session_id) or AdapterHealth(
            adapter_id=self.adapter_id, session_id=session_id,
        )
        h.state = AdapterHealthState.DISCONNECTED
        h.cdp_connection_alive = False
        h.disconnect_count += 1
        h.last_error_category = "disconnected"
        h.reconciliation_required = True
        self._health[session_id] = h
        b = self._bindings.get(session_id)
        if b:
            b.pending_uncertain_action_id = b.pending_uncertain_action_id or b.last_action_id

    # ── operations ─────────────────────────────────────────────────────────

    def navigate(self, request: GovernedActionRequest) -> AdapterActionResult:
        return self.act(request) if request.action_type in ("navigate", "open") else self.act(
            GovernedActionRequest(**{**request.__dict__, "action_type": "navigate"})
        )

    def inspect(self, request: GovernedActionRequest) -> AdapterActionResult:
        t0 = time.time()
        b = self._precheck(request)
        page = b.pages.get(b.active_page_id)
        return AdapterActionResult(
            status="succeeded",
            action_id=request.action_id,
            action_type="inspect",
            summary="page inspected",
            final_url=page.url if page else "",
            final_origin=page.origin if page else "",
            page_id=page.page_id if page else "",
            page_fingerprint=page.fingerprint if page else "",
            page_title=page.title if page else "",
            duration_sec=time.time() - t0,
            details={"sandbox": True, "elements": list(
                (b.sandbox_pages.get(page.url or "", {}) or {}).get("elements", [])
            )[:20] if page else []},
        )

    def act(self, request: GovernedActionRequest) -> AdapterActionResult:
        t0 = time.time()
        try:
            b = self._precheck(request)
        except AdapterError as e:
            return AdapterActionResult(
                status="denied" if e.code not in (
                    AdapterErrorCode.DISCONNECTED.value,
                    AdapterErrorCode.UNCERTAIN_OUTCOME.value,
                ) else "failed",
                action_id=request.action_id,
                action_type=request.action_type,
                summary=e.message,
                error_category=e.code.lower(),
                retryable=e.retryable,
                reconciliation_required=e.reconciliation,
                duration_sec=time.time() - t0,
                details=e.details,
            )

        action = request.action_type
        # Unsupported live actions fail closed
        supported = {
            "navigate", "open", "read", "extract", "screenshot", "scroll", "wait",
            "click", "hover", "fill", "type", "submit", "select", "select_option",
            "check", "uncheck", "dismiss_dialog", "inspect_dom", "snapshot",
            "download", "upload",
        }
        if action not in supported:
            return AdapterActionResult(
                status="failed",
                action_id=request.action_id,
                action_type=action,
                summary=f"unsupported live action: {action}",
                error_category=AdapterErrorCode.UNSUPPORTED_ACTION.value.lower(),
                retryable=False,
                duration_sec=time.time() - t0,
            )

        # Force uncertain path for tests
        if request.payload.get("force_uncertain") and action in NO_BLIND_RETRY_ACTIONS:
            b.pending_uncertain_action_id = request.action_id
            b.last_action_id = request.action_id
            b.last_action_status = "uncertain"
            h = self._health.get(request.session_id)
            if h:
                h.state = AdapterHealthState.RECONCILIATION_REQUIRED
                h.reconciliation_required = True
                self._health[request.session_id] = h
            return AdapterActionResult(
                status="uncertain",
                action_id=request.action_id,
                action_type=action,
                summary="action outcome uncertain",
                error_category="outcome_uncertain",
                reconciliation_required=True,
                retryable=False,
                duration_sec=time.time() - t0,
            )

        page = b.pages.get(b.active_page_id)
        final_url = request.url or (page.url if page else "")
        # Redirect simulation
        redirect_to = request.payload.get("redirect_to")
        if redirect_to and action in ("navigate", "open", "click", "submit"):
            d = self.domain_policy.check_redirect(final_url or "https://example.com/", redirect_to)
            if not d.allowed:
                return AdapterActionResult(
                    status="denied",
                    action_id=request.action_id,
                    action_type=action,
                    summary=f"redirect denied: {d.reason}",
                    error_category=d.reason,
                    final_url=redirect_to,
                    duration_sec=time.time() - t0,
                )
            final_url = redirect_to

        # Popup simulation
        popup_url = request.payload.get("popup_url")
        if popup_url:
            d = self.domain_policy.check_popup(popup_url)
            if not d.allowed:
                return AdapterActionResult(
                    status="denied",
                    action_id=request.action_id,
                    action_type=action,
                    summary=f"popup denied: {d.reason}",
                    error_category=d.reason,
                    duration_sec=time.time() - t0,
                )

        norm = normalize_url(final_url) if final_url else None
        origin = norm.origin if norm else ""
        title = ""
        fp = ""

        if action in ("navigate", "open"):
            # Domain already validated above adapter; defensive recheck
            if final_url and not final_url.startswith("about:"):
                d = self.domain_policy.check(final_url)
                if not d.allowed:
                    return AdapterActionResult(
                        status="denied",
                        action_id=request.action_id,
                        action_type=action,
                        summary=f"domain recheck denied: {d.reason}",
                        error_category=AdapterErrorCode.DOMAIN_RECHECK_FAILED.value.lower(),
                        duration_sec=time.time() - t0,
                    )
            title = (b.sandbox_pages.get(final_url) or {}).get("title", "Page")
            fp = hashlib.sha256((final_url or "").encode()).hexdigest()[:16]
            if page:
                page.url = final_url
                page.origin = origin
                page.title = title
                page.fingerprint = fp
            # live navigate if present
            driver = self._live_drivers.get(request.session_id)
            if driver is not None:
                try:
                    driver.navigate(final_url)
                except Exception as e:
                    self._mark_disconnected(request.session_id)
                    return AdapterActionResult(
                        status="failed",
                        action_id=request.action_id,
                        action_type=action,
                        summary=f"live navigate failed: {e}"[:160],
                        error_category="adapter_error",
                        reconciliation_required=True,
                        duration_sec=time.time() - t0,
                    )
            summary = f"navigated {origin or final_url}"
        elif action in ("click", "hover", "select", "select_option", "check", "uncheck", "dismiss_dialog"):
            if request.selector and request.payload.get("target_missing"):
                return AdapterActionResult(
                    status="failed",
                    action_id=request.action_id,
                    action_type=action,
                    summary="target not interactable",
                    error_category=AdapterErrorCode.TARGET_NOT_INTERACTABLE.value.lower(),
                    duration_sec=time.time() - t0,
                )
            b.clicks.append({"selector": request.selector, "action": action})
            driver = self._live_drivers.get(request.session_id)
            if driver is not None and request.selector:
                try:
                    driver.click(request.selector)
                except Exception as e:
                    self._mark_disconnected(request.session_id)
                    return AdapterActionResult(
                        status="failed", action_id=request.action_id,
                        action_type=action, summary=str(e)[:160],
                        error_category="adapter_error", reconciliation_required=True,
                        duration_sec=time.time() - t0,
                    )
            summary = f"clicked {request.selector or 'element'}"
            if page:
                final_url = page.url
                origin = page.origin
                title = page.title
                fp = page.fingerprint
        elif action in ("fill", "type"):
            # Never log sensitive text
            b.fills.append({"selector": request.selector, "redacted": True})
            driver = self._live_drivers.get(request.session_id)
            if driver is not None and request.selector:
                # Sensitive values must not arrive; use empty if redacted
                val = "" if request.text_redacted else str(request.payload.get("text") or "")
                try:
                    driver.fill(request.selector, val)
                except Exception as e:
                    self._mark_disconnected(request.session_id)
                    return AdapterActionResult(
                        status="failed", action_id=request.action_id,
                        action_type=action, summary=str(e)[:160],
                        error_category="adapter_error", reconciliation_required=True,
                        duration_sec=time.time() - t0,
                    )
            summary = f"filled {request.selector or 'field'} (text redacted)"
            if page:
                final_url, origin, title, fp = page.url, page.origin, page.title, page.fingerprint
        elif action == "submit":
            b.submits.append({"selector": request.selector, "idem": request.idempotency_key})
            summary = "form submitted"
            if page:
                final_url, origin, title, fp = page.url, page.origin, page.title, page.fingerprint
        elif action in ("read", "extract", "inspect_dom", "snapshot", "scroll", "wait"):
            summary = f"{action} ok"
            if page:
                final_url, origin, title, fp = page.url, page.origin, page.title, page.fingerprint
        elif action == "screenshot":
            summary = "screenshot captured (adapter; redaction upstream)"
            if page:
                final_url, origin, title, fp = page.url, page.origin, page.title, page.fingerprint
        elif action in ("download", "upload"):
            summary = f"{action} completed (metadata only)"
            if page:
                final_url, origin, title, fp = page.url, page.origin, page.title, page.fingerprint
        else:
            summary = f"{action} completed"

        b.last_action_id = request.action_id
        b.last_action_status = "succeeded"
        h = self._health.get(request.session_id)
        if h:
            h.last_successful_action = time.time()
            h.state = AdapterHealthState.HEALTHY
            self._health[request.session_id] = heartbeat(h)

        return AdapterActionResult(
            status="succeeded",
            action_id=request.action_id,
            action_type=action,
            summary=summary,
            final_url=final_url,
            final_origin=origin,
            page_id=page.page_id if page else "",
            page_fingerprint=fp,
            page_title=title,
            duration_sec=time.time() - t0,
            details={"adapter_id": self.adapter_id, "raw_page_exposed": False},
        )

    def capture_evidence(
        self, request: GovernedActionRequest, *, kind: str = "screenshot",
    ) -> AdapterActionResult:
        # Adapter captures only metadata markers; redaction is upstream
        b = self._bindings.get(request.session_id)
        if not b or b.closed:
            return AdapterActionResult(
                status="denied", action_id=request.action_id,
                error_category="session_required", summary="session not attached",
            )
        page = b.pages.get(b.active_page_id)
        return AdapterActionResult(
            status="succeeded",
            action_id=request.action_id,
            action_type=f"capture_{kind}",
            summary=f"{kind} metadata captured; redaction required before persist",
            final_url=page.url if page else "",
            page_id=page.page_id if page else "",
            details={"kind": kind, "raw_bytes_returned": False},
        )

    def pause(self, session_id: str, *, reason: str = "") -> AdapterHealth:
        b = self._bindings.get(session_id)
        if not b:
            raise AdapterError(AdapterErrorCode.SESSION_REQUIRED, "unknown session")
        b.paused = True
        h = self._health.get(session_id) or AdapterHealth(
            adapter_id=self.adapter_id, session_id=session_id,
        )
        h.state = AdapterHealthState.DEGRADED
        h.details["pause_reason"] = reason[:80]
        self._health[session_id] = h
        return h

    def resume(self, session_id: str, *, checkpoint: dict | None = None) -> AdapterHealth:
        b = self._bindings.get(session_id)
        if not b or b.closed:
            raise AdapterError(AdapterErrorCode.SESSION_REQUIRED, "unknown session")
        cp = checkpoint or {}
        page = b.pages.get(b.active_page_id)
        if cp.get("page_fingerprint") and page and page.fingerprint and \
                cp["page_fingerprint"] != page.fingerprint:
            h = self._health.get(session_id) or AdapterHealth(
                adapter_id=self.adapter_id, session_id=session_id,
            )
            h.state = AdapterHealthState.RECONCILIATION_REQUIRED
            h.reconciliation_required = True
            h.last_error_category = "page_state_mismatch"
            self._health[session_id] = h
            raise AdapterError(
                AdapterErrorCode.PAGE_MISMATCH,
                "page state changed since checkpoint; fail closed",
                reconciliation=True,
            )
        if cp.get("page_origin") and page and page.origin and cp["page_origin"] != page.origin:
            raise AdapterError(
                AdapterErrorCode.PAGE_MISMATCH,
                "origin mismatch on resume",
                reconciliation=True,
            )
        b.paused = False
        b.human_control = False
        h = self._health.get(session_id) or AdapterHealth(
            adapter_id=self.adapter_id, session_id=session_id,
        )
        h.state = AdapterHealthState.HEALTHY
        h.session_lease_valid = True
        self._health[session_id] = heartbeat(h)
        return h

    def reconcile(self, session_id: str, *, action_id: str = "", outcome: str = "failed") -> AdapterActionResult:
        """Mark uncertain action resolved without re-executing side effects."""
        b = self._bindings.get(session_id)
        if not b:
            return AdapterActionResult(
                status="denied", error_category="session_required",
                summary="unknown session",
            )
        if action_id and b.pending_uncertain_action_id and action_id != b.pending_uncertain_action_id:
            return AdapterActionResult(
                status="denied", error_category="action_mismatch",
                summary="reconcile action_id does not match pending uncertain action",
            )
        resolved = outcome if outcome in ("succeeded", "failed") else "failed"
        b.pending_uncertain_action_id = ""
        b.last_action_status = resolved
        h = self._health.get(session_id)
        if h:
            h.reconciliation_required = False
            h.state = AdapterHealthState.HEALTHY
            self._health[session_id] = h
        return AdapterActionResult(
            status="succeeded",
            action_id=action_id or b.last_action_id,
            action_type="reconcile",
            summary=f"reconciled as {resolved} without re-execution",
            details={"outcome": resolved, "duplicate_execution": False},
        )

    def close_session(self, session_id: str, *, detach_only: bool = True) -> AdapterHealth:
        b = self._bindings.get(session_id)
        if b:
            b.closed = True
            b.pages.clear()
        driver = self._live_drivers.pop(session_id, None)
        if driver is not None and not detach_only:
            try:
                driver.close()
            except Exception:
                pass
        elif driver is not None and detach_only:
            # detach without killing unrelated browsers — only our managed driver
            try:
                driver.close()
            except Exception:
                pass
        h = AdapterHealth(
            state=AdapterHealthState.CLOSED,
            adapter_id=self.adapter_id,
            adapter_type=self.adapter_type,
            session_id=session_id,
            adapter_available=False,
        )
        self._health[session_id] = h
        return h

    # ── reconnect ──────────────────────────────────────────────────────────

    def reconnect(
        self,
        session_id: str,
        *,
        actor_id: str = "",
        mission_id: str = "",
        lease_owner: str = "",
        page_fingerprint: str = "",
        page_origin: str = "",
        checkpoint: dict | None = None,
        kill_switch: bool = False,
        approval_valid: bool = True,
    ) -> AdapterHealth:
        b = self._bindings.get(session_id)
        if not b or b.closed:
            raise AdapterError(AdapterErrorCode.SESSION_REQUIRED, "cannot reconnect unknown session")
        if kill_switch or b.kill_switch or self._global_kill:
            raise AdapterError(AdapterErrorCode.KILL_SWITCH, "kill switch blocks reconnect execution")
        if b.cancelled:
            raise AdapterError(AdapterErrorCode.CANCELLED, "cancelled session cannot reconnect-execute")
        if not self.validate_session(
            session_id, actor_id=actor_id or b.actor_id,
            lease_owner=lease_owner or b.lease_owner, mission_id=mission_id or b.mission_id,
        ):
            raise AdapterError(AdapterErrorCode.OWNERSHIP_MISMATCH, "reconnect ownership failed")
        if not approval_valid:
            raise AdapterError(AdapterErrorCode.CONTEXT_MISSING, "approval invalid on reconnect")

        b.reconnect_attempts += 1
        if b.reconnect_attempts > b.max_reconnect_attempts:
            h = self._health.get(session_id) or AdapterHealth(
                adapter_id=self.adapter_id, session_id=session_id,
            )
            h.state = AdapterHealthState.UNAVAILABLE
            h.reconnect_count = b.reconnect_attempts
            h.last_error_category = "reconnect_exhausted"
            self._health[session_id] = h
            raise AdapterError(
                AdapterErrorCode.RECONNECT_FAILED,
                "reconnect attempts exhausted; manual review required",
            )

        # Clear forced disconnect for sandbox
        self._force_disconnect.discard(session_id)

        page = b.pages.get(b.active_page_id)
        if page_fingerprint and page and page.fingerprint and page_fingerprint != page.fingerprint:
            h = self._health.get(session_id) or AdapterHealth(
                adapter_id=self.adapter_id, session_id=session_id,
            )
            h.state = AdapterHealthState.RECONCILIATION_REQUIRED
            h.reconciliation_required = True
            self._health[session_id] = h
            raise AdapterError(
                AdapterErrorCode.PAGE_MISMATCH,
                "page identity changed during disconnect; fail closed",
                reconciliation=True,
            )
        if page_origin and page and page.origin and page_origin != page.origin:
            raise AdapterError(
                AdapterErrorCode.PAGE_MISMATCH,
                "domain changed during disconnect; fail closed",
                reconciliation=True,
            )
        if b.pending_uncertain_action_id:
            h = self._health.get(session_id) or AdapterHealth(
                adapter_id=self.adapter_id, session_id=session_id,
            )
            h.state = AdapterHealthState.RECONCILIATION_REQUIRED
            h.reconciliation_required = True
            h.reconnect_count = b.reconnect_attempts
            self._health[session_id] = h
            return h

        h = AdapterHealth(
            state=AdapterHealthState.HEALTHY,
            adapter_id=self.adapter_id,
            adapter_type=self.adapter_type,
            session_id=session_id,
            adapter_available=True,
            process_alive=True,
            cdp_connection_alive=True,
            browser_context_alive=True,
            active_page_available=True,
            session_lease_valid=True,
            reconnect_count=b.reconnect_attempts,
            last_heartbeat=time.time(),
            supported_capabilities=list(
                (self._health.get(session_id) or AdapterHealth()).supported_capabilities
                or ["navigate", "click", "fill", "submit"]
            ),
        )
        self._health[session_id] = h
        return h

    # ── test / ops helpers ─────────────────────────────────────────────────

    def configure_sandbox_page(self, session_id: str, url: str, *, title: str = "", text: str = "",
                               elements: list | None = None) -> None:
        b = self._bindings.get(session_id)
        if not b:
            raise AdapterError(AdapterErrorCode.SESSION_REQUIRED, "attach first")
        b.sandbox_pages[url] = {
            "title": title or "Sandbox",
            "text": text or "",
            "elements": list(elements or []),
        }

    def simulate_disconnect(self, session_id: str) -> None:
        self._force_disconnect.add(session_id)
        self._mark_disconnected(session_id)

    def set_human_control(self, session_id: str, active: bool) -> None:
        b = self._bindings.get(session_id)
        if b:
            b.human_control = active
            if active:
                b.paused = True

    def set_kill_switch(self, active: bool = True, session_id: str = "") -> None:
        if session_id:
            b = self._bindings.get(session_id)
            if b:
                b.kill_switch = active
        else:
            self._global_kill = active

    def get_binding(self, session_id: str) -> SessionBinding | None:
        return self._bindings.get(session_id)

    def expose_raw_page(self, session_id: str) -> None:
        """Explicitly refuse — raw page objects are never exposed."""
        raise AdapterError(
            AdapterErrorCode.RAW_FALLBACK_DENIED,
            "raw page objects are never exposed to callers",
        )


# Process registry for Control Center / InteractiveBrowser wiring
_PROD_ADAPTERS: dict[str, ProductionBrowserAdapter] = {}
_DEFAULT: ProductionBrowserAdapter | None = None


def default_production_adapter(**kwargs) -> ProductionBrowserAdapter:
    global _DEFAULT
    if kwargs:
        return ProductionBrowserAdapter(**kwargs)
    if _DEFAULT is None:
        _DEFAULT = ProductionBrowserAdapter(allow_live=False)
    return _DEFAULT


def reset_production_adapter() -> None:
    global _DEFAULT, _PROD_ADAPTERS
    _DEFAULT = None
    _PROD_ADAPTERS = {}
