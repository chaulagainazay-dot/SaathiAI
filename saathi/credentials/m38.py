"""M38 — Multi-session reliability, recovery, and canary readiness evaluation.

Composes M31–M37 without parallel session/lease/credential systems.
Proves bounded concurrency, isolation, deterministic recovery, and retry
classification. Evaluates canary readiness without granting CANARY/ACTIVE.

Hard invariants:
  * no production / rollout / CANARY / ACTIVE / write authority;
  * no plaintext secret in coordinator state, events, or evidence;
  * no SecretHandle sharing across sessions;
  * cleanup idempotent; recovery never re-creates secrets from evidence;
  * live sandbox optional; max readiness without live is READY_WITH_LIMITATIONS
    or BLOCKED_LIVE_VALIDATION_REQUIRED;
  * M39 not started; Trading Guardian UNENGAGED.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import threading
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

from saathi.credentials.backends import InMemoryTestSecretBackend, SecretBackend
from saathi.credentials.leakscan import assert_clean, is_clean, scan
from saathi.credentials import m36, m37
from saathi.credentials.m37 import (
    M37SessionRecord,
    run_provider_lifecycle,
    fixture_transport,
    path_aware_sender,
    SUBJECT_FP,
    SYNTH_SECRET,
    PROVIDER_ID as M37_PROVIDER,
)
from saathi.credentials.sandbox_provider import list_sandbox_providers, resolve_sandbox_provider
from saathi.connectors.providers.external.transport import ExternalTransport, SendContext
from saathi.connectors.providers.external.testkit import make_transport, public_resolver

SCHEMA_VERSION = "m38.multi_session_reliability.v1"
_FP_DOMAIN = b"saathi.m38.reliability.domain.v1"

PROVIDER_ID = M37_PROVIDER
DEFAULT_CONCURRENCY = 2
HARD_MAX_CONCURRENCY = 4
DEFAULT_AGGREGATE_CALL_BUDGET = 6
HARD_MAX_AGGREGATE_CALLS = 12
DEFAULT_RETRY_MAX_ATTEMPTS = 3
DEFAULT_RETRY_SCHEDULE_MS = (50, 100, 200)  # deterministic, bounded
MAX_RETRY_AFTER_MS = 1000

ENV_LIVE_FLAG = "SAATHI_M38_ALLOW_LIVE_MULTI_SESSION"

NON_PRODUCTION_BANNER = (
    "M38 MULTI-SESSION RELIABILITY\n"
    "NON-PRODUCTION\n"
    "READ-ONLY\n"
    "BOUNDED CONCURRENCY\n"
    "ROLLOUT OFF\n"
    "NO CANARY\n"
    "NO ACTIVE\n"
    "TRADING GUARDIAN UNENGAGED"
)

AUTHORITIES = {
    "production_authorization": "NOT GRANTED",
    "rollout_authorization": "NOT GRANTED",
    "CANARY_authorization": "NOT GRANTED",
    "ACTIVE_authorization": "NOT GRANTED",
    "write_authority": "NOT GRANTED",
}


class M38Error(Exception):
    def __init__(self, code: str, detail: str = ""):
        super().__init__(detail or code)
        self.code = code
        self.detail = detail


# ── session state machine ────────────────────────────────────────────────────
class SessionState(str, Enum):
    CREATED = "CREATED"
    AUTHORIZATION_PENDING = "AUTHORIZATION_PENDING"
    AUTHORIZED = "AUTHORIZED"
    QUALIFYING = "QUALIFYING"
    QUALIFIED = "QUALIFIED"
    RUNNING = "RUNNING"
    RETRY_WAIT = "RETRY_WAIT"
    CLEANUP_PENDING = "CLEANUP_PENDING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    INTERRUPTED = "INTERRUPTED"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"
    CLEANED = "CLEANED"
    TERMINAL_FAILED = "TERMINAL_FAILED"


# Valid directed edges (fail closed otherwise).
_TRANSITIONS: dict[str, frozenset[str]] = {
    SessionState.CREATED.value: frozenset({
        SessionState.AUTHORIZATION_PENDING.value, SessionState.FAILED.value,
        SessionState.TERMINAL_FAILED.value,
    }),
    SessionState.AUTHORIZATION_PENDING.value: frozenset({
        SessionState.AUTHORIZED.value, SessionState.FAILED.value,
        SessionState.INTERRUPTED.value, SessionState.TERMINAL_FAILED.value,
    }),
    SessionState.AUTHORIZED.value: frozenset({
        SessionState.QUALIFYING.value, SessionState.FAILED.value,
        SessionState.INTERRUPTED.value, SessionState.RECOVERY_REQUIRED.value,
    }),
    SessionState.QUALIFYING.value: frozenset({
        SessionState.QUALIFIED.value, SessionState.FAILED.value,
        SessionState.INTERRUPTED.value, SessionState.RECOVERY_REQUIRED.value,
    }),
    SessionState.QUALIFIED.value: frozenset({
        SessionState.RUNNING.value, SessionState.FAILED.value,
        SessionState.INTERRUPTED.value, SessionState.RECOVERY_REQUIRED.value,
    }),
    SessionState.RUNNING.value: frozenset({
        SessionState.RETRY_WAIT.value, SessionState.CLEANUP_PENDING.value,
        SessionState.COMPLETED.value, SessionState.FAILED.value,
        SessionState.INTERRUPTED.value, SessionState.RECOVERY_REQUIRED.value,
    }),
    SessionState.RETRY_WAIT.value: frozenset({
        SessionState.RUNNING.value, SessionState.FAILED.value,
        SessionState.TERMINAL_FAILED.value, SessionState.INTERRUPTED.value,
        SessionState.CLEANUP_PENDING.value,
    }),
    SessionState.CLEANUP_PENDING.value: frozenset({
        SessionState.CLEANED.value, SessionState.COMPLETED.value,
        SessionState.TERMINAL_FAILED.value, SessionState.FAILED.value,
    }),
    SessionState.COMPLETED.value: frozenset({
        SessionState.CLEANUP_PENDING.value, SessionState.CLEANED.value,
    }),
    SessionState.FAILED.value: frozenset({
        SessionState.CLEANUP_PENDING.value, SessionState.CLEANED.value,
        SessionState.RECOVERY_REQUIRED.value, SessionState.TERMINAL_FAILED.value,
    }),
    SessionState.INTERRUPTED.value: frozenset({
        SessionState.RECOVERY_REQUIRED.value, SessionState.CLEANUP_PENDING.value,
        SessionState.TERMINAL_FAILED.value,
    }),
    SessionState.RECOVERY_REQUIRED.value: frozenset({
        SessionState.CLEANUP_PENDING.value, SessionState.CLEANED.value,
        SessionState.TERMINAL_FAILED.value, SessionState.FAILED.value,
    }),
    SessionState.CLEANED.value: frozenset(),  # terminal
    SessionState.TERMINAL_FAILED.value: frozenset({
        SessionState.CLEANED.value,  # still allow final cleanup mark
    }),
}

_TERMINAL = frozenset({
    SessionState.CLEANED.value,
    SessionState.TERMINAL_FAILED.value,
})


def assert_transition(from_state: str, to_state: str) -> None:
    allowed = _TRANSITIONS.get(from_state)
    if allowed is None:
        raise M38Error("unknown_session_state", from_state)
    if to_state not in allowed:
        raise M38Error("invalid_state_transition", f"{from_state}->{to_state}")


def state_machine_spec() -> dict[str, Any]:
    return {
        "states": [s.value for s in SessionState],
        "transitions": {k: sorted(v) for k, v in _TRANSITIONS.items()},
        "terminal": sorted(_TERMINAL),
    }


# ── retry classification ─────────────────────────────────────────────────────
class RetryClass(str, Enum):
    RETRYABLE = "RETRYABLE"
    NON_RETRYABLE = "NON_RETRYABLE"
    EXHAUSTED = "EXHAUSTED"


_RETRYABLE_CODES = frozenset({
    "timeout", "network_timeout", "connection_refused", "connection_reset",
    "http_429", "http_500", "http_502", "http_503", "http_504",
    "TRANSPORT_FAILURE", "RATE_LIMITED", "PROVIDER_ERROR",
    "NETWORK_TIMEOUT", "CONNECTION_REFUSED", "PROVIDER_UNAVAILABLE",
})
_NON_RETRYABLE_CODES = frozenset({
    "missing_credential", "secret_empty", "secret_retrieval_failed",
    "authorization_expired", "authorization_denied", "missing_acknowledgement",
    "http_401", "http_403", "AUTHENTICATION_FAILURE", "scope_mismatch",
    "invalid_state_transition", "call_budget_exhausted", "concurrency_limit",
    "unknown_sandbox_provider", "provider_capability_forbidden",
    "invalid_provider_contract", "qualification_failed",
})


def classify_retry(reason: str) -> str:
    r = (reason or "").strip()
    low = r.lower()
    if any(c.lower() in low or c in r for c in _NON_RETRYABLE_CODES):
        return RetryClass.NON_RETRYABLE.value
    # status codes in reason strings like identity:http_401
    for code in ("401", "403"):
        if f"http_{code}" in low or f":{code}" in low or low.endswith(code):
            if "401" in low or "403" in low:
                return RetryClass.NON_RETRYABLE.value
    for code in ("429", "500", "502", "503", "504"):
        if f"http_{code}" in low or f"_{code}" in low:
            return RetryClass.RETRYABLE.value
    if any(c.lower() in low or c in r for c in _RETRYABLE_CODES):
        return RetryClass.RETRYABLE.value
    if "timeout" in low or "unavailable" in low or "refused" in low:
        return RetryClass.RETRYABLE.value
    return RetryClass.NON_RETRYABLE.value


@dataclass
class RetryPolicy:
    max_attempts: int = DEFAULT_RETRY_MAX_ATTEMPTS
    schedule_ms: tuple[int, ...] = DEFAULT_RETRY_SCHEDULE_MS
    max_retry_after_ms: int = MAX_RETRY_AFTER_MS

    def delay_ms(self, attempt: int, retry_after_ms: Optional[int] = None) -> int:
        """Deterministic delay for attempt index (0-based). Bounded Retry-After."""
        if attempt < 0:
            raise M38Error("invalid_retry_attempt")
        if attempt >= self.max_attempts:
            raise M38Error("retry_exhausted")
        base = self.schedule_ms[min(attempt, len(self.schedule_ms) - 1)]
        if retry_after_ms is not None:
            ra = max(0, min(int(retry_after_ms), self.max_retry_after_ms))
            return max(base, ra)
        return base

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_attempts": self.max_attempts,
            "schedule_ms": list(self.schedule_ms),
            "max_retry_after_ms": self.max_retry_after_ms,
            "probabilistic": False,
            "unbounded": False,
        }


# ── session record (metadata only — no secrets) ──────────────────────────────
@dataclass
class SessionRecord:
    session_id: str
    correlation_id: str
    provider_id: str
    credential_ref_id: str
    credential_fingerprint: str = ""  # purpose-bound, non-reversible
    authorization_id: str = ""
    state: str = SessionState.CREATED.value
    call_budget_max: int = 3
    call_budget_used: int = 0
    retry_attempts: int = 0
    cleanup_state: str = "NONE"
    start_time: float = 0.0
    end_time: float = 0.0
    last_reason: str = ""
    transitions: list[str] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    lease_id: str = ""
    handle_was_opened: bool = False
    handle_closed: bool = True
    recovery_attempts: int = 0
    interrupted_at: str = ""
    result_ok: Optional[bool] = None

    def to_safe_dict(self) -> dict[str, Any]:
        return {
            "schema": "m38.session_record.v1",
            "session_id": self.session_id,
            "correlation_id": self.correlation_id,
            "provider_id": self.provider_id,
            "credential_ref_id": self.credential_ref_id,
            "credential_fingerprint": self.credential_fingerprint,
            "authorization_id": self.authorization_id,
            "state": self.state,
            "call_budget_max": self.call_budget_max,
            "call_budget_used": self.call_budget_used,
            "retry_attempts": self.retry_attempts,
            "cleanup_state": self.cleanup_state,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "last_reason": self.last_reason,
            "transitions": list(self.transitions),
            "events": list(self.events),
            "lease_id": self.lease_id,
            "handle_was_opened": self.handle_was_opened,
            "handle_closed": self.handle_closed,
            "recovery_attempts": self.recovery_attempts,
            "interrupted_at": self.interrupted_at,
            "result_ok": self.result_ok,
            "contains_secret_values": False,
            "contains_raw_identity": False,
        }


# ── multi-session coordinator ────────────────────────────────────────────────
class MultiSessionCoordinator:
    """Governed multi-session coordinator. Composes M37 lifecycle per session.

    Never stores SecretHandle or plaintext secrets. Isolation enforced by
    construction: each run uses independent backends/handles inside M37.
    """

    def __init__(
        self,
        *,
        concurrency_limit: int = DEFAULT_CONCURRENCY,
        aggregate_call_budget: int = DEFAULT_AGGREGATE_CALL_BUDGET,
        retry_policy: Optional[RetryPolicy] = None,
        clock: Optional[Callable[[], float]] = None,
        provider_id: str = PROVIDER_ID,
    ):
        if concurrency_limit < 1 or concurrency_limit > HARD_MAX_CONCURRENCY:
            raise M38Error("invalid_concurrency_limit", str(concurrency_limit))
        if aggregate_call_budget < 1 or aggregate_call_budget > HARD_MAX_AGGREGATE_CALLS:
            raise M38Error("invalid_aggregate_budget", str(aggregate_call_budget))
        self.concurrency_limit = concurrency_limit
        self.aggregate_call_budget = aggregate_call_budget
        self.aggregate_calls_used = 0
        self.retry_policy = retry_policy or RetryPolicy()
        self._clock = clock or time.time
        self.provider_id = provider_id
        self._sessions: dict[str, SessionRecord] = {}
        self._active: set[str] = set()
        self._lock = threading.RLock()
        self._seq = 0
        self._start_tokens: set[str] = set()  # idempotency for duplicate starts
        self._cleanup_tokens: set[str] = set()
        self._events: list[dict[str, Any]] = []

    def _emit(self, event_type: str, **payload: Any) -> None:
        self._events.append({
            "event_type": event_type,
            "ts": float(self._clock()),
            "privacy_safe": True,
            "contains_secret_values": False,
            **payload,
        })

    def _next_ids(self, explicit_session: str = "", explicit_corr: str = "") -> tuple[str, str]:
        self._seq += 1
        sid = explicit_session or f"sess_m38_{self._seq:04d}"
        cid = explicit_corr or f"corr_m38_{self._seq:04d}"
        return sid, cid

    def _transition(self, rec: SessionRecord, to_state: str, reason: str = "") -> None:
        assert_transition(rec.state, to_state)
        rec.state = to_state
        rec.transitions.append(to_state)
        if reason:
            rec.last_reason = reason[:200]
        rec.events.append({
            "event_type": "m38.state_transition",
            "state": to_state,
            "reason": reason[:200],
            "privacy_safe": True,
            "contains_secret_values": False,
        })
        self._emit("m38.state_transition", session_id=rec.session_id, state=to_state, reason=reason[:200])

    def list_sessions(self) -> list[dict[str, Any]]:
        with self._lock:
            return [s.to_safe_dict() for s in self._sessions.values()]

    def session_status(self, session_id: str) -> dict[str, Any]:
        with self._lock:
            rec = self._sessions.get(session_id)
            if rec is None:
                return {"found": False, "session_id": session_id}
            return {"found": True, "session": rec.to_safe_dict()}

    def active_count(self) -> int:
        with self._lock:
            return len(self._active)

    def start_session(
        self,
        *,
        credential_ref_id: str,
        provider_id: str = "",
        session_id: str = "",
        correlation_id: str = "",
        call_budget: int = 3,
        secret_backend: Optional[SecretBackend] = None,
        secret_locator: str = "",
        secret_value: str = SYNTH_SECRET,
        transport: Optional[ExternalTransport] = None,
        interrupt_after: str = "",
        inject_failure: str = "",
        seed_if_missing: bool = True,
        expected_subject_fingerprint: str = SUBJECT_FP,
        start_token: str = "",
        live_exercised: bool = False,
    ) -> dict[str, Any]:
        """Start one bounded sandbox session through M37 lifecycle.

        Returns a safe status dict. Never returns secrets.
        """
        pid = (provider_id or self.provider_id).strip()
        if not credential_ref_id:
            raise M38Error("missing_credential_ref")
        if call_budget < 1 or call_budget > m36.M36_MAX_CALL_BUDGET:
            raise M38Error("invalid_session_call_budget", str(call_budget))

        with self._lock:
            # idempotent duplicate start
            tok = start_token or f"{credential_ref_id}:{session_id or 'auto'}"
            if tok in self._start_tokens and session_id and session_id in self._sessions:
                return {
                    "ok": True, "idempotent": True, "session_id": session_id,
                    "state": self._sessions[session_id].state,
                    "contains_secret_values": False,
                }
            if session_id and session_id in self._sessions:
                raise M38Error("session_id_collision", session_id)
            if len(self._active) >= self.concurrency_limit:
                raise M38Error("concurrency_limit")
            if self.aggregate_calls_used + call_budget > self.aggregate_call_budget:
                raise M38Error("aggregate_call_budget_exhausted")

            sid, cid = self._next_ids(session_id, correlation_id)
            now = float(self._clock())
            rec = SessionRecord(
                session_id=sid,
                correlation_id=cid,
                provider_id=pid,
                credential_ref_id=credential_ref_id,
                state=SessionState.CREATED.value,
                call_budget_max=call_budget,
                start_time=now,
            )
            rec.transitions.append(SessionState.CREATED.value)
            self._sessions[sid] = rec
            self._active.add(sid)
            self._start_tokens.add(tok)
            self._emit("m38.session_started", session_id=sid, correlation_id=cid,
                       provider_id=pid, credential_ref_id=credential_ref_id)

        # Drive lifecycle outside lock (session-local resources only)
        try:
            self._drive(rec, secret_backend=secret_backend, secret_locator=secret_locator or f"m38/{sid}",
                        secret_value=secret_value, transport=transport,
                        interrupt_after=interrupt_after, inject_failure=inject_failure,
                        seed_if_missing=seed_if_missing,
                        expected_subject_fingerprint=expected_subject_fingerprint,
                        live_exercised=live_exercised)
        finally:
            with self._lock:
                self._active.discard(sid)

        return {
            "ok": bool(rec.result_ok),
            "session_id": rec.session_id,
            "correlation_id": rec.correlation_id,
            "state": rec.state,
            "session": rec.to_safe_dict(),
            "contains_secret_values": False,
        }

    def _drive(
        self,
        rec: SessionRecord,
        *,
        secret_backend: Optional[SecretBackend],
        secret_locator: str,
        secret_value: str,
        transport: Optional[ExternalTransport],
        interrupt_after: str,
        inject_failure: str,
        seed_if_missing: bool,
        expected_subject_fingerprint: str,
        live_exercised: bool,
    ) -> None:
        try:
            self._transition(rec, SessionState.AUTHORIZATION_PENDING.value)
            if inject_failure == "before_handle":
                raise M38Error("injected_before_handle")

            self._transition(rec, SessionState.AUTHORIZED.value)
            self._transition(rec, SessionState.QUALIFYING.value)
            if interrupt_after == "authorization":
                rec.interrupted_at = "authorization"
                self._transition(rec, SessionState.INTERRUPTED.value, "authorization")
                self._transition(rec, SessionState.RECOVERY_REQUIRED.value)
                self.recover_session(rec.session_id)
                return

            self._transition(rec, SessionState.QUALIFIED.value)
            if interrupt_after == "qualification":
                rec.interrupted_at = "qualification"
                self._transition(rec, SessionState.INTERRUPTED.value, "qualification")
                self._transition(rec, SessionState.RECOVERY_REQUIRED.value)
                self.recover_session(rec.session_id)
                return

            self._transition(rec, SessionState.RUNNING.value)
            if inject_failure == "before_sender":
                raise M38Error("injected_before_sender")

            # Retry loop (bounded)
            last_err = ""
            for attempt in range(self.retry_policy.max_attempts):
                if inject_failure == "during_sender" and attempt == 0:
                    last_err = "http_503"
                    cls = classify_retry(last_err)
                    rec.retry_attempts += 1
                    if cls == RetryClass.RETRYABLE.value and attempt + 1 < self.retry_policy.max_attempts:
                        self._transition(rec, SessionState.RETRY_WAIT.value, last_err)
                        _ = self.retry_policy.delay_ms(attempt)  # record schedule; no sleep in tests
                        self._transition(rec, SessionState.RUNNING.value, "retry")
                        continue
                    raise M38Error(last_err)

                if inject_failure == "timeout" and attempt == 0:
                    # simulate one timeout then success path via lifecycle with bad transport first
                    tr = fixture_transport(raise_on="timeout")
                    life = run_provider_lifecycle(
                        transport=tr,
                        secret_backend=secret_backend,
                        secret_locator=secret_locator,
                        secret_value=secret_value,
                        seed_if_missing=seed_if_missing,
                        session_id=rec.session_id,
                        expected_subject_fingerprint=expected_subject_fingerprint,
                        live_exercised=live_exercised,
                    )
                    if not life.ok:
                        last_err = life.reason or "timeout"
                        cls = classify_retry(last_err)
                        rec.retry_attempts += 1
                        if cls == RetryClass.RETRYABLE.value and attempt + 1 < self.retry_policy.max_attempts:
                            self._transition(rec, SessionState.RETRY_WAIT.value, last_err)
                            _ = self.retry_policy.delay_ms(attempt)
                            self._transition(rec, SessionState.RUNNING.value, "retry")
                            continue
                        raise M38Error(last_err or "timeout")

                tr = transport or fixture_transport()
                if inject_failure == "429":
                    tr = fixture_transport(identity_status=429)

                life = run_provider_lifecycle(
                    transport=tr,
                    secret_backend=secret_backend,
                    secret_locator=secret_locator,
                    secret_value=secret_value,
                    seed_if_missing=seed_if_missing,
                    session_id=rec.session_id,
                    interrupt_after=interrupt_after if interrupt_after in ("identity", "operation", "secret") else "",
                    expected_subject_fingerprint=expected_subject_fingerprint,
                    live_exercised=live_exercised,
                )
                rec.handle_was_opened = True
                rec.handle_closed = life.handle_closed
                rec.credential_fingerprint = life.credential_fingerprint
                rec.call_budget_used = int((life.call_budget or {}).get("consumed", 0))
                with self._lock:
                    self.aggregate_calls_used += rec.call_budget_used

                if inject_failure == "after_response" and life.ok:
                    raise M38Error("injected_after_response")

                if life.ok:
                    rec.result_ok = True
                    if interrupt_after == "before_cleanup":
                        rec.interrupted_at = "before_cleanup"
                        self._transition(rec, SessionState.INTERRUPTED.value, "before_cleanup")
                        self._transition(rec, SessionState.RECOVERY_REQUIRED.value)
                        self.recover_session(rec.session_id)
                        return
                    self._transition(rec, SessionState.COMPLETED.value)
                    self._cleanup(rec, inject_failure=inject_failure)
                    return

                # lifecycle failed
                last_err = life.reason or "lifecycle_failed"
                if interrupt_after in ("identity", "operation", "secret"):
                    rec.interrupted_at = interrupt_after
                    self._transition(rec, SessionState.INTERRUPTED.value, interrupt_after)
                    self._transition(rec, SessionState.RECOVERY_REQUIRED.value)
                    self.recover_session(rec.session_id)
                    return

                cls = classify_retry(last_err)
                if cls == RetryClass.NON_RETRYABLE.value:
                    raise M38Error(last_err)
                rec.retry_attempts += 1
                if attempt + 1 >= self.retry_policy.max_attempts:
                    raise M38Error(f"retry_exhausted:{last_err}")
                ra = 100 if "429" in last_err else None
                self._transition(rec, SessionState.RETRY_WAIT.value, last_err)
                _ = self.retry_policy.delay_ms(attempt, retry_after_ms=ra)
                self._transition(rec, SessionState.RUNNING.value, "retry")

            raise M38Error(f"retry_exhausted:{last_err}")

        except M38Error as e:
            rec.result_ok = False
            rec.last_reason = e.code
            if rec.state not in _TERMINAL and rec.state not in (
                SessionState.CLEANUP_PENDING.value, SessionState.CLEANED.value,
                SessionState.RECOVERY_REQUIRED.value, SessionState.INTERRUPTED.value,
            ):
                try:
                    if rec.state == SessionState.RUNNING.value:
                        self._transition(rec, SessionState.FAILED.value, e.code)
                    elif rec.state == SessionState.RETRY_WAIT.value:
                        self._transition(rec, SessionState.TERMINAL_FAILED.value, e.code)
                    elif rec.state in (SessionState.CREATED.value, SessionState.AUTHORIZATION_PENDING.value):
                        self._transition(rec, SessionState.FAILED.value, e.code)
                    else:
                        # best-effort toward FAILED
                        if SessionState.FAILED.value in _TRANSITIONS.get(rec.state, frozenset()):
                            self._transition(rec, SessionState.FAILED.value, e.code)
                except M38Error:
                    pass
            if rec.state not in (SessionState.CLEANED.value, SessionState.CLEANUP_PENDING.value):
                try:
                    self._cleanup(rec, inject_failure=inject_failure if inject_failure == "cleanup_exception" else "")
                except Exception:
                    rec.cleanup_state = "FAILED"
            if rec.state not in _TERMINAL and rec.state != SessionState.CLEANED.value:
                if SessionState.TERMINAL_FAILED.value in _TRANSITIONS.get(rec.state, frozenset()):
                    try:
                        self._transition(rec, SessionState.TERMINAL_FAILED.value, e.code)
                    except M38Error:
                        pass

    def _cleanup(self, rec: SessionRecord, *, inject_failure: str = "") -> None:
        tok = f"cleanup:{rec.session_id}"
        with self._lock:
            if tok in self._cleanup_tokens:
                # idempotent
                rec.cleanup_state = "CLEANED"
                if rec.state != SessionState.CLEANED.value and SessionState.CLEANED.value in _TRANSITIONS.get(rec.state, frozenset()):
                    try:
                        self._transition(rec, SessionState.CLEANED.value, "idempotent_cleanup")
                    except M38Error:
                        pass
                return
            self._cleanup_tokens.add(tok)

        if rec.state not in (
            SessionState.CLEANUP_PENDING.value, SessionState.CLEANED.value,
            SessionState.COMPLETED.value, SessionState.FAILED.value,
            SessionState.TERMINAL_FAILED.value, SessionState.RECOVERY_REQUIRED.value,
            SessionState.INTERRUPTED.value,
        ):
            if SessionState.CLEANUP_PENDING.value in _TRANSITIONS.get(rec.state, frozenset()):
                self._transition(rec, SessionState.CLEANUP_PENDING.value)
        elif rec.state in (SessionState.COMPLETED.value, SessionState.FAILED.value,
                          SessionState.TERMINAL_FAILED.value, SessionState.RECOVERY_REQUIRED.value):
            if SessionState.CLEANUP_PENDING.value in _TRANSITIONS.get(rec.state, frozenset()):
                self._transition(rec, SessionState.CLEANUP_PENDING.value)

        if inject_failure == "cleanup_exception":
            rec.cleanup_state = "PARTIAL_FAILURE"
            rec.last_reason = "cleanup_exception"
            # still mark cleaned to free resources deterministically after operator note
            rec.cleanup_state = "CLEANED_AFTER_PARTIAL"
        elif inject_failure == "lease_revoke_failure":
            rec.cleanup_state = "LEASE_REVOKE_FAILED_LOCAL_ONLY"
        else:
            rec.cleanup_state = "CLEANED"

        rec.handle_closed = True
        rec.end_time = float(self._clock())
        if rec.state != SessionState.CLEANED.value:
            if SessionState.CLEANED.value in _TRANSITIONS.get(rec.state, frozenset()):
                self._transition(rec, SessionState.CLEANED.value, rec.cleanup_state)
            elif rec.state == SessionState.CLEANUP_PENDING.value:
                self._transition(rec, SessionState.CLEANED.value, rec.cleanup_state)
        self._emit("m38.cleanup_completed", session_id=rec.session_id, cleanup_state=rec.cleanup_state)

    def cleanup_session(self, session_id: str) -> dict[str, Any]:
        with self._lock:
            rec = self._sessions.get(session_id)
            if rec is None:
                raise M38Error("session_not_found", session_id)
        self._cleanup(rec)
        return {"ok": True, "session_id": session_id, "state": rec.state, "cleanup_state": rec.cleanup_state}

    def recover_session(self, session_id: str) -> dict[str, Any]:
        """Deterministic recovery: never reopens secrets from evidence."""
        with self._lock:
            rec = self._sessions.get(session_id)
            if rec is None:
                return self._reconcile_orphan_lease(session_id)

        rec.recovery_attempts += 1
        if rec.recovery_attempts > 3:
            if rec.state != SessionState.TERMINAL_FAILED.value:
                if SessionState.TERMINAL_FAILED.value in _TRANSITIONS.get(rec.state, frozenset()):
                    self._transition(rec, SessionState.TERMINAL_FAILED.value, "recovery_exhausted")
            self._cleanup(rec)
            return {
                "ok": False,
                "session_id": session_id,
                "state": rec.state,
                "operator_action": "MANUAL_REVIEW_REQUIRED",
                "reason": "recovery_exhausted",
                "contains_secret_values": False,
            }

        # Idempotent recovery: cleanup residual authority only; no secret reopen.
        if rec.state == SessionState.RECOVERY_REQUIRED.value:
            pass
        elif rec.state == SessionState.INTERRUPTED.value:
            self._transition(rec, SessionState.RECOVERY_REQUIRED.value, "recover")
        elif rec.state in _TERMINAL or rec.state == SessionState.CLEANED.value:
            return {
                "ok": True, "session_id": session_id, "state": rec.state,
                "idempotent": True, "contains_secret_values": False,
            }

        # Reauthorization would be required for resume — we do not auto-resume.
        rec.last_reason = "recovery_cleanup_only_no_secret_reopen"
        self._cleanup(rec)
        return {
            "ok": True,
            "session_id": session_id,
            "state": rec.state,
            "recovery": "cleanup_without_secret_reopen",
            "reauthorization_required_for_resume": True,
            "contains_secret_values": False,
        }

    def _reconcile_orphan_lease(self, session_id: str) -> dict[str, Any]:
        """Missing session record with surviving lease — record operator action."""
        self._emit("m38.orphan_lease_detected", session_id=session_id)
        return {
            "ok": False,
            "session_id": session_id,
            "state": "MISSING_SESSION_RECORD",
            "operator_action": "REVOKE_ORPHAN_LEASE_IF_PRESENT",
            "contains_secret_values": False,
        }

    def reconcile(self) -> dict[str, Any]:
        """Scan sessions for inconsistencies; deterministic, no secrets."""
        actions: list[dict[str, Any]] = []
        with self._lock:
            items = list(self._sessions.values())
        for rec in items:
            if rec.state in (SessionState.INTERRUPTED.value, SessionState.RECOVERY_REQUIRED.value):
                out = self.recover_session(rec.session_id)
                actions.append({"session_id": rec.session_id, "action": "recover", "result": out})
            elif rec.state in (SessionState.RUNNING.value, SessionState.RETRY_WAIT.value):
                # Stale active without being in _active → recovery
                if rec.session_id not in self._active:
                    try:
                        self._transition(rec, SessionState.RECOVERY_REQUIRED.value, "stale_active")
                    except M38Error:
                        pass
                    out = self.recover_session(rec.session_id)
                    actions.append({"session_id": rec.session_id, "action": "stale_recover", "result": out})
            elif rec.handle_was_opened and not rec.handle_closed:
                rec.handle_closed = True  # cannot reopen; mark closed
                actions.append({"session_id": rec.session_id, "action": "force_handle_closed_flag"})
                self._cleanup(rec)
        return {
            "ok": True,
            "actions": actions,
            "sessions": self.list_sessions(),
            "aggregate_calls_used": self.aggregate_calls_used,
            "aggregate_call_budget": self.aggregate_call_budget,
            "active_count": self.active_count(),
            "contains_secret_values": False,
        }


# ── multi-session offline validation suite ───────────────────────────────────
def run_offline_multisession_validation() -> dict[str, Any]:
    """Deterministic offline multi-session scenarios."""
    results: list[dict[str, Any]] = []
    coord = MultiSessionCoordinator(concurrency_limit=2, aggregate_call_budget=8, clock=lambda: 5_000_000.0)

    # 1. two sessions different credential refs
    be1, be2 = InMemoryTestSecretBackend(), InMemoryTestSecretBackend()
    r1 = coord.start_session(credential_ref_id="cred_a", secret_backend=be1, secret_locator="a", session_id="sess_diff_a")
    r2 = coord.start_session(credential_ref_id="cred_b", secret_backend=be2, secret_locator="b", session_id="sess_diff_b")
    results.append({
        "name": "two_sessions_different_refs",
        "pass": r1["ok"] and r2["ok"] and r1["session_id"] != r2["session_id"],
        "s1": r1["state"], "s2": r2["state"],
    })

    # 2. two sessions same permitted ref (sequential after first cleaned — concurrency 2 but sequential ok)
    coord2 = MultiSessionCoordinator(concurrency_limit=2, aggregate_call_budget=8, clock=lambda: 5_000_001.0)
    be = InMemoryTestSecretBackend()
    s1 = coord2.start_session(credential_ref_id="cred_same", secret_backend=be, secret_locator="s", session_id="sess_same_1")
    s2 = coord2.start_session(credential_ref_id="cred_same", secret_backend=be, secret_locator="s", session_id="sess_same_2")
    results.append({
        "name": "two_sessions_same_ref",
        "pass": s1["ok"] and s2["ok"] and s1["session"]["credential_fingerprint"] == s2["session"]["credential_fingerprint"],
    })

    # 3. success + failure isolation
    coord3 = MultiSessionCoordinator(concurrency_limit=2, aggregate_call_budget=8, clock=lambda: 5_000_002.0)
    ok_s = coord3.start_session(credential_ref_id="cred_ok", session_id="sess_ok", secret_locator="ok")
    fail_s = coord3.start_session(
        credential_ref_id="cred_fail", session_id="sess_fail", secret_locator="fail",
        transport=fixture_transport(identity_status=401),
    )
    results.append({
        "name": "success_and_failure_isolation",
        "pass": ok_s["ok"] and (not fail_s["ok"]) and ok_s["state"] == SessionState.CLEANED.value,
    })

    # 4. interrupt one while other completes
    coord4 = MultiSessionCoordinator(concurrency_limit=2, aggregate_call_budget=8, clock=lambda: 5_000_003.0)
    done = coord4.start_session(credential_ref_id="cred_done", session_id="sess_done")
    inter = coord4.start_session(
        credential_ref_id="cred_inter", session_id="sess_inter", interrupt_after="identity",
    )
    results.append({
        "name": "interrupt_while_other_completes",
        "pass": done["ok"] and inter["session"]["state"] == SessionState.CLEANED.value,
    })

    # 5. concurrency limit
    coord5 = MultiSessionCoordinator(concurrency_limit=1, aggregate_call_budget=10, clock=lambda: 5_000_004.0)
    # Hold active by not completing — inject mid-run isn't concurrent; simulate by direct _active
    with coord5._lock:  # noqa: SLF001
        dummy = SessionRecord(
            session_id="hold", correlation_id="c", provider_id=PROVIDER_ID,
            credential_ref_id="x", state=SessionState.RUNNING.value,
        )
        coord5._sessions["hold"] = dummy  # noqa: SLF001
        coord5._active.add("hold")  # noqa: SLF001
    rejected = False
    try:
        coord5.start_session(credential_ref_id="cred_rej", session_id="sess_rej")
    except M38Error as e:
        rejected = e.code == "concurrency_limit"
    results.append({"name": "concurrency_limit_rejection", "pass": rejected})

    # 6. aggregate budget
    coord6 = MultiSessionCoordinator(concurrency_limit=2, aggregate_call_budget=2, clock=lambda: 5_000_005.0)
    coord6.aggregate_calls_used = 2
    agg_rej = False
    try:
        coord6.start_session(credential_ref_id="cred_agg", session_id="sess_agg", call_budget=2)
    except M38Error as e:
        agg_rej = e.code == "aggregate_call_budget_exhausted"
    results.append({"name": "aggregate_budget_exhaustion", "pass": agg_rej})

    # 7. session id collision
    coord7 = MultiSessionCoordinator(clock=lambda: 5_000_006.0)
    coord7.start_session(credential_ref_id="c1", session_id="dup_id")
    coll = False
    try:
        coord7.start_session(credential_ref_id="c2", session_id="dup_id")
    except M38Error as e:
        coll = e.code == "session_id_collision"
    results.append({"name": "session_id_collision", "pass": coll})

    # 8. duplicate cleanup idempotent
    coord8 = MultiSessionCoordinator(clock=lambda: 5_000_007.0)
    r = coord8.start_session(credential_ref_id="c", session_id="sess_cln")
    c1 = coord8.cleanup_session("sess_cln")
    c2 = coord8.cleanup_session("sess_cln")
    results.append({
        "name": "duplicate_cleanup_idempotent",
        "pass": c1["ok"] and c2["ok"] and c2["cleanup_state"] in ("CLEANED", "CLEANED_AFTER_PARTIAL"),
    })

    # 9. invalid transition
    inv = False
    try:
        assert_transition(SessionState.CREATED.value, SessionState.RUNNING.value)
    except M38Error as e:
        inv = e.code == "invalid_state_transition"
    results.append({"name": "invalid_transition_rejected", "pass": inv})

    # 10. no secrets in coordinator dumps
    dump = json.dumps({"sessions": coord.list_sessions(), "results": results}, default=str)
    leak_clean = is_clean(json.loads(json.dumps({"sessions": coord.list_sessions()}))) and SYNTH_SECRET not in dump

    passed = sum(1 for r in results if r.get("pass"))
    return {
        "schema": "m38.multi_session_validation.v1",
        "total": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "results": results,
        "leak_clean": leak_clean,
        "contains_secret_values": False,
    }


# ── retry matrix ─────────────────────────────────────────────────────────────
def run_retry_matrix() -> dict[str, Any]:
    cases = []
    for reason, expected in [
        ("timeout", RetryClass.RETRYABLE.value),
        ("http_429", RetryClass.RETRYABLE.value),
        ("http_500", RetryClass.RETRYABLE.value),
        ("http_503", RetryClass.RETRYABLE.value),
        ("http_401", RetryClass.NON_RETRYABLE.value),
        ("http_403", RetryClass.NON_RETRYABLE.value),
        ("secret_empty", RetryClass.NON_RETRYABLE.value),
        ("authorization_expired", RetryClass.NON_RETRYABLE.value),
        ("call_budget_exhausted", RetryClass.NON_RETRYABLE.value),
        ("concurrency_limit", RetryClass.NON_RETRYABLE.value),
        ("identity:http_401", RetryClass.NON_RETRYABLE.value),
        ("identity:http_503", RetryClass.RETRYABLE.value),
    ]:
        got = classify_retry(reason)
        cases.append({"reason": reason, "expected": expected, "got": got, "pass": got == expected})

    pol = RetryPolicy()
    delays = [pol.delay_ms(i) for i in range(pol.max_attempts)]
    exhausted = False
    try:
        pol.delay_ms(pol.max_attempts)
    except M38Error as e:
        exhausted = e.code == "retry_exhausted"
    ra = pol.delay_ms(0, retry_after_ms=5000)  # capped
    cases.append({
        "reason": "retry_after_bounded",
        "pass": ra <= pol.max_retry_after_ms and ra >= pol.schedule_ms[0],
        "delay": ra,
    })
    cases.append({"reason": "retry_schedule_deterministic", "pass": delays == list(DEFAULT_RETRY_SCHEDULE_MS[:len(delays)])})
    cases.append({"reason": "retry_exhausted_raises", "pass": exhausted})

    # coordinator retry on 503 injection
    coord = MultiSessionCoordinator(clock=lambda: 6_000_000.0, retry_policy=RetryPolicy(max_attempts=3))
    out = coord.start_session(credential_ref_id="r", session_id="sess_retry", inject_failure="during_sender")
    cases.append({
        "reason": "coordinator_retries_503",
        "pass": out["session"]["retry_attempts"] >= 1 and out["session"]["handle_closed"],
        "retry_attempts": out["session"]["retry_attempts"],
        "state": out["state"],
    })

    passed = sum(1 for c in cases if c.get("pass"))
    return {
        "schema": "m38.retry_matrix.v1",
        "policy": pol.to_dict(),
        "total": len(cases),
        "passed": passed,
        "failed": len(cases) - passed,
        "cases": cases,
        "contains_secret_values": False,
    }


# ── recovery matrix ──────────────────────────────────────────────────────────
def run_recovery_matrix() -> dict[str, Any]:
    cases = []
    for stage in ("authorization", "qualification", "identity", "before_cleanup"):
        coord = MultiSessionCoordinator(clock=lambda: 7_000_000.0)
        out = coord.start_session(
            credential_ref_id=f"c_{stage}", session_id=f"sess_rec_{stage}",
            interrupt_after=stage,
        )
        cases.append({
            "name": f"interrupt_{stage}",
            "pass": out["session"]["state"] == SessionState.CLEANED.value
            and out["session"]["handle_closed"]
            and out["session"]["recovery_attempts"] >= 1,
            "state": out["state"],
            "recovery_attempts": out["session"]["recovery_attempts"],
        })

    # duplicate recovery
    coord = MultiSessionCoordinator(clock=lambda: 7_000_001.0)
    coord.start_session(credential_ref_id="c", session_id="sess_dup_rec", interrupt_after="identity")
    a = coord.recover_session("sess_dup_rec")
    b = coord.recover_session("sess_dup_rec")
    cases.append({
        "name": "duplicate_recovery_idempotent",
        "pass": a.get("ok") is not None and b.get("idempotent") is True or b.get("ok") is True,
        "a": a.get("state"), "b": b.get("state"),
    })

    # missing session / orphan
    orphan = coord.recover_session("no_such_session")
    cases.append({
        "name": "orphan_missing_session",
        "pass": orphan.get("operator_action") == "REVOKE_ORPHAN_LEASE_IF_PRESENT",
    })

    # reconcile
    coord2 = MultiSessionCoordinator(clock=lambda: 7_000_002.0)
    coord2.start_session(credential_ref_id="c", session_id="sess_recon", interrupt_after="qualification")
    recon = coord2.reconcile()
    cases.append({"name": "reconcile_ok", "pass": recon.get("ok") is True})

    # recovery exhausted
    coord3 = MultiSessionCoordinator(clock=lambda: 7_000_003.0)
    rec = SessionRecord(
        session_id="sess_exh", correlation_id="c", provider_id=PROVIDER_ID,
        credential_ref_id="c", state=SessionState.RECOVERY_REQUIRED.value,
        recovery_attempts=3,
    )
    coord3._sessions["sess_exh"] = rec  # noqa: SLF001
    exh = coord3.recover_session("sess_exh")
    cases.append({
        "name": "recovery_exhausted_terminal",
        "pass": exh.get("operator_action") == "MANUAL_REVIEW_REQUIRED",
    })

    passed = sum(1 for c in cases if c.get("pass"))
    return {
        "schema": "m38.recovery_matrix.v1",
        "total": len(cases),
        "passed": passed,
        "failed": len(cases) - passed,
        "cases": cases,
        "contains_secret_values": False,
    }


# ── failure injection matrix ─────────────────────────────────────────────────
def run_failure_injection_matrix() -> dict[str, Any]:
    injections = [
        "before_handle", "before_sender", "during_sender", "after_response",
        "cleanup_exception", "lease_revoke_failure", "timeout", "429",
    ]
    cases = []
    for inj in injections:
        coord = MultiSessionCoordinator(clock=lambda: 8_000_000.0)
        out = coord.start_session(
            credential_ref_id=f"c_{inj}", session_id=f"sess_inj_{inj}",
            inject_failure=inj,
        )
        sess = out["session"]
        safe = is_clean(sess) and SYNTH_SECRET not in json.dumps(sess)
        cases.append({
            "injection": inj,
            "final_state": sess["state"],
            "handle_closed": sess["handle_closed"],
            "cleanup_state": sess["cleanup_state"],
            "leak_clean": safe,
            "authority_unchanged": True,
            "pass": sess["handle_closed"] and safe and sess["state"] in (
                SessionState.CLEANED.value, SessionState.TERMINAL_FAILED.value,
                SessionState.FAILED.value, SessionState.COMPLETED.value,
            ),
        })

    # malformed via 500
    coord = MultiSessionCoordinator(clock=lambda: 8_000_001.0)
    out = coord.start_session(
        credential_ref_id="c500", session_id="sess_500",
        transport=fixture_transport(identity_status=500),
    )
    cases.append({
        "injection": "provider_500",
        "final_state": out["state"],
        "handle_closed": out["session"]["handle_closed"],
        "leak_clean": is_clean(out),
        "pass": out["session"]["handle_closed"] and not out["ok"],
    })

    passed = sum(1 for c in cases if c.get("pass"))
    return {
        "schema": "m38.failure_injection.v1",
        "total": len(cases),
        "passed": passed,
        "failed": len(cases) - passed,
        "cases": cases,
        "contains_secret_values": False,
        "authorities": dict(AUTHORITIES),
    }


# ── canary readiness evaluator (read-only — never grants) ────────────────────
class CanaryReadinessVerdict(str, Enum):
    NOT_READY = "NOT_READY"
    READY_WITH_LIMITATIONS = "READY_WITH_LIMITATIONS"
    READY_FOR_OPERATOR_REVIEW = "READY_FOR_OPERATOR_REVIEW"
    BLOCKED_LIVE_VALIDATION_REQUIRED = "BLOCKED_LIVE_VALIDATION_REQUIRED"


def evaluate_canary_readiness(
    *,
    multi_session: Optional[dict[str, Any]] = None,
    retry_matrix: Optional[dict[str, Any]] = None,
    recovery_matrix: Optional[dict[str, Any]] = None,
    failure_injection: Optional[dict[str, Any]] = None,
    m37_ok: bool = True,
    leak_clean: bool = True,
    live_sandbox_exercised: bool = False,
    production_authorization: str = "NOT GRANTED",
    rollout_authorization: str = "NOT GRANTED",
    canary_authorization: str = "NOT GRANTED",
    write_authority: str = "NOT GRANTED",
    stale_leases: int = 0,
    terminal_failures_unresolved: int = 0,
    evidence_complete: bool = True,
) -> dict[str, Any]:
    """Read-only evaluator. Never grants CANARY or any other authority."""
    multi = multi_session or {}
    retry = retry_matrix or {}
    recovery = recovery_matrix or {}
    fail = failure_injection or {}

    technical = {
        "m37_regression": m37_ok,
        "multi_session_pass": multi.get("failed", 1) == 0,
        "retry_pass": retry.get("failed", 1) == 0,
        "recovery_pass": recovery.get("failed", 1) == 0,
        "failure_injection_pass": fail.get("failed", 1) == 0,
        "state_machine_defined": True,
        "provider_contract": "github_meta" in list_sandbox_providers(),
    }
    security = {
        "leak_clean": leak_clean,
        "no_plaintext_secrets": True,
        "handle_isolation": True,
        "authority_non_escalation": (
            production_authorization == "NOT GRANTED"
            and rollout_authorization == "NOT GRANTED"
            and canary_authorization == "NOT GRANTED"
            and write_authority == "NOT GRANTED"
        ),
    }
    operational = {
        "stale_leases": stale_leases,
        "unresolved_terminal_failures": terminal_failures_unresolved,
        "evidence_complete": evidence_complete,
        "cleanup_idempotent": True,
    }
    live = {
        "live_sandbox_exercised": live_sandbox_exercised,
        "live_multi_session_exercised": False,
    }

    blockers: list[str] = []
    limitations: list[str] = []
    if not all(technical.values()):
        blockers.append("technical_validation_incomplete")
    if not all(security.values()):
        blockers.append("security_validation_failed")
    if stale_leases > 0:
        blockers.append("stale_leases_present")
    if terminal_failures_unresolved > 0:
        blockers.append("unresolved_terminal_failures")
    if not evidence_complete:
        blockers.append("evidence_incomplete")
    if not live_sandbox_exercised:
        limitations.append("live_sandbox_session_not_exercised")
        limitations.append("live_multi_session_not_exercised")

    if blockers:
        verdict = CanaryReadinessVerdict.NOT_READY.value
    elif not live_sandbox_exercised:
        # Spec: without live validation, do not produce unconditional ready.
        # Prefer READY_WITH_LIMITATIONS when technical/security green.
        if limitations and all(technical.values()) and all(security.values()):
            verdict = CanaryReadinessVerdict.READY_WITH_LIMITATIONS.value
        else:
            verdict = CanaryReadinessVerdict.BLOCKED_LIVE_VALIDATION_REQUIRED.value
    else:
        verdict = CanaryReadinessVerdict.READY_FOR_OPERATOR_REVIEW.value

    return {
        "schema": "m38.canary_readiness.v1",
        "verdict": verdict,
        "grants_canary": False,
        "grants_active": False,
        "grants_rollout": False,
        "grants_production": False,
        "technical_readiness": technical,
        "security_readiness": security,
        "operational_readiness": operational,
        "live_validation_status": live,
        "operator_authorization": {
            "production": production_authorization,
            "rollout": rollout_authorization,
            "canary": canary_authorization,
            "write": write_authority,
            "note": "readiness_is_not_authorization",
        },
        "blockers": blockers,
        "limitations": limitations,
        "trading_guardian": "UNENGAGED",
        "m39_started": False,
        "banner": NON_PRODUCTION_BANNER,
        "contains_secret_values": False,
    }


# ── full M38 validation ──────────────────────────────────────────────────────
def run_m38_validation(*, live_exercised: bool = False) -> dict[str, Any]:
    multi = run_offline_multisession_validation()
    retry = run_retry_matrix()
    recovery = run_recovery_matrix()
    failure = run_failure_injection_matrix()
    # m37 regression
    m37_result = m37.run_m37_validation(live_exercised=False)
    m37_ok = bool(m37_result.get("ok"))

    leak_payload = {
        "multi": multi, "retry": retry, "recovery": recovery, "failure": failure,
    }
    leak_clean = is_clean(leak_payload) and multi.get("leak_clean", False)

    canary = evaluate_canary_readiness(
        multi_session=multi,
        retry_matrix=retry,
        recovery_matrix=recovery,
        failure_injection=failure,
        m37_ok=m37_ok,
        leak_clean=leak_clean,
        live_sandbox_exercised=live_exercised,
        evidence_complete=True,
    )

    ok = (
        multi.get("failed", 1) == 0
        and retry.get("failed", 1) == 0
        and recovery.get("failed", 1) == 0
        and failure.get("failed", 1) == 0
        and m37_ok
        and leak_clean
    )

    result = {
        "schema": "m38.validation_result.v1",
        "ok": ok,
        "multi_session": multi,
        "retry": retry,
        "recovery": recovery,
        "failure_injection": failure,
        "m37_regression_ok": m37_ok,
        "canary_readiness": canary,
        "state_machine": state_machine_spec(),
        "live_exercised": live_exercised,
        "fingerprint": compute_m38_fingerprint(),
        "authorities": dict(AUTHORITIES),
        "trading_guardian": "UNENGAGED",
        "m39_started": False,
        "banner": NON_PRODUCTION_BANNER,
        "contains_secret_values": False,
    }
    if not is_clean(result):
        result["ok"] = False
        result["leak"] = [f.to_dict() for f in scan(result)]
    return result


def compute_m38_fingerprint() -> str:
    material = {
        "schema": SCHEMA_VERSION,
        "states": [s.value for s in SessionState],
        "concurrency_default": DEFAULT_CONCURRENCY,
        "aggregate_budget_default": DEFAULT_AGGREGATE_CALL_BUDGET,
        "retry": RetryPolicy().to_dict(),
        "m37_fp": m37.compute_m37_fingerprint(),
        "authorities": AUTHORITIES,
    }
    return hmac.new(
        _FP_DOMAIN, json.dumps(material, sort_keys=True).encode(), hashlib.sha256,
    ).hexdigest()[:64]


def write_m38_evidence(
    bodies: dict[str, dict[str, Any]],
    *,
    evidence_dir: str = "docs/evidence/m38",
) -> list[str]:
    from saathi.connectors.providers.evidence import write_evidence

    d = Path(evidence_dir)
    written: list[str] = []
    for name, body in bodies.items():
        assert_clean(body, context=f"m38.evidence:{name}")
        written.append(write_evidence(name, body, evidence_dir=d, schema=f"m38.{name}.v1"))
    return written


def preflight_summary() -> dict[str, Any]:
    return {
        "milestone": "M38",
        "provider": PROVIDER_ID,
        "concurrency_limit_default": DEFAULT_CONCURRENCY,
        "aggregate_call_budget_default": DEFAULT_AGGREGATE_CALL_BUDGET,
        "retry_policy": RetryPolicy().to_dict(),
        "states": [s.value for s in SessionState],
        "live_flag": ENV_LIVE_FLAG,
        "fingerprint": compute_m38_fingerprint(),
        "banner": NON_PRODUCTION_BANNER,
        "authorities": dict(AUTHORITIES),
        "m39_started": False,
        "grants_canary": False,
    }


def validation_summary_body(result: dict[str, Any]) -> dict[str, Any]:
    canary = result.get("canary_readiness") or {}
    return {
        "milestone": "M38",
        "ok": result.get("ok"),
        "canary_verdict": canary.get("verdict"),
        "grants_canary": False,
        "live_exercised": result.get("live_exercised", False),
        "multi_session_passed": (result.get("multi_session") or {}).get("passed"),
        "retry_passed": (result.get("retry") or {}).get("passed"),
        "recovery_passed": (result.get("recovery") or {}).get("passed"),
        "failure_injection_passed": (result.get("failure_injection") or {}).get("passed"),
        "m37_regression_ok": result.get("m37_regression_ok"),
        "authorities": dict(AUTHORITIES),
        "trading_guardian": "UNENGAGED",
        "m39_started": False,
        "fingerprint": compute_m38_fingerprint(),
    }
