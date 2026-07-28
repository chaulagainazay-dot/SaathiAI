"""Central ConversationService — sole model path for Live Voice and text surfaces."""
from __future__ import annotations

import threading
import time
from typing import Any, Iterator

from saathi.platform.context import PlatformContextError
from saathi.platform.models import PlatformPermission, new_id

from .context import ConversationContextBuilder, SessionMemory
from .intent import ToolIntentRouter
from .models import (
    GENERATION_TIMEOUT_SEC,
    MAX_CONCURRENT_GENERATIONS,
    MAX_RESPONSE_CHARS,
    MAX_TOKENS_DEFAULT,
    ActionKind,
    ConversationMessage,
    ConversationRequest,
    ConversationResult,
    ConversationStreamEvent,
    ConversationValidationError,
    StreamEventType,
    bounded_text,
    is_safe_speech_segment,
    sanitize_for_speech,
)
from .providers import (
    ConversationProvider,
    InjectedConversationProvider,
    default_providers,
    select_provider,
)


class ConversationService:
    """Provider-neutral conversational intelligence with streaming + cancel.

    Does not execute tools. Does not call SpeechService. Frontend never calls
    providers directly.
    """

    def __init__(
        self,
        platform_store=None,
        *,
        providers: list[ConversationProvider] | None = None,
        context_builder: ConversationContextBuilder | None = None,
        intent_router: ToolIntentRouter | None = None,
    ):
        self.store = platform_store
        self.providers = providers or default_providers()
        self.context_builder = context_builder or ConversationContextBuilder()
        self.intent_router = intent_router or ToolIntentRouter()
        self._memories: dict[str, SessionMemory] = {}
        self._active: dict[str, str] = {}  # request_id -> session_key
        self._cancel: set[str] = set()
        self._lock = threading.RLock()
        self._sem = threading.BoundedSemaphore(MAX_CONCURRENT_GENERATIONS)
        self._provider_by_id = {p.provider_id: p for p in self.providers}

    def _audit(self, ctx, event: str, **detail) -> None:
        if self.store is None:
            return
        safe = {
            k: v
            for k, v in detail.items()
            if k not in {"prompt", "text", "messages", "password", "token", "authorization"}
        }
        self.store.append_audit(
            event,
            user_id=getattr(ctx, "user_id", "") or "",
            role=getattr(ctx, "role", "") or "",
            org_id=getattr(ctx, "org_id", "") or "",
            workspace_id=getattr(ctx, "workspace_id", "") or "",
            project_id=getattr(ctx, "project_id", "") or "",
            outcome=str(detail.get("outcome") or "success"),
            evidence=str(detail.get("evidence") or ""),
            detail=safe,
        )

    def _session_key(self, ctx, session_id: str = "", conversation_id: str = "") -> str:
        sid = session_id or conversation_id or "default"
        return f"{ctx.org_id}:{ctx.workspace_id}:{ctx.user_id}:{sid}"

    def memory_for(self, ctx, session_id: str = "", conversation_id: str = "") -> SessionMemory:
        key = self._session_key(ctx, session_id, conversation_id)
        with self._lock:
            mem = self._memories.get(key)
            if mem is None:
                mem = SessionMemory()
                self._memories[key] = mem
            return mem

    def clear_session(self, ctx, session_id: str = "", conversation_id: str = "") -> None:
        key = self._session_key(ctx, session_id, conversation_id)
        with self._lock:
            mem = self._memories.pop(key, None)
            if mem:
                mem.clear()
            # cancel any active gens for this session
            for rid, sk in list(self._active.items()):
                if sk == key:
                    self.cancel(rid)

    def clear_user(self, ctx) -> int:
        prefix = f"{ctx.org_id}:{ctx.workspace_id}:{ctx.user_id}:"
        cleared = 0
        with self._lock:
            for key in list(self._memories.keys()):
                if key.startswith(prefix):
                    self._memories.pop(key, None)
                    cleared += 1
            for rid, sk in list(self._active.items()):
                if sk.startswith(prefix):
                    self.cancel(rid)
        self._audit(ctx, "conversation.memory.cleared", cleared=cleared)
        return cleared

    def provider_health(self, ctx) -> list[dict[str, Any]]:
        ctx.require_permission(PlatformPermission.VOICE_SESSION_READ)
        return [p.health().to_public() for p in self.providers]

    def health(self, ctx) -> dict[str, Any]:
        ctx.require_permission(PlatformPermission.VOICE_SESSION_READ)
        providers = self.provider_health(ctx)
        ready = [p for p in providers if p.get("generation_healthy")]
        return {
            "service": "conversation",
            "ready": bool(ready),
            "providers": providers,
            "default_provider": ready[0]["provider_id"] if ready else "unavailable",
            "default_model": ready[0].get("model") if ready else "",
            "max_concurrent_generations": MAX_CONCURRENT_GENERATIONS,
            "auto_model_download": False,
            "tools_executable_by_model": False,
            "intelligence_templates_disabled": True,
        }

    def cancel(self, request_id: str) -> None:
        rid = (request_id or "").strip()
        if not rid:
            return
        with self._lock:
            self._cancel.add(rid)
        for provider in self.providers:
            try:
                provider.cancel(rid)
            except Exception:
                pass

    def is_cancelled(self, request_id: str) -> bool:
        with self._lock:
            return request_id in self._cancel

    def _build_request(self, ctx, payload: dict[str, Any]) -> ConversationRequest:
        try:
            message = bounded_text(
                payload.get("message") or payload.get("text"),
                "message",
                maximum=4000,
                required=True,
            )
        except ConversationValidationError as exc:
            raise PlatformContextError("VALIDATION_FAILED", str(exc)) from exc
        max_tokens = int(payload.get("max_tokens") or MAX_TOKENS_DEFAULT)
        max_tokens = max(16, min(max_tokens, 1024))
        timeout = float(payload.get("timeout_seconds") or GENERATION_TIMEOUT_SEC)
        timeout = max(5.0, min(timeout, 120.0))
        return ConversationRequest(
            request_id=new_id("creq_"),
            organization_id=ctx.org_id,
            workspace_id=ctx.workspace_id,
            user_id=ctx.user_id,
            message=message,
            session_id=str(payload.get("session_id") or ""),
            conversation_id=str(payload.get("conversation_id") or ""),
            yeti_mode=str(payload.get("yeti_mode") or "general"),
            locale=str(payload.get("locale") or "en-US"),
            project_id=str(payload.get("project_id") or getattr(ctx, "project_id", "") or ""),
            mission_id=str(payload.get("mission_id") or ""),
            module_context=str(payload.get("module_context") or "")[:400],
            max_tokens=max_tokens,
            timeout_seconds=timeout,
            stream=bool(payload.get("stream", True)),
            provider=str(payload.get("provider") or "auto"),
            correlation_id=str(payload.get("correlation_id") or ""),
        )

    def stream(
        self, ctx, payload: dict[str, Any]
    ) -> Iterator[ConversationStreamEvent]:
        ctx.require_permission(PlatformPermission.VOICE_TRANSCRIBE)
        # Speak/listen users can converse; generation is part of the turn.
        req = self._build_request(ctx, payload)
        if not self._sem.acquire(blocking=False):
            yield ConversationStreamEvent(
                event=StreamEventType.FAILED.value,
                request_id=req.request_id,
                error_code="RESOURCE_BUDGET_EXHAUSTED",
                error_message="Too many concurrent generations.",
            )
            return

        key = self._session_key(ctx, req.session_id, req.conversation_id)
        with self._lock:
            self._active[req.request_id] = key
            self._cancel.discard(req.request_id)

        memory = self.memory_for(ctx, req.session_id, req.conversation_id)
        history = memory.history_messages()
        ctx_build = self.context_builder.build(
            user_message=req.message,
            yeti_mode=req.yeti_mode,
            history=history,
            summary=memory.summary,
            module_context=req.module_context,
            project_id=req.project_id,
            mission_id=req.mission_id,
        )
        provider = select_provider(req.provider, self.providers)
        t0 = time.time()
        assembled = ""
        speech_buf = ""
        provider_name = provider.provider_id
        model_name = ""
        streamed = False
        cancelled = False
        failed = False
        error_code = ""
        error_message = ""
        intelligence = (
            "test_injected"
            if provider.provider_id == "test_injected"
            else ("model" if provider.provider_id != "unavailable" else "unavailable")
        )

        audit_start = {
            **req.to_safe_audit(),
            **ctx_build.safe_telemetry(),
            "selected_provider": provider.provider_id,
        }
        self._audit(ctx, "conversation.generation.started", **audit_start)

        try:
            for event in provider.stream(
                ctx_build.messages,
                request_id=req.request_id,
                max_tokens=req.max_tokens,
                timeout_seconds=req.timeout_seconds,
            ):
                if self.is_cancelled(req.request_id) and event.event == StreamEventType.TEXT_DELTA.value:
                    yield ConversationStreamEvent(
                        event=StreamEventType.LATE_CHUNK_REJECTED.value,
                        request_id=req.request_id,
                        provider=provider_name,
                        model=model_name,
                        cancelled=True,
                        sequence=event.sequence,
                    )
                    cancelled = True
                    break
                provider_name = event.provider or provider_name
                model_name = event.model or model_name
                if event.event == StreamEventType.TEXT_DELTA.value:
                    streamed = True
                    piece = event.text or ""
                    assembled = (assembled + piece)[:MAX_RESPONSE_CHARS]
                    speech_buf = (speech_buf + piece)
                    # Emit segment when safe for TTS
                    if is_safe_speech_segment(sanitize_for_speech(speech_buf)):
                        seg = sanitize_for_speech(speech_buf)
                        yield ConversationStreamEvent(
                            event=StreamEventType.SEGMENT_READY.value,
                            request_id=req.request_id,
                            text=seg,
                            partial=True,
                            provider=provider_name,
                            model=model_name,
                            sequence=event.sequence,
                        )
                        speech_buf = ""
                    yield ConversationStreamEvent(
                        event=event.event,
                        request_id=req.request_id,
                        text=piece,
                        partial=True,
                        provider=provider_name,
                        model=model_name,
                        sequence=event.sequence,
                    )
                elif event.event == StreamEventType.COMPLETED.value:
                    assembled = (event.text or assembled)[:MAX_RESPONSE_CHARS]
                    streamed = streamed or bool(event.text)
                    yield event
                elif event.event == StreamEventType.CANCELLED.value:
                    cancelled = True
                    assembled = (event.text or assembled)[:MAX_RESPONSE_CHARS]
                    yield event
                elif event.event == StreamEventType.FAILED.value:
                    failed = True
                    error_code = event.error_code
                    error_message = event.error_message
                    yield event
                else:
                    yield event

                if self.is_cancelled(req.request_id):
                    cancelled = True
                    try:
                        provider.cancel(req.request_id)
                    except Exception:
                        pass

            intent = self.intent_router.analyze(req.message, assembled)
            if not failed and not cancelled:
                # Final intent event
                yield ConversationStreamEvent(
                    event=StreamEventType.INTENT_PROPOSED.value,
                    request_id=req.request_id,
                    provider=provider_name,
                    model=model_name,
                    action_kind=intent.get("action_kind", ActionKind.INFORMATIONAL.value),
                    intent=intent,
                    text="",
                )
                if assembled and intelligence != "unavailable":
                    memory.append("user", req.message)
                    memory.append(
                        "assistant",
                        assembled,
                        provider=provider_name,
                        model=model_name,
                    )
            elif cancelled and assembled:
                memory.append("user", req.message)
                memory.append(
                    "assistant",
                    assembled,
                    provider=provider_name,
                    model=model_name,
                    interrupted=True,
                )

            self._audit(
                ctx,
                "conversation.generation.finished",
                **{
                    "request_id": req.request_id,
                    "selected_provider": provider_name,
                    "model": model_name,
                    "cancelled": cancelled,
                    "failed": failed,
                    "streamed": streamed,
                    "text_chars": len(assembled),
                    "latency_ms": round((time.time() - t0) * 1000, 2),
                    "intelligence_kind": intelligence,
                    "action_kind": intent.get("action_kind") if not failed else "",
                },
            )
        finally:
            with self._lock:
                self._active.pop(req.request_id, None)
            self._sem.release()

    def complete(self, ctx, payload: dict[str, Any]) -> ConversationResult:
        assembled = ""
        request_id = ""
        provider = ""
        model = ""
        streamed = False
        cancelled = False
        error_code = ""
        error_message = ""
        action_kind = ActionKind.INFORMATIONAL.value
        intent: dict[str, Any] = {}
        t0 = time.time()
        intelligence = "unavailable"
        ok = False
        for event in self.stream(ctx, payload):
            request_id = event.request_id or request_id
            provider = event.provider or provider
            model = event.model or model
            if event.event == StreamEventType.TEXT_DELTA.value:
                assembled += event.text or ""
                streamed = True
            elif event.event == StreamEventType.COMPLETED.value:
                assembled = event.text or assembled
                streamed = streamed or True
                ok = True
                intelligence = (
                    "test_injected"
                    if provider == "test_injected"
                    else "model"
                )
            elif event.event == StreamEventType.CANCELLED.value:
                cancelled = True
                assembled = event.text or assembled
                ok = bool(assembled)
                intelligence = "model" if provider == "ollama_local" else intelligence
            elif event.event == StreamEventType.FAILED.value:
                error_code = event.error_code
                error_message = event.error_message
                ok = False
                if error_code == "MODEL_NOT_AVAILABLE":
                    intelligence = "unavailable"
            elif event.event == StreamEventType.INTENT_PROPOSED.value:
                intent = event.intent or {}
                action_kind = event.action_kind or action_kind
        return ConversationResult(
            ok=ok and not (error_code and not assembled),
            request_id=request_id,
            text=assembled[:MAX_RESPONSE_CHARS],
            provider=provider,
            model=model,
            streamed=streamed,
            cancelled=cancelled,
            partial=cancelled and bool(assembled),
            error_code=error_code,
            error_message=error_message,
            action_kind=action_kind,
            intent=intent,
            latency_ms=round((time.time() - t0) * 1000, 2),
            intelligence_kind=intelligence,
        )

    # ── Voice Runtime bridge helpers ─────────────────────────────────────
    def stream_for_voice(
        self, ctx, session, user_text: str
    ) -> Iterator[str]:
        """Yield growing assembled text chunks for Voice Runtime speech path."""
        payload = {
            "message": user_text,
            "session_id": session.session_id,
            "conversation_id": session.conversation_id,
            "yeti_mode": session.yeti_mode,
            "locale": session.locale,
            "project_id": session.project_id,
            "provider": "auto",
            "stream": True,
        }
        assembled = ""
        for event in self.stream(ctx, payload):
            if event.event == StreamEventType.TEXT_DELTA.value:
                assembled = (assembled + (event.text or ""))[:MAX_RESPONSE_CHARS]
                yield assembled
            elif event.event == StreamEventType.COMPLETED.value:
                assembled = (event.text or assembled)[:MAX_RESPONSE_CHARS]
                yield assembled
            elif event.event == StreamEventType.FAILED.value:
                if event.error_code == "MODEL_NOT_AVAILABLE":
                    # Truthful — do not emit deterministic templates as intelligence
                    yield ""
                    return
                yield assembled
            elif event.event == StreamEventType.CANCELLED.value:
                yield (event.text or assembled)
                return


_DEFAULT: ConversationService | None = None
_DEFAULT_LOCK = threading.Lock()


def default_conversation_service(platform_service=None) -> ConversationService:
    global _DEFAULT
    with _DEFAULT_LOCK:
        if platform_service is not None:
            existing = getattr(platform_service, "_conversation_service", None)
            if existing is not None:
                return existing
            svc = ConversationService(platform_store=getattr(platform_service, "store", None))
            setattr(platform_service, "_conversation_service", svc)
            return svc
        if _DEFAULT is None:
            _DEFAULT = ConversationService()
        return _DEFAULT


def reset_conversation_service_for_tests(platform_service=None) -> None:
    global _DEFAULT
    with _DEFAULT_LOCK:
        _DEFAULT = None
        if platform_service is not None and hasattr(platform_service, "_conversation_service"):
            delattr(platform_service, "_conversation_service")


def make_test_conversation_service(
    platform_store=None,
    *,
    reply_fn=None,
) -> ConversationService:
    inject = InjectedConversationProvider(reply_fn=reply_fn)
    return ConversationService(
        platform_store=platform_store,
        providers=[inject, *default_providers()],
    )
