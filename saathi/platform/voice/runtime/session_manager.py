"""VoiceSessionManager + VoiceRuntime facade.

Central entrypoint for real-time interruptible voice conversations.
Reuses Platform identity/RBAC/audit and SpeechService; does not replace them.
"""
from __future__ import annotations

import audioop
import io
import struct
import threading
import wave
from typing import Any

from saathi.platform.context import PlatformContextError
from saathi.platform.models import PlatformPermission, new_id
from saathi.platform.voice.models import VoiceValidationError

from .conversation import ConversationRuntime
from .input_service import VoiceInputService
from .models import (
    MAX_AUDIO_UPLOAD_BYTES,
    MAX_SESSIONS_PER_USER,
    SESSION_TTL_SECONDS,
    ConversationSession,
    ConversationState,
    InputMode,
    InputState,
    PlaybackState,
    validate_session_create,
    validate_transcript_text,
)
from .playback import AudioPlaybackController
from .repository import VoiceRuntimeRepository
from .speech_runtime import SpeechRuntime
from .stt import (
    BrowserPassthroughSpeechRecognitionProvider,
    discover_stt_providers,
    select_stt_provider,
)


class VoiceSessionManager:
    """Owns per-user session lifecycle, interruption, and module coordination."""

    def __init__(
        self,
        platform_store,
        *,
        speech_service=None,
        conversation: ConversationRuntime | None = None,
        conversation_service=None,
        stt_providers=None,
    ):
        self.store = platform_store
        self.repo = VoiceRuntimeRepository(platform_store)
        self.speech_service = speech_service
        self.conversation_service = conversation_service
        self.conversation = conversation or ConversationRuntime(
            conversation_service=conversation_service
        )
        if conversation_service is not None:
            self.conversation.bind_conversation_service(conversation_service)
        self.stt_providers = stt_providers
        self._lock = threading.RLock()
        self._inputs: dict[str, VoiceInputService] = {}
        self._playback: dict[str, AudioPlaybackController] = {}
        self._speech_runtimes: dict[str, SpeechRuntime] = {}
        self._spoken_partial: dict[str, str] = {}
        self._turn_ctx = None

    # ── RBAC helpers ─────────────────────────────────────────────────────
    def _require(self, ctx, permission: PlatformPermission) -> None:
        ctx.require_permission(permission)

    def _audit(
        self,
        ctx,
        event: str,
        *,
        session: ConversationSession | None = None,
        outcome: str = "success",
        evidence: str = "",
        detail: dict[str, Any] | None = None,
    ) -> None:
        safe = dict(detail or {})
        if session:
            safe.update(
                {
                    "session_id": session.session_id,
                    "state": session.state,
                    "input_state": session.input_state,
                    "playback_state": session.playback_state,
                }
            )
        # Avoid raw audio / secrets
        for banned in ("audio", "pcm", "wav", "password", "token", "authorization"):
            safe.pop(banned, None)
        self.store.append_audit(
            event,
            user_id=ctx.user_id,
            role=ctx.role,
            org_id=ctx.org_id,
            workspace_id=ctx.workspace_id,
            project_id=getattr(ctx, "project_id", "") or "",
            outcome=outcome,
            evidence=evidence,
            detail=safe,
        )

    def _get_owned(self, ctx, session_id: str) -> ConversationSession:
        session = self.repo.get_session(
            session_id, org_id=ctx.org_id, workspace_id=ctx.workspace_id
        )
        if not session or session.user_id != ctx.user_id:
            raise PlatformContextError("NOT_FOUND", "voice session not found")
        if session.expires_at and session.expires_at < self.store._now():
            session.state = ConversationState.FINISHED.value
            self.repo.save_session(session)
            raise PlatformContextError("NOT_FOUND", "voice session expired")
        return session

    def _input_for(self, session: ConversationSession) -> VoiceInputService:
        existing = self._inputs.get(session.session_id)
        if existing:
            return existing
        service = VoiceInputService(
            sample_rate=session.sample_rate,
            max_recording_seconds=session.max_recording_seconds,
            silence_timeout_ms=session.silence_timeout_ms,
            min_speech_ms=session.min_speech_ms,
        )
        self._inputs[session.session_id] = service
        return service

    def _playback_for(self, session: ConversationSession) -> AudioPlaybackController:
        existing = self._playback.get(session.session_id)
        if existing:
            return existing
        controller = AudioPlaybackController()
        self._playback[session.session_id] = controller
        return controller

    def _speech_runtime(self, session: ConversationSession) -> SpeechRuntime:
        existing = self._speech_runtimes.get(session.session_id)
        if existing:
            return existing
        if self.speech_service is None:
            raise PlatformContextError(
                "UNAVAILABLE", "SpeechService is not bound to Voice Runtime"
            )
        runtime = SpeechRuntime(self.speech_service)
        self._speech_runtimes[session.session_id] = runtime
        return runtime

    def _persist(self, session: ConversationSession) -> ConversationSession:
        return self.repo.save_session(session)

    # ── discovery / health ───────────────────────────────────────────────
    def stt_provider_states(self, ctx) -> list[dict[str, Any]]:
        self._require(ctx, PlatformPermission.VOICE_SESSION_READ)
        return discover_stt_providers(self.stt_providers)

    def health(self, ctx) -> dict[str, Any]:
        self._require(ctx, PlatformPermission.VOICE_SESSION_READ)
        return {
            "runtime": "voice_runtime",
            "speech_service_bound": self.speech_service is not None,
            "stt_providers": self.stt_provider_states(ctx),
            "background_recording": False,
            "hidden_activation": False,
            "loopback_only": True,
            "public_listeners": False,
            "cloning": False,
            "auto_model_download": False,
        }

    # ── session CRUD ─────────────────────────────────────────────────────
    def create_session(self, ctx, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        self._require(ctx, PlatformPermission.VOICE_LISTEN)
        try:
            body = validate_session_create(payload or {})
        except VoiceValidationError as exc:
            raise PlatformContextError("VALIDATION_FAILED", str(exc)) from exc
        active = self.repo.count_active_for_user(
            org_id=ctx.org_id, workspace_id=ctx.workspace_id, user_id=ctx.user_id
        )
        if active >= MAX_SESSIONS_PER_USER:
            raise PlatformContextError(
                "RESOURCE_BUDGET_EXHAUSTED", "too many active voice sessions"
            )
        now = self.store._now()
        session = ConversationSession(
            session_id=new_id("vses_"),
            organization_id=ctx.org_id,
            workspace_id=ctx.workspace_id,
            user_id=ctx.user_id,
            conversation_id=body["conversation_id"],
            state=ConversationState.IDLE.value,
            input_mode=body["input_mode"],
            input_state=InputState.IDLE.value,
            playback_state=PlaybackState.IDLE.value,
            stt_provider=body["stt_provider"],
            voice_profile_id=body["voice_profile_id"],
            sample_rate=body["sample_rate"],
            max_recording_seconds=body["max_recording_seconds"],
            silence_timeout_ms=body["silence_timeout_ms"],
            min_speech_ms=body["min_speech_ms"],
            project_id=body["project_id"] or getattr(ctx, "project_id", "") or "",
            locale=body["locale"],
            yeti_mode=body["yeti_mode"],
            created_at=now,
            updated_at=now,
            last_activity_at=now,
            expires_at=now + SESSION_TTL_SECONDS,
        )
        self.repo.create_session(session)
        evidence = self.repo.create_evidence(
            session,
            event_type="voice.session.created",
            summary="Real-time voice session created.",
            metadata={"yeti_mode": session.yeti_mode, "stt": session.stt_provider},
        )
        session.evidence_id = evidence
        self.repo.save_session(session)
        self._audit(ctx, "voice.session.created", session=session, evidence=evidence)
        return session.to_public()

    def get_session(self, ctx, session_id: str) -> dict[str, Any]:
        self._require(ctx, PlatformPermission.VOICE_SESSION_READ)
        session = self._get_owned(ctx, session_id)
        payload = session.to_public()
        payload["input"] = self._input_for(session).snapshot()
        payload["playback"] = self._playback_for(session).to_public()
        return payload

    def list_sessions(self, ctx) -> list[dict[str, Any]]:
        self._require(ctx, PlatformPermission.VOICE_SESSION_READ)
        sessions = self.repo.list_sessions(
            org_id=ctx.org_id, workspace_id=ctx.workspace_id, user_id=ctx.user_id
        )
        return [session.to_public(include_history=False) for session in sessions]

    def finish_session(self, ctx, session_id: str) -> dict[str, Any]:
        self._require(ctx, PlatformPermission.VOICE_LISTEN)
        session = self._get_owned(ctx, session_id)
        self._hard_stop_audio(ctx, session)
        self.conversation.transition(session, ConversationState.FINISHED)
        session.input_state = InputState.IDLE.value
        session.playback_state = PlaybackState.IDLE.value
        self._cleanup_runtime(session.session_id)
        self._persist(session)
        self._audit(ctx, "voice.session.finished", session=session)
        return session.to_public()

    def clear_user_sessions(self, ctx) -> int:
        """Logout / context switch cleanup — finish all owned active sessions."""
        self._require(ctx, PlatformPermission.VOICE_SESSION_READ)
        sessions = self.repo.list_sessions(
            org_id=ctx.org_id, workspace_id=ctx.workspace_id, user_id=ctx.user_id
        )
        cleared = 0
        for session in sessions:
            if session.state in {
                ConversationState.FINISHED.value,
                ConversationState.FAILED.value,
            }:
                continue
            try:
                self._hard_stop_audio(ctx, session)
            except Exception:
                pass
            try:
                self.conversation.cancel_active_generation()
            except Exception:
                pass
            session.state = ConversationState.FINISHED.value
            session.input_state = InputState.IDLE.value
            session.playback_state = PlaybackState.IDLE.value
            session.partial_user_transcript = ""
            session.partial_assistant_response = ""
            self.repo.save_session(session)
            self._cleanup_runtime(session.session_id)
            cleared += 1
        if self.conversation_service is not None:
            try:
                self.conversation_service.clear_user(ctx)
            except Exception:
                pass
        if cleared:
            self._audit(
                ctx,
                "voice.session.logout_cleared",
                detail={"cleared": cleared},
            )
        return cleared

    # ── microphone lifecycle ─────────────────────────────────────────────
    def start_listening(
        self,
        ctx,
        session_id: str,
        *,
        mode: str | None = None,
        permission_granted: bool = True,
    ) -> dict[str, Any]:
        self._require(ctx, PlatformPermission.VOICE_LISTEN)
        session = self._get_owned(ctx, session_id)
        input_service = self._input_for(session)
        chosen_mode = mode or session.input_mode or InputMode.TOGGLE.value
        snap = input_service.start(
            chosen_mode, permission_granted=permission_granted
        )
        if snap.get("state") == InputState.ERROR.value:
            session.input_state = InputState.ERROR.value
            session.error_category = "microphone_permission"
            session.error_message = snap.get("error") or "permission denied"
            self._persist(session)
            raise PlatformContextError(
                "PERMISSION_DENIED", "microphone permission is required"
            )
        # Barge-in path: if responding, interrupt first
        if session.state == ConversationState.RESPONDING.value:
            self.interrupt(ctx, session_id, reason="start_listening")
            session = self._get_owned(ctx, session_id)
        self.conversation.transition(session, ConversationState.LISTENING)
        session.input_mode = chosen_mode
        session.input_state = snap["state"]
        session.error_category = ""
        session.error_message = ""
        self._persist(session)
        self._audit(ctx, "voice.input.listening", session=session)
        return self.get_session(ctx, session_id)

    def stop_listening(self, ctx, session_id: str) -> dict[str, Any]:
        self._require(ctx, PlatformPermission.VOICE_LISTEN)
        session = self._get_owned(ctx, session_id)
        snap = self._input_for(session).stop(process=True)
        session.input_state = snap["state"]
        self._persist(session)
        return self.get_session(ctx, session_id)

    def cancel_input(self, ctx, session_id: str) -> dict[str, Any]:
        self._require(ctx, PlatformPermission.VOICE_LISTEN)
        session = self._get_owned(ctx, session_id)
        snap = self._input_for(session).cancel()
        session.input_state = snap["state"]
        session.partial_user_transcript = ""
        self._persist(session)
        self._audit(ctx, "voice.input.cancelled", session=session)
        return self.get_session(ctx, session_id)

    def set_microphone_permission(
        self, ctx, session_id: str, *, granted: bool
    ) -> dict[str, Any]:
        self._require(ctx, PlatformPermission.VOICE_LISTEN)
        session = self._get_owned(ctx, session_id)
        snap = self._input_for(session).set_permission(granted)
        session.input_state = snap["state"]
        if not granted:
            session.error_category = "microphone_permission"
        self._persist(session)
        return self.get_session(ctx, session_id)

    # ── STT paths ────────────────────────────────────────────────────────
    def submit_transcript(
        self,
        ctx,
        session_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Browser / passthrough STT path with partial + final support."""
        self._require(ctx, PlatformPermission.VOICE_TRANSCRIBE)
        session = self._get_owned(ctx, session_id)
        is_final = bool(payload.get("is_final", True))
        partial = bool(payload.get("partial", not is_final))
        try:
            text = validate_transcript_text(
                payload.get("text"), partial=partial or not is_final
            )
        except VoiceValidationError as exc:
            raise PlatformContextError("VALIDATION_FAILED", str(exc)) from exc
        confidence = float(payload.get("confidence") or 0.85)
        language = str(payload.get("language") or session.locale or "en")
        browser = BrowserPassthroughSpeechRecognitionProvider()
        result = browser.accept_text(
            text,
            language=language,
            confidence=confidence,
            is_final=is_final,
            partial=partial,
        )
        now = self.store._now()
        if result.partial or not result.is_final:
            self.conversation.append_user(
                session,
                result.text,
                provider=result.provider,
                confidence=result.confidence,
                partial=True,
                now=now,
            )
            session.input_state = InputState.RECORDING.value
            self._persist(session)
            return {
                "session": session.to_public(),
                "transcript": result.to_public(),
                "turn": None,
            }
        # Final transcript → conversation turn
        entry = self.conversation.append_user(
            session,
            result.text,
            provider=result.provider,
            confidence=result.confidence,
            partial=False,
            now=now,
        )
        self.repo.add_transcript(session.session_id, entry)
        self._input_for(session).finish_processing()
        session.input_state = InputState.IDLE.value
        turn = self._run_turn(ctx, session, result.text)
        return {
            "session": session.to_public(),
            "transcript": result.to_public(),
            "turn": turn,
        }

    def submit_audio(
        self,
        ctx,
        session_id: str,
        audio_bytes: bytes,
        *,
        content_type: str = "audio/wav",
        sample_rate: int | None = None,
    ) -> dict[str, Any]:
        self._require(ctx, PlatformPermission.VOICE_TRANSCRIBE)
        session = self._get_owned(ctx, session_id)
        if not audio_bytes:
            raise PlatformContextError("VALIDATION_FAILED", "audio is required")
        if len(audio_bytes) > MAX_AUDIO_UPLOAD_BYTES:
            raise PlatformContextError("RESOURCE_BUDGET_EXHAUSTED", "audio too large")
        rate = int(sample_rate or session.sample_rate)
        samples = self._pcm_from_upload(audio_bytes, content_type=content_type, sample_rate=rate)
        input_service = self._input_for(session)
        if input_service.state in {InputState.IDLE.value, InputState.CANCELLED.value}:
            input_service.start(session.input_mode or InputMode.TOGGLE.value)
        vad_payload = input_service.ingest_pcm(samples)
        session.input_state = input_service.state
        provider = select_stt_provider(session.stt_provider, self.stt_providers)
        # Prefer non-browser providers for raw audio
        if provider.provider_id == "browser":
            provider = select_stt_provider("whisper_compatible", self.stt_providers)
            if provider.provider_id == "unavailable":
                provider = select_stt_provider("macos_speech", self.stt_providers)
        result = provider.transcribe(
            samples,
            sample_rate=rate,
            language=(session.locale or "en").split("-")[0],
            timeout_seconds=30.0,
        )
        # Do not persist raw audio.
        now = self.store._now()
        if not result.text:
            session.input_state = InputState.ERROR.value
            session.error_category = result.error_category or "empty_transcript"
            session.error_message = "speech recognition produced no text"
            self.conversation.transition(session, ConversationState.FAILED)
            self._persist(session)
            return {
                "session": session.to_public(),
                "transcript": result.to_public(),
                "vad": vad_payload.get("vad"),
                "turn": None,
            }
        entry = self.conversation.append_user(
            session,
            result.text,
            provider=result.provider,
            confidence=result.confidence,
            partial=False,
            now=now,
        )
        self.repo.add_transcript(session.session_id, entry)
        input_service.finish_processing()
        session.input_state = InputState.IDLE.value
        turn = self._run_turn(ctx, session, result.text)
        return {
            "session": session.to_public(),
            "transcript": result.to_public(),
            "vad": vad_payload.get("vad"),
            "turn": turn,
        }

    def transcribe_audio(
        self,
        ctx,
        session_id: str,
        audio_bytes: bytes,
        *,
        sample_rate: int = 16_000,
        language: str = "en",
    ) -> dict[str, Any]:
        """Authenticated STT-only operation; never creates a conversation turn."""
        self._require(ctx, PlatformPermission.VOICE_TRANSCRIBE)
        session = self._get_owned(ctx, session_id)
        if not audio_bytes or len(audio_bytes) > MAX_AUDIO_UPLOAD_BYTES:
            raise PlatformContextError("VALIDATION_FAILED", "audio payload is invalid")
        provider = select_stt_provider("whisper_compatible", self.stt_providers)
        result = provider.transcribe(
            audio_bytes,
            sample_rate=int(sample_rate),
            language=(language or session.locale or "en").split("-")[0],
            timeout_seconds=30.0,
        )
        return {"transcript": result.to_public(), "session_id": session.session_id}

    # ── turn / speak / interrupt ─────────────────────────────────────────
    def _run_turn(self, ctx, session: ConversationSession, user_text: str) -> dict[str, Any]:
        # Final transcripts may arrive from IDLE after push-to-talk stop.
        if session.state == ConversationState.IDLE.value:
            self.conversation.transition(session, ConversationState.LISTENING)
        if session.state == ConversationState.INTERRUPTED.value:
            self.conversation.transition(session, ConversationState.LISTENING)
        self.conversation.transition(session, ConversationState.THINKING)
        self._persist(session)
        # Bind platform context for ConversationService generation
        self._turn_ctx = ctx
        if self.conversation_service is not None:
            self.conversation.bind_conversation_service(
                self.conversation_service,
                platform_ctx_fn=lambda: self._turn_ctx,
            )
        spoken_so_far = ""
        partial_ops: list[dict[str, Any]] = []
        assembled = ""
        last_emitted = ""
        intelligence_kind = "unavailable"
        try:
            for chunk in self.conversation.stream_reply(session, user_text):
                if not chunk:
                    continue
                # stream_for_voice yields full assembled text; avoid double-append
                if chunk.startswith(assembled) or not assembled:
                    assembled = chunk
                else:
                    assembled = (assembled + " " + chunk).strip()
                if assembled == last_emitted:
                    continue
                last_emitted = assembled
                session.partial_assistant_response = assembled
                self.conversation.transition(session, ConversationState.RESPONDING)
                intelligence_kind = "model"
                # Incremental speech when SpeechService is bound
                if self.speech_service is not None:
                    self._require(ctx, PlatformPermission.VOICE_SPEAK)
                    runtime = self._speech_runtime(session)
                    ops, spoken_so_far = runtime.speak_partial(
                        ctx,
                        assembled,
                        already_spoken=spoken_so_far,
                        voice_profile_id=session.voice_profile_id,
                        language=session.locale,
                        correlation_id=session.session_id,
                    )
                    for op in ops:
                        partial_ops.append(op)
                        play = self._playback_for(session).play(
                            speech_operation_id=op.get("operation_id", ""),
                            text=chunk[-200:] if isinstance(chunk, str) else "",
                        )
                        session.active_speech_operation_id = op.get("operation_id", "")
                        session.active_playback_id = play.playback_id
                        session.playback_state = PlaybackState.PLAYING.value
                self._persist(session)

            final_text = assembled
            if not final_text:
                # Truthful model-unavailable path — never invent intelligence
                session.error_category = "MODEL_NOT_AVAILABLE"
                session.error_message = "No configured conversational model generated a response."
                self.conversation.transition(session, ConversationState.FAILED)
                self._persist(session)
                evidence = self.repo.create_evidence(
                    session,
                    event_type="voice.turn.model_unavailable",
                    summary="Conversational model unavailable; no template reply emitted.",
                    metadata={"user_chars": len(user_text or "")},
                )
                self._audit(
                    ctx,
                    "voice.turn.model_unavailable",
                    session=session,
                    evidence=evidence,
                    outcome="failure",
                )
                return {
                    "assistant_text": "",
                    "speech_operations": [],
                    "evidence_id": evidence,
                    "intelligence_kind": "unavailable",
                    "error_code": "MODEL_NOT_AVAILABLE",
                }

            if self.speech_service is not None and final_text:
                remainder = final_text
                if spoken_so_far and final_text.startswith(spoken_so_far):
                    remainder = final_text[len(spoken_so_far) :].strip()
                if remainder:
                    self._require(ctx, PlatformPermission.VOICE_SPEAK)
                    ops = self._speech_runtime(session).speak_text(
                        ctx,
                        remainder,
                        voice_profile_id=session.voice_profile_id,
                        language=session.locale,
                        correlation_id=session.session_id,
                    )
                    partial_ops.extend(ops)
                    if ops:
                        play = self._playback_for(session).play(
                            speech_operation_id=ops[0].get("operation_id", ""),
                            text=remainder,
                        )
                        session.active_speech_operation_id = ops[0].get(
                            "operation_id", ""
                        )
                        session.active_playback_id = play.playback_id
                        session.playback_state = PlaybackState.PLAYING.value

            entry = self.conversation.append_assistant(
                session,
                final_text,
                partial=False,
                speech_operation_id=session.active_speech_operation_id,
                now=self.store._now(),
            )
            self.repo.add_transcript(session.session_id, entry)
            session.partial_assistant_response = ""
            # After responding, return to listening readiness (not finished)
            self.conversation.transition(session, ConversationState.LISTENING)
            session.input_state = InputState.IDLE.value
            self._persist(session)
            evidence = self.repo.create_evidence(
                session,
                event_type="voice.turn.completed",
                summary="Voice turn completed with model-backed streamed speech.",
                metadata={
                    "user_chars": len(user_text or ""),
                    "assistant_chars": len(final_text or ""),
                    "speech_ops": len(partial_ops),
                    "intelligence_kind": intelligence_kind,
                },
            )
            self._audit(
                ctx,
                "voice.turn.completed",
                session=session,
                evidence=evidence,
            )
            return {
                "assistant_text": final_text,
                "speech_operations": partial_ops,
                "evidence_id": evidence,
                "intelligence_kind": intelligence_kind,
            }
        except PlatformContextError:
            raise
        except Exception as exc:
            session.error_category = "turn_failed"
            session.error_message = str(exc)[:200]
            self.conversation.transition(session, ConversationState.FAILED)
            self._persist(session)
            self._audit(
                ctx,
                "voice.turn.failed",
                session=session,
                outcome="failure",
                detail={"error_category": session.error_category},
            )
            raise PlatformContextError("VOICE_TURN_FAILED", "voice turn failed") from exc
        finally:
            self._turn_ctx = None

    def interrupt(
        self, ctx, session_id: str, *, reason: str = "barge_in"
    ) -> dict[str, Any]:
        self._require(ctx, PlatformPermission.VOICE_LISTEN)
        session = self._get_owned(ctx, session_id)
        from_state = session.state
        preserved = session.partial_assistant_response
        # Cancel model generation first so late chunks are rejected.
        # Do NOT clear multi-turn memory on barge-in — only generation/speech.
        try:
            self.conversation.cancel_active_generation()
        except Exception:
            pass
        if self.conversation_service is not None:
            try:
                for rid in list(getattr(self.conversation_service, "_active", {}) or {}):
                    self.conversation_service.cancel(rid)
            except Exception:
                pass
        # Preserve completed transcript entries; mark latest assistant partial if any
        if preserved:
            entry = self.conversation.append_assistant(
                session,
                preserved,
                partial=False,
                speech_operation_id=session.active_speech_operation_id,
                now=self.store._now(),
                interrupted=True,
            )
            self.repo.add_transcript(session.session_id, entry)
            session.partial_assistant_response = ""
        self._hard_stop_audio(ctx, session)
        record = self.conversation.record_interruption(
            session,
            reason=reason,
            from_state=from_state,
            to_state=ConversationState.INTERRUPTED.value,
            preserved_text=preserved,
            now=self.store._now(),
        )
        self.repo.add_interruption(session.session_id, record)
        self.conversation.transition(session, ConversationState.INTERRUPTED)
        # Begin listening immediately
        snap = self._input_for(session).start(
            session.input_mode or InputMode.TOGGLE.value,
            permission_granted=True,
        )
        self.conversation.transition(session, ConversationState.LISTENING)
        session.input_state = snap["state"]
        session.playback_state = PlaybackState.IDLE.value
        self._persist(session)
        evidence = self.repo.create_evidence(
            session,
            event_type="voice.interrupted",
            summary="Barge-in: playback stopped; listening resumed.",
            metadata={"reason": reason, "from_state": from_state},
        )
        self._audit(ctx, "voice.interrupted", session=session, evidence=evidence)
        return self.get_session(ctx, session_id)

    def playback_control(
        self, ctx, session_id: str, action: str
    ) -> dict[str, Any]:
        self._require(ctx, PlatformPermission.VOICE_SPEAK)
        session = self._get_owned(ctx, session_id)
        controller = self._playback_for(session)
        action = (action or "").strip().lower()
        if action == "play":
            # Resume or no-op; actual audio is client-side after speech ops.
            controller.resume()
        elif action == "pause":
            controller.pause()
        elif action == "resume":
            controller.resume()
        elif action == "stop":
            controller.stop()
            if session.active_speech_operation_id and self.speech_service:
                try:
                    self.speech_service.cancel(ctx, session.active_speech_operation_id)
                except Exception:
                    pass
            session.active_playback_id = ""
        elif action == "cancel":
            controller.cancel()
            if self.speech_service:
                try:
                    self._speech_runtime(session).cancel_all(ctx)
                except Exception:
                    pass
            session.active_speech_operation_id = ""
            session.active_playback_id = ""
        else:
            raise PlatformContextError("VALIDATION_FAILED", "unsupported playback action")
        session.playback_state = controller.state
        self._persist(session)
        return self.get_session(ctx, session_id)

    def mark_playback_complete(
        self, ctx, session_id: str, playback_id: str
    ) -> dict[str, Any]:
        self._require(ctx, PlatformPermission.VOICE_SPEAK)
        session = self._get_owned(ctx, session_id)
        controller = self._playback_for(session)
        controller.complete(playback_id)
        session.playback_state = controller.state
        if controller.current() is None:
            session.active_playback_id = ""
        self._persist(session)
        return self.get_session(ctx, session_id)

    # ── internals ────────────────────────────────────────────────────────
    def _hard_stop_audio(self, ctx, session: ConversationSession) -> None:
        controller = self._playback_for(session)
        controller.cancel()
        if self.speech_service is not None:
            try:
                self._speech_runtime(session).cancel_all(ctx)
            except Exception:
                pass
            if session.active_speech_operation_id:
                try:
                    self.speech_service.cancel(ctx, session.active_speech_operation_id)
                except Exception:
                    pass
        session.active_speech_operation_id = ""
        session.active_playback_id = ""
        session.playback_state = PlaybackState.CANCELLED.value

    def _cleanup_runtime(self, session_id: str) -> None:
        self._inputs.pop(session_id, None)
        self._playback.pop(session_id, None)
        self._speech_runtimes.pop(session_id, None)
        self._spoken_partial.pop(session_id, None)

    @staticmethod
    def _pcm_from_upload(
        audio_bytes: bytes, *, content_type: str, sample_rate: int
    ) -> list[float]:
        ctype = (content_type or "").lower()
        if "wav" in ctype or audio_bytes[:4] == b"RIFF":
            with wave.open(io.BytesIO(audio_bytes), "rb") as handle:
                channels = handle.getnchannels()
                width = handle.getsampwidth()
                rate = handle.getframerate() or sample_rate
                frames = handle.readframes(handle.getnframes())
            if channels > 1:
                frames = audioop.tomono(frames, width, 1, 1)
            if width != 2:
                frames = audioop.lin2lin(frames, width, 2)
            if rate != sample_rate:
                frames, _ = audioop.ratecv(frames, 2, 1, rate, sample_rate, None)
            count = len(frames) // 2
            samples = list(struct.unpack("<" + "h" * count, frames))
            return [s / 32768.0 for s in samples]
        # Treat as mono int16 PCM little-endian
        if len(audio_bytes) % 2:
            audio_bytes = audio_bytes[:-1]
        count = len(audio_bytes) // 2
        samples = list(struct.unpack("<" + "h" * count, audio_bytes))
        return [s / 32768.0 for s in samples]


# Process-local default bound to platform speech service
_DEFAULT_RUNTIME: VoiceSessionManager | None = None
_DEFAULT_LOCK = threading.Lock()


def default_voice_runtime(platform_service) -> VoiceSessionManager:
    global _DEFAULT_RUNTIME
    with _DEFAULT_LOCK:
        existing = getattr(platform_service, "_voice_runtime", None)
        if existing is not None:
            return existing
        from saathi.platform.conversation import default_conversation_service
        from saathi.platform.voice.service import default_speech_service

        speech = default_speech_service(platform_service)
        conversation = default_conversation_service(platform_service)
        runtime = VoiceSessionManager(
            platform_service.store,
            speech_service=speech,
            conversation_service=conversation,
        )
        setattr(platform_service, "_voice_runtime", runtime)
        return runtime


def reset_voice_runtime_for_tests(platform_service=None) -> None:
    global _DEFAULT_RUNTIME
    with _DEFAULT_LOCK:
        _DEFAULT_RUNTIME = None
        if platform_service is not None and hasattr(platform_service, "_voice_runtime"):
            delattr(platform_service, "_voice_runtime")
        if platform_service is not None:
            try:
                from saathi.platform.conversation import (
                    reset_conversation_service_for_tests,
                )

                reset_conversation_service_for_tests(platform_service)
            except Exception:
                pass
