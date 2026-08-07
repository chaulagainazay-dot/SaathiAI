"""FM-I6 LocalModelHarness — untrusted AgentHarness driver for loopback Ollama.

Never executes tools, never calls ExecutionGateway, never starts/stops Ollama,
never pulls models, never owns credentials/approvals/RBAC/trading.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Callable, Dict, Iterator, List, Mapping, Optional, Tuple
import platform
import re
import subprocess
import threading
import time
import uuid

from saathi.agent_runtime.harness.errors import HarnessError, HarnessErrorCode
from saathi.agent_runtime.harness.local_model_context import ContextAssembler
from saathi.agent_runtime.harness.local_model_normalize import normalize_model_text
from saathi.agent_runtime.harness.local_model_transport import (
    LocalModelTransport,
    LoopbackOllamaTransport,
    MockOllamaTransport,
    TransportError,
    check_os_bindings_loopback_only,
)
from saathi.agent_runtime.harness.local_model_types import (
    ALLOWED_ENDPOINT,
    HARNESS_ID,
    HARNESS_VERSION,
    LocalFailureKind,
    LocalMetrics,
    LocalModelConfig,
    LocalReadinessState,
    MAX_ACTIVE_LOCAL_SESSIONS,
    MAX_OUTPUT_TOKENS,
    MemorySnapshot,
    MIN_AVAILABLE_MEMORY_MIB,
    MIN_FREE_MEMORY_PERCENT,
    PINNED_MODEL,
    PINNED_MODEL_DIGEST,
    PRODUCTION_CERTIFIED,
    PROTOCOL_VERSION,
    RuntimeInventory,
    estimate_tokens,
    validate_loopback_endpoint,
    version_compatible,
)
from saathi.agent_runtime.harness.types import (
    CancelAck,
    CancelAckStatus,
    EventClassification,
    EventRedactionState,
    HarnessBudget,
    HarnessCapability,
    HarnessCapabilityId,
    HarnessCapabilityProfile,
    HarnessEvent,
    HarnessEventType,
    HarnessHealth,
    HarnessHealthStatus,
    HarnessResourceUsage,
    HarnessSessionHandle,
    HarnessSessionStartRequest,
    HarnessSessionState,
    HarnessTurnHandle,
    HarnessTurnSubmitRequest,
    SessionCloseResult,
    ToolProposal,
    can_transition_harness,
    is_terminal_harness_state,
)


def _default_memory_probe() -> MemorySnapshot:
    """Best-effort Darwin/Linux memory snapshot; fail closed if unreadable."""
    total = 0
    try:
        if platform.system() == "Darwin":
            out = subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True, timeout=2)
            total = int(out.strip())
            vm = subprocess.check_output(["vm_stat"], text=True, timeout=2)
            page_size = 16384
            m = re.search(r"page size of (\d+)", vm)
            if m:
                page_size = int(m.group(1))
            def _pages(label: str) -> int:
                mm = re.search(rf"{label}:\s+(\d+)", vm)
                return int(mm.group(1)) if mm else 0

            free = _pages("Pages free")
            inactive = _pages("Pages inactive")
            speculative = _pages("Pages speculative")
            available = (free + inactive + speculative) * page_size
            free_pct = (available / total * 100.0) if total else 0.0
            avail_mib = available / (1024 * 1024)
            ok = free_pct >= MIN_FREE_MEMORY_PERCENT and avail_mib >= MIN_AVAILABLE_MEMORY_MIB
            return MemorySnapshot(
                total_bytes=total,
                free_percent=free_pct,
                available_mib=avail_mib,
                ok=ok,
                detail="darwin_vm_stat",
            )
    except Exception as e:
        return MemorySnapshot(0, 0.0, 0.0, False, detail=f"probe_failed:{e}")
    return MemorySnapshot(0, 0.0, 0.0, False, detail="unsupported_platform")


def _default_binding_probe() -> Tuple[bool, str]:
    """Read-only lsof check; does not reconfigure Ollama."""
    try:
        out = subprocess.check_output(
            ["lsof", "-nP", "-iTCP:11434", "-sTCP:LISTEN"],
            text=True,
            timeout=3,
            stderr=subprocess.DEVNULL,
        )
        lines = out.splitlines()
        return check_os_bindings_loopback_only(lines)
    except Exception as e:
        return False, f"LIVE_OLLAMA_BINDING_UNSAFE: probe_failed:{e}"


@dataclass
class _LocalSession:
    req: HarnessSessionStartRequest
    state: HarnessSessionState = HarnessSessionState.CREATED
    events: List[HarnessEvent] = field(default_factory=list)
    seq: int = 0
    turns: Dict[str, HarnessSessionState] = field(default_factory=dict)
    usage: HarnessResourceUsage = field(default_factory=HarnessResourceUsage)
    cancel_requested: bool = False
    cancel_event: threading.Event = field(default_factory=threading.Event)
    terminal_reason: str = ""
    closed: bool = False
    history: List[Dict[str, str]] = field(default_factory=list)
    pending_tool_results: List[Mapping[str, Any]] = field(default_factory=list)
    last_correlation_id: str = ""


class LocalModelHarness:
    """Untrusted multi-turn local inference driver (AgentHarness-compatible)."""

    def __init__(
        self,
        transport: Optional[LocalModelTransport] = None,
        *,
        config: Optional[LocalModelConfig] = None,
        clock: Optional[Callable[[], float]] = None,
        id_factory: Optional[Callable[[], str]] = None,
        memory_probe: Optional[Callable[[], MemorySnapshot]] = None,
        binding_probe: Optional[Callable[[], Tuple[bool, str]]] = None,
        live_mode: bool = False,
    ) -> None:
        self._live_mode = live_mode
        cfg = config or LocalModelConfig()
        # Memory/binding gates apply to live runtime by default; mock tests inject probes.
        if not live_mode and config is None:
            cfg = LocalModelConfig(enforce_memory_gate=False, enforce_binding_gate=False)
        self._config = cfg
        # Validate config endpoint once.
        validate_loopback_endpoint(self._config.endpoint)
        if transport is not None:
            self._transport = transport
        elif live_mode:
            self._transport = LoopbackOllamaTransport(self._config.endpoint)
        else:
            self._transport = MockOllamaTransport()
        self._clock = clock or time.time
        self._id_factory = id_factory or (lambda: str(uuid.uuid4()))
        # Default memory probe always-OK for mock; live uses real probe.
        if memory_probe is not None:
            self._memory_probe = memory_probe
        elif live_mode:
            self._memory_probe = _default_memory_probe
        else:
            self._memory_probe = lambda: MemorySnapshot(
                total_bytes=8 * 1024**3,
                free_percent=50.0,
                available_mib=2048.0,
                ok=True,
                detail="mock_default",
            )
        self._binding_probe = binding_probe or _default_binding_probe
        self._sessions: Dict[str, _LocalSession] = {}
        self._lock = threading.RLock()
        self._quarantined = False
        self._readiness = LocalReadinessState.UNCONFIGURED
        self._readiness_detail = ""
        self._metrics = LocalMetrics()
        self._assembler = ContextAssembler(
            max_context_tokens=self._config.max_context_tokens,
            reserved_output_tokens=self._config.reserved_output_tokens,
            system_policy=self._config.system_policy,
            synthetic_only=self._config.synthetic_only,
        )
        self._profile = HarnessCapabilityProfile(
            harness_id=HARNESS_ID,
            harness_version=HARNESS_VERSION,
            protocol_version=PROTOCOL_VERSION,
            capabilities=(
                HarnessCapability(HarnessCapabilityId.SESSION_LIFECYCLE),
                HarnessCapability(HarnessCapabilityId.SUBMIT_TURN),
                HarnessCapability(HarnessCapabilityId.EVENT_STREAM),
                HarnessCapability(HarnessCapabilityId.COOPERATIVE_CANCEL),
                HarnessCapability(HarnessCapabilityId.TOOL_PROPOSALS),
                HarnessCapability(HarnessCapabilityId.HEALTH),
                HarnessCapability(HarnessCapabilityId.RESOURCE_USAGE_REPORT),
                HarnessCapability(HarnessCapabilityId.MULTI_TURN),
                HarnessCapability(HarnessCapabilityId.HEALTH_REPORTING),
                HarnessCapability(HarnessCapabilityId.RESOURCE_REPORTING),
            ),
        )
        # Note: LOCAL_RUNTIME / STREAMING_TEXT are descriptive notes in capability notes
        # via harness_id; we do not invent new enum values here.

    # ── Protocol surface ────────────────────────────────────────────────────

    def describe_capabilities(self) -> HarnessCapabilityProfile:
        return self._profile

    def health(self) -> HarnessHealth:
        with self._lock:
            active = sum(1 for s in self._sessions.values() if not s.closed)
            if self._quarantined:
                return HarnessHealth(
                    status=HarnessHealthStatus.UNHEALTHY,
                    harness_id=HARNESS_ID,
                    detail=f"{LocalReadinessState.QUARANTINED.value}:{self._readiness_detail}",
                    active_sessions=active,
                )
            # Refresh lightweight readiness for mock always; live inventory on demand.
            try:
                self._refresh_readiness_unlocked(probe_memory=False, probe_binding=False)
            except Exception:
                pass
            status = HarnessHealthStatus.HEALTHY
            if self._readiness in (
                LocalReadinessState.RUNTIME_UNAVAILABLE,
                LocalReadinessState.MODEL_NOT_INSTALLED,
                LocalReadinessState.MODEL_MISMATCH,
                LocalReadinessState.UNCONFIGURED,
            ):
                status = HarnessHealthStatus.UNHEALTHY
            elif self._readiness in (
                LocalReadinessState.RESOURCE_PRESSURE,
                LocalReadinessState.DEGRADED,
                LocalReadinessState.BINDING_UNSAFE,
            ):
                status = HarnessHealthStatus.DEGRADED
            return HarnessHealth(
                status=status,
                harness_id=HARNESS_ID,
                detail=f"{self._readiness.value}:{self._readiness_detail}",
                active_sessions=active,
            )

    def readiness(self) -> LocalReadinessState:
        with self._lock:
            return self._readiness

    def metrics(self) -> LocalMetrics:
        with self._lock:
            return LocalMetrics(**self._metrics.__dict__)

    def start_session(self, req: HarnessSessionStartRequest) -> HarnessSessionHandle:
        with self._lock:
            if self._quarantined:
                raise HarnessError(
                    HarnessErrorCode.QUARANTINED,
                    "local model harness quarantined",
                    session_id=req.session_id,
                )
            if not req.session_id or not req.actor_id or not req.correlation_id:
                raise HarnessError(
                    HarnessErrorCode.INVALID_REQUEST,
                    "session_id, actor_id, and correlation_id are required",
                )
            existing = self._sessions.get(req.session_id)
            if existing is not None:
                if (
                    existing.req.organization_id != req.organization_id
                    or existing.req.workspace_id != req.workspace_id
                    or existing.req.actor_id != req.actor_id
                ):
                    raise HarnessError(
                        HarnessErrorCode.IDEMPOTENCY_CONFLICT,
                        "session_id already exists with different scope",
                        session_id=req.session_id,
                    )
                return self._handle(existing)

            active = sum(1 for s in self._sessions.values() if not s.closed)
            if active >= self._config.max_active_sessions:
                raise HarnessError(
                    HarnessErrorCode.RESOURCE_EXHAUSTED,
                    "max active local sessions exceeded",
                    session_id=req.session_id,
                    details={"limit": "max_active_sessions", "max": MAX_ACTIVE_LOCAL_SESSIONS},
                )

            self._refresh_readiness_unlocked(probe_memory=True, probe_binding=self._live_mode)
            if self._readiness is LocalReadinessState.RESOURCE_PRESSURE:
                self._metrics.resource_pressure_count += 1
                raise HarnessError(
                    HarnessErrorCode.RESOURCE_EXHAUSTED,
                    "RESOURCE_PRESSURE: memory gate failed",
                    session_id=req.session_id,
                    details={"kind": LocalFailureKind.MEMORY_PRESSURE.value},
                )
            if self._readiness in (
                LocalReadinessState.RUNTIME_UNAVAILABLE,
                LocalReadinessState.MODEL_NOT_INSTALLED,
                LocalReadinessState.MODEL_MISMATCH,
                LocalReadinessState.QUARANTINED,
            ):
                raise HarnessError(
                    HarnessErrorCode.INTERNAL,
                    f"local runtime not ready: {self._readiness.value}",
                    session_id=req.session_id,
                    details={"readiness": self._readiness.value, "detail": self._readiness_detail},
                )
            # Binding unsafe: allow session start for mock; live turns blocked later.
            sess = _LocalSession(req=req, state=HarnessSessionState.CREATED)
            self._sessions[req.session_id] = sess
            self._transition(sess, HarnessSessionState.INITIALIZING)
            self._emit(
                sess,
                HarnessEventType.SESSION_STARTED,
                {
                    "actor_id": req.actor_id,
                    "harness_id": HARNESS_ID,
                    "model": self._config.model,
                    "production_certified": PRODUCTION_CERTIFIED,
                },
                correlation_id=req.correlation_id,
            )
            self._transition(sess, HarnessSessionState.READY)
            self._emit(
                sess,
                HarnessEventType.SESSION_READY,
                {"readiness": self._readiness.value},
                correlation_id=req.correlation_id,
            )
            return self._handle(sess)

    def submit_turn(self, req: HarnessTurnSubmitRequest) -> HarnessTurnHandle:
        # Preflight under lock; release lock during transport stream so cancel can proceed.
        with self._lock:
            sess = self._require_session(req.session_id)
            if sess.closed or sess.state is HarnessSessionState.CLOSED:
                raise HarnessError(
                    HarnessErrorCode.TERMINAL_SESSION,
                    "session is closed",
                    session_id=req.session_id,
                )
            if sess.cancel_requested or is_terminal_harness_state(sess.state):
                raise HarnessError(
                    HarnessErrorCode.CANCELLED
                    if sess.cancel_requested or sess.state is HarnessSessionState.CANCELLED
                    else HarnessErrorCode.TERMINAL_SESSION,
                    f"cannot accept turns in state {sess.state.value}",
                    session_id=req.session_id,
                )
            if sess.state is not HarnessSessionState.READY:
                raise HarnessError(
                    HarnessErrorCode.INVALID_STATE,
                    f"cannot submit_turn from {sess.state.value}",
                    session_id=req.session_id,
                )
            if not req.turn_id or not req.correlation_id:
                raise HarnessError(
                    HarnessErrorCode.INVALID_REQUEST,
                    "turn_id and correlation_id required",
                    session_id=req.session_id,
                )
            if req.turn_id in sess.turns:
                return HarnessTurnHandle(
                    turn_id=req.turn_id,
                    session_id=req.session_id,
                    state=sess.state,
                    accepted=True,
                )

            budget = sess.req.budget
            next_turns = sess.usage.turns + 1
            if next_turns > budget.max_turns:
                self._fail(sess, "max_turns", req.correlation_id, code=HarnessErrorCode.RESOURCE_EXHAUSTED)
                raise HarnessError(
                    HarnessErrorCode.RESOURCE_EXHAUSTED,
                    "max_turns exceeded",
                    session_id=req.session_id,
                )

            # Live gates before any model call
            self._refresh_readiness_unlocked(
                probe_memory=self._config.enforce_memory_gate,
                probe_binding=self._live_mode and self._config.enforce_binding_gate,
            )
            if self._live_mode and self._readiness is LocalReadinessState.BINDING_UNSAFE:
                self._emit(
                    sess,
                    HarnessEventType.WARNING,
                    {"kind": "LIVE_OLLAMA_BINDING_UNSAFE", "detail": self._readiness_detail},
                    turn_id=req.turn_id,
                    correlation_id=req.correlation_id,
                )
                self._fail(
                    sess,
                    self._readiness_detail,
                    req.correlation_id,
                    turn_id=req.turn_id,
                )
                raise HarnessError(
                    HarnessErrorCode.INTERNAL,
                    self._readiness_detail,
                    session_id=req.session_id,
                    details={"kind": LocalFailureKind.BINDING_UNSAFE.value},
                )
            if self._readiness is LocalReadinessState.RESOURCE_PRESSURE:
                self._metrics.resource_pressure_count += 1
                self._emit(
                    sess,
                    HarnessEventType.WARNING,
                    {"kind": "RESOURCE_PRESSURE", "detail": self._readiness_detail},
                    turn_id=req.turn_id,
                    correlation_id=req.correlation_id,
                )
                self._fail(
                    sess,
                    "RESOURCE_PRESSURE",
                    req.correlation_id,
                    turn_id=req.turn_id,
                )
                raise HarnessError(
                    HarnessErrorCode.RESOURCE_EXHAUSTED,
                    "RESOURCE_PRESSURE",
                    session_id=req.session_id,
                )
            if self._readiness in (
                LocalReadinessState.MODEL_NOT_INSTALLED,
                LocalReadinessState.MODEL_MISMATCH,
                LocalReadinessState.RUNTIME_UNAVAILABLE,
            ):
                self._fail(
                    sess,
                    self._readiness.value,
                    req.correlation_id,
                    turn_id=req.turn_id,
                )
                raise HarnessError(
                    HarnessErrorCode.INTERNAL,
                    f"pin verification failed: {self._readiness.value}",
                    session_id=req.session_id,
                    details={"readiness": self._readiness.value},
                )

            self._transition(sess, HarnessSessionState.RUNNING)
            sess.turns[req.turn_id] = HarnessSessionState.RUNNING
            sess.last_correlation_id = req.correlation_id
            sess.usage = replace(
                sess.usage,
                turns=next_turns,
                logical_time_ms=sess.usage.logical_time_ms + 10,
            )
            self._emit(
                sess,
                HarnessEventType.TURN_ACCEPTED,
                {"input_chars": len(req.input_text or "")},
                turn_id=req.turn_id,
                correlation_id=req.correlation_id,
                causation_id=req.causation_id,
            )
            self._metrics.request_count += 1

        # Prepare context under lock; stream outside lock for cooperative cancel.
        t0 = time.monotonic()
        try:
            with self._lock:
                sess = self._require_session(req.session_id)
                prepared = self._prepare_turn_locked(sess, req)
            if prepared.get("error"):
                with self._lock:
                    self._metrics.failure_count += 1
                raise prepared["error"]
            self._stream_turn(
                session_id=req.session_id,
                req=req,
                messages=prepared["messages"],
                estimated_input_tokens=prepared["estimated_input_tokens"],
                truncation_notes=prepared["truncation_notes"],
            )
            with self._lock:
                self._metrics.success_count += 1
                self._metrics.total_latency_ms = (time.monotonic() - t0) * 1000
                state = self._require_session(req.session_id).state
        except HarnessError:
            with self._lock:
                self._metrics.failure_count += 1
            raise
        except Exception as e:
            with self._lock:
                self._metrics.failure_count += 1
                sess = self._sessions.get(req.session_id)
                if sess is not None:
                    self._fail(sess, f"internal:{e}", req.correlation_id, turn_id=req.turn_id)
            raise HarnessError(
                HarnessErrorCode.INTERNAL,
                "local model turn failed",
                session_id=req.session_id,
                details={"error": type(e).__name__},
            ) from e
        return HarnessTurnHandle(
            turn_id=req.turn_id,
            session_id=req.session_id,
            state=state,
            accepted=True,
        )

    def stream_events(self, session_id: str, after_seq: int = 0) -> Iterator[HarnessEvent]:
        for ev in self.poll_events(session_id, after_seq=after_seq):
            yield ev

    def poll_events(self, session_id: str, after_seq: int = 0) -> List[HarnessEvent]:
        with self._lock:
            sess = self._require_session(session_id)
            return [e for e in sess.events if e.sequence_number > after_seq]

    def request_cancel(self, session_id: str, reason: str = "") -> CancelAck:
        with self._lock:
            sess = self._require_session(session_id)
            if sess.closed or sess.state is HarnessSessionState.CLOSED:
                return CancelAck(
                    session_id=session_id,
                    status=CancelAckStatus.ALREADY_TERMINAL,
                    reason=reason or "already_closed",
                )
            if is_terminal_harness_state(sess.state) and sess.state is not HarnessSessionState.CANCELLING:
                return CancelAck(
                    session_id=session_id,
                    status=CancelAckStatus.ALREADY_TERMINAL,
                    reason=reason or sess.terminal_reason or sess.state.value,
                )
            sess.cancel_requested = True
            sess.cancel_event.set()
            # Cooperative transport cancel only — never kill OS processes.
            try:
                cancel_active = getattr(self._transport, "cancel_active", None)
                if callable(cancel_active):
                    cancel_active()
            except Exception:
                pass
            if can_transition_harness(sess.state, HarnessSessionState.CANCELLING):
                self._transition(sess, HarnessSessionState.CANCELLING)
            self._emit(
                sess,
                HarnessEventType.CANCELLATION_REQUESTED,
                {"reason": reason},
            )
            if can_transition_harness(sess.state, HarnessSessionState.CANCELLED):
                self._transition(sess, HarnessSessionState.CANCELLED)
            elif sess.state is HarnessSessionState.CANCELLING:
                self._transition(sess, HarnessSessionState.CANCELLED)
            sess.terminal_reason = reason or "cancelled"
            self._emit(
                sess,
                HarnessEventType.CANCELLATION_ACKNOWLEDGED,
                {"reason": sess.terminal_reason},
            )
            self._metrics.cancel_count += 1
            return CancelAck(
                session_id=session_id,
                status=CancelAckStatus.ACKNOWLEDGED,
                reason=sess.terminal_reason,
            )

    def close_session(self, session_id: str, reason: str = "") -> SessionCloseResult:
        with self._lock:
            sess = self._require_session(session_id)
            if sess.closed or sess.state is HarnessSessionState.CLOSED:
                return SessionCloseResult(
                    session_id=session_id,
                    state=HarnessSessionState.CLOSED,
                    already_closed=True,
                    reason=reason or "already_closed",
                )
            sess.cancel_event.set()
            if not is_terminal_harness_state(sess.state):
                if can_transition_harness(sess.state, HarnessSessionState.CANCELLING):
                    self._transition(sess, HarnessSessionState.CANCELLING)
                if can_transition_harness(sess.state, HarnessSessionState.CANCELLED):
                    self._transition(sess, HarnessSessionState.CANCELLED)
                elif can_transition_harness(sess.state, HarnessSessionState.COMPLETED):
                    self._transition(sess, HarnessSessionState.COMPLETED)
                elif can_transition_harness(sess.state, HarnessSessionState.FAILED):
                    self._transition(sess, HarnessSessionState.FAILED)
            if can_transition_harness(sess.state, HarnessSessionState.CLOSED):
                self._transition(sess, HarnessSessionState.CLOSED)
            sess.closed = True
            self._emit(
                sess,
                HarnessEventType.SESSION_CLOSED,
                {"reason": reason or "closed"},
            )
            return SessionCloseResult(
                session_id=session_id,
                state=HarnessSessionState.CLOSED,
                already_closed=False,
                reason=reason or "closed",
            )

    def resource_usage(self, session_id: str) -> HarnessResourceUsage:
        with self._lock:
            sess = self._require_session(session_id)
            active = sum(1 for s in self._sessions.values() if not s.closed)
            return replace(sess.usage, concurrent_sessions=active)

    def deliver_tool_result(
        self,
        session_id: str,
        *,
        turn_id: str,
        correlation_id: str,
        result: Mapping[str, Any],
        denied: bool = False,
    ) -> None:
        """Controller-only: accept redacted tool result summary into history."""
        with self._lock:
            sess = self._require_session(session_id)
            if sess.cancel_requested or is_terminal_harness_state(sess.state):
                raise HarnessError(
                    HarnessErrorCode.TERMINAL_SESSION,
                    "cannot deliver tool result to terminal session",
                    session_id=session_id,
                )
            safe = {
                k: v
                for k, v in dict(result).items()
                if k not in ("chain_of_thought", "private_cot", "secret", "password", "token")
            }
            self._emit(
                sess,
                HarnessEventType.TOOL_RESULT_DELIVERED,
                {"denied": denied, "result": safe},
                turn_id=turn_id,
                correlation_id=correlation_id,
            )
            summary = str(safe.get("summary") or ("denied" if denied else "ok"))
            sess.pending_tool_results.append({"summary": summary})
            if sess.state is HarnessSessionState.WAITING_FOR_TOOL:
                self._transition(sess, HarnessSessionState.READY)

    # ── Internals ───────────────────────────────────────────────────────────

    def _prepare_turn_locked(self, sess: _LocalSession, req: HarnessTurnSubmitRequest) -> dict:
        """Assemble context under lock. Returns messages or error."""
        if sess.cancel_requested:
            return {
                "error": HarnessError(
                    HarnessErrorCode.CANCELLED, "cancelled", session_id=req.session_id
                )
            }
        assembled = self._assembler.assemble(
            user_turn=req.input_text or "",
            history=sess.history,
            tool_results=sess.pending_tool_results,
            correlation_id=req.correlation_id,
        )
        sess.pending_tool_results.clear()
        if assembled.rejected_reason:
            kind = "CONTEXT_OVERFLOW" if "OVERFLOW" in assembled.rejected_reason else "CLASSIFICATION"
            self._emit(
                sess,
                HarnessEventType.ERROR,
                {"kind": kind, "detail": assembled.rejected_reason},
                turn_id=req.turn_id,
                correlation_id=req.correlation_id,
                classification=EventClassification.INTERNAL,
            )
            self._fail(sess, assembled.rejected_reason, req.correlation_id, turn_id=req.turn_id)
            return {
                "error": HarnessError(
                    HarnessErrorCode.INVALID_REQUEST
                    if kind == "CLASSIFICATION"
                    else HarnessErrorCode.RESOURCE_EXHAUSTED,
                    assembled.rejected_reason,
                    session_id=req.session_id,
                )
            }
        notes = list(assembled.truncation_notes)
        if assembled.truncated:
            self._emit(
                sess,
                HarnessEventType.WARNING,
                {"kind": "context_truncated", "notes": notes},
                turn_id=req.turn_id,
                correlation_id=req.correlation_id,
            )
        messages = self._assembler.to_ollama_messages(assembled)
        self._metrics.estimated_input_tokens += assembled.estimated_tokens
        return {
            "messages": messages,
            "estimated_input_tokens": assembled.estimated_tokens,
            "truncation_notes": notes,
        }

    def _stream_turn(
        self,
        *,
        session_id: str,
        req: HarnessTurnSubmitRequest,
        messages: List[dict],
        estimated_input_tokens: int,
        truncation_notes: List[str],
    ) -> None:
        options = {
            "temperature": self._config.temperature,
            "top_p": self._config.top_p,
            "num_predict": min(self._config.max_output_tokens, MAX_OUTPUT_TOKENS),
            "num_ctx": self._config.max_context_tokens,
        }
        with self._lock:
            sess = self._require_session(session_id)
            cancel_event = sess.cancel_event
            if sess.cancel_requested:
                raise HarnessError(HarnessErrorCode.CANCELLED, "cancelled", session_id=session_id)

        text_parts: List[str] = []
        first_token_at: Optional[float] = None
        t0 = time.monotonic()
        response_bytes = 0
        thinking_any = False

        try:
            for chunk in self._transport.stream_chat(
                model=self._config.model,
                messages=messages,
                options=options,
                cancel_event=cancel_event,
                correlation_id=req.correlation_id,
            ):
                with self._lock:
                    sess = self._require_session(session_id)
                    if sess.cancel_requested:
                        raise TransportError("CANCELLED", "cancelled")
                    if chunk.thinking_stripped:
                        thinking_any = True
                    if chunk.error:
                        raise TransportError("RUNTIME_ERROR", chunk.error)
                    if chunk.text:
                        if first_token_at is None:
                            first_token_at = time.monotonic()
                            self._metrics.first_token_latency_ms = (first_token_at - t0) * 1000
                        response_bytes += len(chunk.text.encode("utf-8"))
                        text_parts.append(chunk.text)
                        joined_len = sum(len(p) for p in text_parts)
                        if joined_len > self._config.max_output_chars:
                            text_parts = ["".join(text_parts)[: self._config.max_output_chars]]
                            self._emit(
                                sess,
                                HarnessEventType.WARNING,
                                {"kind": "OUTPUT_LIMIT", "detail": "output char ceiling"},
                                turn_id=req.turn_id,
                                correlation_id=req.correlation_id,
                            )
                            break
                        delta = chunk.text[:4096]
                        self._emit(
                            sess,
                            HarnessEventType.TEXT_DELTA,
                            {"text": delta},
                            turn_id=req.turn_id,
                            correlation_id=req.correlation_id,
                        )
                        sess.usage = replace(
                            sess.usage,
                            output_chars=sess.usage.output_chars + len(delta),
                            fake_tokens=sess.usage.fake_tokens + estimate_tokens(delta),
                        )
                        if sess.usage.output_chars > sess.req.budget.max_output_chars:
                            break
                    if chunk.done:
                        break
        except TransportError as e:
            with self._lock:
                sess = self._require_session(session_id)
                if e.kind == "CANCELLED" or sess.cancel_requested:
                    if not is_terminal_harness_state(sess.state):
                        if can_transition_harness(sess.state, HarnessSessionState.CANCELLING):
                            self._transition(sess, HarnessSessionState.CANCELLING)
                        if can_transition_harness(sess.state, HarnessSessionState.CANCELLED):
                            self._transition(sess, HarnessSessionState.CANCELLED)
                    raise HarnessError(
                        HarnessErrorCode.CANCELLED,
                        "cancelled",
                        session_id=session_id,
                    )
                if e.kind == "TIMEOUT":
                    self._metrics.timeout_count += 1
                    self._timeout(sess, e.message, req.correlation_id, turn_id=req.turn_id)
                    raise HarnessError(
                        HarnessErrorCode.TIMED_OUT,
                        e.message,
                        session_id=session_id,
                    )
                if e.kind in ("MALFORMED_STREAM", "MALFORMED_JSON"):
                    self._metrics.malformed_stream_count += 1
                    self._emit(
                        sess,
                        HarnessEventType.PROTOCOL_VIOLATION,
                        {"kind": e.kind, "detail": e.message},
                        turn_id=req.turn_id,
                        correlation_id=req.correlation_id,
                    )
                    self._fail(sess, e.message, req.correlation_id, turn_id=req.turn_id)
                    raise HarnessError(
                        HarnessErrorCode.PROTOCOL_VIOLATION,
                        e.message,
                        session_id=session_id,
                    )
                self._fail(sess, e.message, req.correlation_id, turn_id=req.turn_id)
                raise HarnessError(
                    HarnessErrorCode.INTERNAL,
                    e.message,
                    session_id=session_id,
                    details={"kind": e.kind},
                )

        full_text = "".join(text_parts)
        norm = normalize_model_text(
            full_text,
            correlation_id=req.correlation_id,
            max_chars=self._config.max_output_chars,
        )
        with self._lock:
            sess = self._require_session(session_id)
            self._metrics.response_bytes += response_bytes
            self._metrics.estimated_output_tokens += estimate_tokens(full_text)
            if thinking_any or norm.thinking_stripped:
                self._emit(
                    sess,
                    HarnessEventType.WARNING,
                    {"kind": "private_cot_stripped"},
                    turn_id=req.turn_id,
                    correlation_id=req.correlation_id,
                )
            if norm.secret_shaped:
                self._emit(
                    sess,
                    HarnessEventType.WARNING,
                    {"kind": "SECRET_SHAPED_OUTPUT", "redaction": "applied"},
                    turn_id=req.turn_id,
                    correlation_id=req.correlation_id,
                    redaction_state=EventRedactionState.REDACTED,
                )
            if norm.scope_forgery:
                self._emit(
                    sess,
                    HarnessEventType.PROTOCOL_VIOLATION,
                    {"kind": "SCOPE_FORGERY", "warnings": norm.warnings},
                    turn_id=req.turn_id,
                    correlation_id=req.correlation_id,
                )
            for w in norm.warnings:
                if w not in ("secret_shaped_output", "scope_or_approval_claim_in_text"):
                    self._emit(
                        sess,
                        HarnessEventType.WARNING,
                        {"kind": w},
                        turn_id=req.turn_id,
                        correlation_id=req.correlation_id,
                    )
            for reason in norm.rejected_proposal_reasons:
                self._emit(
                    sess,
                    HarnessEventType.WARNING,
                    {"kind": "tool_proposal_rejected", "reason": reason},
                    turn_id=req.turn_id,
                    correlation_id=req.correlation_id,
                )

            for prop in norm.proposals:
                if sess.usage.tool_proposals >= sess.req.budget.max_tool_proposals:
                    self._emit(
                        sess,
                        HarnessEventType.WARNING,
                        {"kind": "tool_proposal_budget_exceeded"},
                        turn_id=req.turn_id,
                        correlation_id=req.correlation_id,
                    )
                    break
                allowed = sess.req.allowed_tool_names
                if allowed and prop.requested_tool_name not in allowed:
                    self._emit(
                        sess,
                        HarnessEventType.TOOL_REQUEST_DENIED,
                        {
                            "tool_name": prop.requested_tool_name,
                            "reason": "not_in_allowlist",
                        },
                        turn_id=req.turn_id,
                        correlation_id=req.correlation_id,
                    )
                    continue
                self._emit(
                    sess,
                    HarnessEventType.TOOL_PROPOSAL,
                    {
                        "proposal_id": prop.proposal_id,
                        "tool_name": prop.requested_tool_name,
                        "parameters": dict(prop.arguments),
                        "rationale_summary": prop.rationale_summary,
                        "confidence": prop.confidence,
                        "non_authoritative": True,
                    },
                    turn_id=req.turn_id,
                    correlation_id=req.correlation_id,
                )
                sess.usage = replace(sess.usage, tool_proposals=sess.usage.tool_proposals + 1)
                self._metrics.tool_proposal_count += 1
                self._transition(sess, HarnessSessionState.WAITING_FOR_TOOL)
                sess.history.append({"role": "user", "content": req.input_text or ""})
                sess.history.append({"role": "assistant", "content": norm.text})
                return

            sess.history.append({"role": "user", "content": req.input_text or ""})
            sess.history.append({"role": "assistant", "content": norm.text})
            self._complete(sess, req.turn_id, req.correlation_id, text=norm.text)

    def _refresh_readiness_unlocked(
        self,
        *,
        probe_memory: bool,
        probe_binding: bool,
    ) -> None:
        if self._quarantined:
            self._readiness = LocalReadinessState.QUARANTINED
            return
        if probe_binding and self._live_mode and self._config.enforce_binding_gate:
            safe, reason = self._binding_probe()
            if not safe:
                self._readiness = LocalReadinessState.BINDING_UNSAFE
                self._readiness_detail = reason
                # Continue inventory check but live turns will fail.
        if probe_memory and self._config.enforce_memory_gate:
            mem = self._memory_probe()
            if not mem.ok:
                self._readiness = LocalReadinessState.RESOURCE_PRESSURE
                self._readiness_detail = (
                    f"free_pct={mem.free_percent:.1f} avail_mib={mem.available_mib:.1f} ({mem.detail})"
                )
                return
        try:
            inv = self._transport.inventory()
        except TransportError as e:
            self._readiness = LocalReadinessState.RUNTIME_UNAVAILABLE
            self._readiness_detail = e.message
            return
        if not inv.reachable:
            self._readiness = LocalReadinessState.RUNTIME_UNAVAILABLE
            self._readiness_detail = inv.detail or "unreachable"
            return
        if inv.version and not version_compatible(inv.version, self._config.min_runtime_version):
            self._readiness = LocalReadinessState.DEGRADED
            self._readiness_detail = f"runtime_version_unsupported:{inv.version}"
            # Still allow mock with version set; for live, treat as fail later.
            if self._live_mode:
                self._readiness = LocalReadinessState.RUNTIME_UNAVAILABLE
                return
        # Model pin
        match = None
        for m in inv.models:
            if m.name == self._config.model or m.name.startswith(self._config.model + ":"):
                match = m
                break
            # Exact tag match only — also accept name as listed.
            if m.name == PINNED_MODEL:
                match = m
                break
        if match is None:
            # try exact
            for m in inv.models:
                if m.name == self._config.model:
                    match = m
                    break
        if match is None:
            self._readiness = LocalReadinessState.MODEL_NOT_INSTALLED
            self._readiness_detail = f"model {self._config.model} missing"
            return
        # Digest: Ollama digests may be full sha256 or short; compare suffix/prefix flexibly.
        expected = self._config.model_digest.lower()
        actual = (match.digest or "").lower()
        if actual:
            # Strip sha256: prefix if present
            if actual.startswith("sha256:"):
                actual = actual[7:]
            if expected not in actual and actual not in expected and not actual.startswith(expected[:12]):
                # Short id from `ollama list` is first 12 of digest
                if not expected.startswith(actual) and not actual.startswith(expected[: len(actual)]):
                    self._readiness = LocalReadinessState.MODEL_MISMATCH
                    self._readiness_detail = f"digest mismatch for {match.name}"
                    return
        if len(inv.loaded_models) > 1:
            self._readiness = LocalReadinessState.DEGRADED
            self._readiness_detail = "multiple_models_loaded"
            return
        if self._readiness is LocalReadinessState.BINDING_UNSAFE:
            # Keep binding unsafe as readiness for live gate.
            return
        self._readiness = LocalReadinessState.MODEL_READY
        self._readiness_detail = f"model={match.name}"

    def _require_session(self, session_id: str) -> _LocalSession:
        sess = self._sessions.get(session_id)
        if sess is None:
            raise HarnessError(
                HarnessErrorCode.UNKNOWN_SESSION,
                "unknown session",
                session_id=session_id,
            )
        return sess

    def _handle(self, sess: _LocalSession) -> HarnessSessionHandle:
        return HarnessSessionHandle(
            session_id=sess.req.session_id,
            state=sess.state,
            harness_id=HARNESS_ID,
            capabilities=self._profile,
            run_id=sess.req.run_id,
            organization_id=sess.req.organization_id,
            workspace_id=sess.req.workspace_id,
        )

    def _transition(self, sess: _LocalSession, new_state: HarnessSessionState) -> None:
        if sess.state is new_state:
            return
        if not can_transition_harness(sess.state, new_state):
            raise HarnessError(
                HarnessErrorCode.INVALID_STATE,
                f"illegal transition {sess.state.value} -> {new_state.value}",
                session_id=sess.req.session_id,
            )
        sess.state = new_state

    def _emit(
        self,
        sess: _LocalSession,
        event_type: HarnessEventType,
        payload: Mapping[str, Any],
        *,
        turn_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        causation_id: Optional[str] = None,
        classification: EventClassification = EventClassification.INTERNAL,
        redaction_state: EventRedactionState = EventRedactionState.NONE,
    ) -> HarnessEvent:
        sess.seq += 1
        # Harness-local event ids are non-authoritative; controller may renumber.
        ev = HarnessEvent(
            event_id=self._id_factory(),
            session_id=sess.req.session_id,
            sequence_number=sess.seq,
            event_type=event_type,
            harness_id=HARNESS_ID,
            timestamp=self._clock(),
            payload=dict(payload),
            turn_id=turn_id,
            run_id=sess.req.run_id,
            mission_id=sess.req.mission_id,
            organization_id=sess.req.organization_id,
            workspace_id=sess.req.workspace_id,
            correlation_id=correlation_id,
            causation_id=causation_id,
            classification=classification,
            redaction_state=redaction_state,
        )
        # Strip private CoT keys from payload
        safe = ev.safe_payload()
        if safe != dict(ev.payload):
            ev = HarnessEvent(
                event_id=ev.event_id,
                session_id=ev.session_id,
                sequence_number=ev.sequence_number,
                event_type=ev.event_type,
                harness_id=ev.harness_id,
                timestamp=ev.timestamp,
                payload=safe,
                turn_id=ev.turn_id,
                run_id=ev.run_id,
                mission_id=ev.mission_id,
                organization_id=ev.organization_id,
                workspace_id=ev.workspace_id,
                correlation_id=ev.correlation_id,
                causation_id=ev.causation_id,
                classification=ev.classification,
                redaction_state=ev.redaction_state,
            )
        sess.events.append(ev)
        sess.usage = replace(sess.usage, events=sess.usage.events + 1)
        if sess.usage.events > sess.req.budget.max_events:
            # Soft: mark fail on next action; still record this event.
            pass
        return ev

    def _complete(
        self,
        sess: _LocalSession,
        turn_id: str,
        correlation_id: str,
        *,
        text: str,
    ) -> None:
        if is_terminal_harness_state(sess.state) or sess.state is HarnessSessionState.CLOSED:
            return
        if sess.state is HarnessSessionState.RUNNING:
            self._transition(sess, HarnessSessionState.READY)
        # Multi-turn: stay READY, not SESSION_COMPLETED (session may continue).
        self._emit(
            sess,
            HarnessEventType.TEXT_DELTA,
            {"text": "", "final": True, "complete_chars": len(text)},
            turn_id=turn_id,
            correlation_id=correlation_id,
        )

    def _fail(
        self,
        sess: _LocalSession,
        reason: str,
        correlation_id: str,
        *,
        turn_id: Optional[str] = None,
        code: str = HarnessErrorCode.INTERNAL,
    ) -> None:
        sess.terminal_reason = reason
        if can_transition_harness(sess.state, HarnessSessionState.FAILED):
            if sess.state is HarnessSessionState.RUNNING or sess.state is HarnessSessionState.READY:
                pass
            if can_transition_harness(sess.state, HarnessSessionState.FAILED):
                try:
                    self._transition(sess, HarnessSessionState.FAILED)
                except HarnessError:
                    if can_transition_harness(sess.state, HarnessSessionState.CANCELLING):
                        self._transition(sess, HarnessSessionState.CANCELLING)
        self._emit(
            sess,
            HarnessEventType.SESSION_FAILED,
            {"reason": reason, "code": code},
            turn_id=turn_id,
            correlation_id=correlation_id,
        )

    def _timeout(
        self,
        sess: _LocalSession,
        reason: str,
        correlation_id: str,
        *,
        turn_id: Optional[str] = None,
    ) -> None:
        sess.terminal_reason = reason
        if can_transition_harness(sess.state, HarnessSessionState.TIMED_OUT):
            self._transition(sess, HarnessSessionState.TIMED_OUT)
        self._emit(
            sess,
            HarnessEventType.SESSION_TIMED_OUT,
            {"reason": reason},
            turn_id=turn_id,
            correlation_id=correlation_id,
        )


__all__ = [
    "LocalModelHarness",
    "MockOllamaTransport",
    "LoopbackOllamaTransport",
    "LocalModelConfig",
    "LocalReadinessState",
    "PRODUCTION_CERTIFIED",
]
