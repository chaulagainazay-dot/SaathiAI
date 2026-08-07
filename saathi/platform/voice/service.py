"""Central bounded asynchronous speech service."""
from __future__ import annotations

from dataclasses import replace
import itertools
import os
from pathlib import Path
import queue
import threading
import time
from typing import Any

from saathi.platform.context import PlatformContextError
from saathi.platform.models import PlatformPermission, new_id

from .models import (
    DEFAULT_RETENTION_SECONDS,
    MAX_QUEUE_DEPTH,
    SpeechOperation,
    SpeechRequest,
    SpeechState,
    VoiceValidationError,
    builtin_profiles,
    validate_profile_payload,
)
from .providers import (
    MacOSSystemSpeechProvider,
    ProviderCancelled,
    ProviderError,
    SpeechProvider,
    UnavailableSpeechProvider,
    VoxCPMSpeechProvider,
)
from .repository import VoiceRepository


class SpeechService:
    def __init__(
        self,
        platform_store,
        *,
        providers: list[SpeechProvider] | None = None,
        artifact_root: Path | str | None = None,
        worker_count: int = 2,
        queue_depth: int = MAX_QUEUE_DEPTH,
        retention_seconds: float = DEFAULT_RETENTION_SECONDS,
        start_workers: bool = True,
    ):
        self.store = platform_store
        self.repo = VoiceRepository(platform_store)
        root = artifact_root or os.environ.get("SAATHI_VOICE_ARTIFACT_DIR", "")
        self.artifact_root = (
            Path(root)
            if root
            else Path(platform_store.db_path).parent / "voice-artifacts"
        )
        self.artifact_root = self.artifact_root.resolve()
        if self.artifact_root in {Path("/"), Path.home().resolve()}:
            raise ValueError("speech artifact root is too broad")
        self.artifact_root.mkdir(parents=True, exist_ok=True)
        provider_list = providers or [
            VoxCPMSpeechProvider(),
            MacOSSystemSpeechProvider(),
            UnavailableSpeechProvider(),
        ]
        self.providers = {provider.provider_id: provider for provider in provider_list}
        self.providers.setdefault("unavailable", UnavailableSpeechProvider())
        self.queue_depth = max(1, min(int(queue_depth), MAX_QUEUE_DEPTH))
        self.retention_seconds = max(60.0, min(float(retention_seconds), 7 * 86400.0))
        self._queue: queue.PriorityQueue = queue.PriorityQueue(maxsize=self.queue_depth)
        self._sequence = itertools.count()
        self._requests: dict[str, SpeechRequest] = {}
        self._cancel: dict[str, threading.Event] = {}
        self._queue_lock = threading.RLock()
        self._shutdown = threading.Event()
        self._workers: list[threading.Thread] = []
        self._provider_semaphores = {
            provider_id: threading.BoundedSemaphore(1 if provider.heavy else 2)
            for provider_id, provider in self.providers.items()
        }
        self.reconciled_operations = self.repo.reconcile_interrupted()
        # Warm native voice discovery once so concurrent shell mounts do not
        # stampede `/usr/bin/say -v ?` on first authenticated page load.
        macos = self.providers.get("macos_system")
        if macos is not None:
            try:
                macos.health()
            except Exception:
                pass
        if start_workers:
            for index in range(max(1, min(int(worker_count), 4))):
                worker = threading.Thread(
                    target=self._worker,
                    name=f"saathi-speech-{index}",
                    daemon=True,
                )
                worker.start()
                self._workers.append(worker)

    def _audit(
        self,
        ctx,
        event: str,
        *,
        operation: SpeechOperation | None = None,
        profile_id: str = "",
        outcome: str = "success",
        evidence: str = "",
        detail: dict[str, Any] | None = None,
    ) -> None:
        safe: dict[str, Any] = {}
        if operation:
            safe.update(
                {
                    "operation_id": operation.operation_id,
                    "state": operation.state,
                    "provider": operation.provider or operation.requested_provider,
                    "text_length": operation.text_length,
                }
            )
        if profile_id:
            safe["profile_id"] = profile_id
        safe.update(detail or {})
        self.store.append_audit(
            event,
            user_id=ctx.user_id,
            role=ctx.role,
            org_id=ctx.org_id,
            workspace_id=ctx.workspace_id,
            project_id=getattr(ctx, "project_id", ""),
            mission_id=getattr(ctx, "mission_id", ""),
            outcome=outcome,
            evidence=evidence[:500],
            detail=safe,
        )

    @staticmethod
    def _owner_access(ctx, owner_id: str) -> bool:
        return owner_id == ctx.user_id or ctx.role in {"owner", "admin"}

    def provider_states(self, ctx) -> list[dict[str, Any]]:
        ctx.require_permission(PlatformPermission.VOICE_READ)
        result = []
        for provider in self.providers.values():
            result.append(
                {
                    "provider_id": provider.provider_id,
                    "health": provider.health(),
                    "capabilities": provider.capabilities(),
                }
            )
        return sorted(result, key=lambda item: item["provider_id"])

    def health(self, ctx) -> dict[str, Any]:
        ctx.require_permission(PlatformPermission.VOICE_READ)
        providers = self.provider_states(ctx)
        ready = [
            item["provider_id"]
            for item in providers
            if item["health"]["state"] in {"ready", "ready_unverified"}
        ]
        certified = [
            item["provider_id"]
            for item in providers
            if item["provider_id"] == "macos_system"
            and item["health"]["state"] == "ready"
        ]
        return {
            "status": "healthy" if certified else "degraded",
            "persistence": "single_host_sqlite",
            "queue": {
                "capacity": self.queue_depth,
                "in_memory_depth": self._queue.qsize(),
                "worker_count": len(self._workers),
                "heavy_provider_concurrency": 1,
            },
            "ready_providers": ready,
            "certified_providers": certified,
            "default_provider": certified[0] if certified else "unavailable",
            "english_certified": bool(certified),
            "nepali_state": "unsupported_not_verified",
            "cloning_state": "CAPABILITY_DISABLED",
            "reconciled_on_start": self.reconciled_operations,
        }

    def list_profiles(self, ctx, *, all_owners: bool = False) -> list[dict[str, Any]]:
        ctx.require_permission(PlatformPermission.VOICE_READ)
        owner = "" if all_owners and ctx.role in {"owner", "admin"} else ctx.user_id
        builtins = builtin_profiles(ctx.org_id, ctx.workspace_id, ctx.user_id)
        stored = self.repo.list_profiles(
            org_id=ctx.org_id, workspace_id=ctx.workspace_id, owner_id=owner
        )
        return [profile.to_public() for profile in [*builtins, *stored]]

    def get_profile(self, ctx, profile_id: str):
        if profile_id in {"saathi_default", "yeti_teacher"}:
            return next(
                item
                for item in builtin_profiles(ctx.org_id, ctx.workspace_id, ctx.user_id)
                if item.profile_id == profile_id
            )
        profile = self.repo.get_profile(
            profile_id, org_id=ctx.org_id, workspace_id=ctx.workspace_id
        )
        if not profile or not self._owner_access(ctx, profile.owner_id):
            raise PlatformContextError("NOT_FOUND", "voice profile not found")
        return profile

    def create_profile(self, ctx, payload: dict[str, Any]) -> dict[str, Any]:
        ctx.require_permission(PlatformPermission.VOICE_PROFILE_MANAGE)
        try:
            body = validate_profile_payload(payload)
        except VoiceValidationError as exc:
            raise PlatformContextError("VALIDATION_FAILED", str(exc)) from exc
        profile = self.repo.create_profile(
            org_id=ctx.org_id,
            workspace_id=ctx.workspace_id,
            owner_id=ctx.user_id,
            body=body,
        )
        self._audit(ctx, "voice.profile.created", profile_id=profile.profile_id)
        return profile.to_public()

    def update_profile(
        self, ctx, profile_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        ctx.require_permission(PlatformPermission.VOICE_PROFILE_MANAGE)
        if profile_id in {"saathi_default", "yeti_teacher"}:
            raise PlatformContextError("PERMISSION_DENIED", "built-in profile is immutable")
        profile = self.get_profile(ctx, profile_id)
        if profile.owner_id != ctx.user_id and ctx.role not in {"owner", "admin"}:
            raise PlatformContextError("NOT_FOUND", "voice profile not found")
        merged = {**profile.to_public(), **payload}
        try:
            body = validate_profile_payload(merged, profile_id=profile_id)
        except VoiceValidationError as exc:
            raise PlatformContextError("VALIDATION_FAILED", str(exc)) from exc
        updated = self.repo.update_profile(profile, body)
        self._audit(ctx, "voice.profile.updated", profile_id=profile_id)
        return updated.to_public()

    def delete_profile(self, ctx, profile_id: str) -> bool:
        ctx.require_permission(PlatformPermission.VOICE_PROFILE_MANAGE)
        if profile_id in {"saathi_default", "yeti_teacher"}:
            raise PlatformContextError("PERMISSION_DENIED", "built-in profile is immutable")
        profile = self.get_profile(ctx, profile_id)
        if profile.owner_id != ctx.user_id and ctx.role not in {"owner", "admin"}:
            raise PlatformContextError("NOT_FOUND", "voice profile not found")
        deleted = self.repo.delete_profile(profile)
        if deleted:
            self._audit(ctx, "voice.profile.deleted", profile_id=profile_id)
        return deleted

    def create_speech(self, ctx, payload: dict[str, Any]) -> dict[str, Any]:
        ctx.require_permission(PlatformPermission.VOICE_SPEAK)
        try:
            request = SpeechRequest.from_payload(ctx, payload)
        except VoiceValidationError as exc:
            raise PlatformContextError("VALIDATION_FAILED", str(exc)) from exc
        if request.voice_profile_id:
            profile = self.get_profile(ctx, request.voice_profile_id)
            if profile.status != "active":
                raise PlatformContextError("VALIDATION_FAILED", "voice profile is disabled")
            if profile.reference_artifact_id:
                raise PlatformContextError(
                    "CAPABILITY_DISABLED", "voice cloning is disabled"
                )
            request = replace(
                request,
                provider=(
                    request.provider
                    if request.provider != "auto"
                    else profile.provider
                ),
                voice_id=request.voice_id or profile.provider_voice_id,
                language=profile.language,
                speaking_rate=(
                    request.speaking_rate
                    if "speaking_rate" in payload
                    else profile.accessibility_rate
                ),
                style=request.style or profile.style,
            )
        with self._queue_lock:
            existing = self.repo.find_idempotent(
                org_id=ctx.org_id,
                workspace_id=ctx.workspace_id,
                user_id=ctx.user_id,
                idempotency_key=request.idempotency_key,
            )
            if existing:
                return existing.to_public()
            if (
                self.repo.count_nonterminal(
                    org_id=ctx.org_id, workspace_id=ctx.workspace_id
                )
                >= self.queue_depth
            ):
                raise PlatformContextError("RESOURCE_BUDGET_EXHAUSTED", "speech queue is full")
            operation_id = new_id("speech_")
            operation = self.repo.create_operation(
                request,
                operation_id=operation_id,
                expires_at=self.store._now() + self.retention_seconds,
            )
            self._requests[operation_id] = request
            self._cancel[operation_id] = threading.Event()
            try:
                self._queue.put_nowait(
                    (-request.priority, next(self._sequence), operation_id)
                )
            except queue.Full as exc:
                operation = self.repo.transition(
                    operation,
                    SpeechState.FAILED,
                    error_category="queue_limit",
                    completed_at=self.store._now(),
                )
                raise PlatformContextError(
                    "RESOURCE_BUDGET_EXHAUSTED", "speech queue is full"
                ) from exc
        evidence = self.repo.create_evidence(
            operation,
            event_type="speech.queued",
            summary="Speech request accepted into the bounded local queue.",
            metadata={"text_length": operation.text_length},
        )
        self._audit(ctx, "voice.speech.queued", operation=operation, evidence=evidence)
        return operation.to_public()

    def get_operation(self, ctx, operation_id: str) -> SpeechOperation:
        ctx.require_permission(PlatformPermission.VOICE_READ)
        operation = self.repo.get_operation(
            operation_id, org_id=ctx.org_id, workspace_id=ctx.workspace_id
        )
        if not operation or not self._owner_access(ctx, operation.user_id):
            raise PlatformContextError("NOT_FOUND", "speech operation not found")
        return operation

    def list_operations(self, ctx, *, all_owners: bool = False) -> list[dict[str, Any]]:
        ctx.require_permission(PlatformPermission.VOICE_READ)
        owner = "" if all_owners and ctx.role in {"owner", "admin"} else ctx.user_id
        return [
            operation.to_public()
            for operation in self.repo.list_operations(
                org_id=ctx.org_id,
                workspace_id=ctx.workspace_id,
                user_id=owner,
                limit=200,
            )
        ]

    def cancel(self, ctx, operation_id: str) -> dict[str, Any]:
        ctx.require_permission(PlatformPermission.VOICE_SPEAK)
        operation = self.get_operation(ctx, operation_id)
        if operation.is_terminal():
            return operation.to_public()
        operation = self.repo.request_cancel(operation)
        event = self._cancel.get(operation_id)
        if event:
            event.set()
        for provider in self.providers.values():
            provider.cancel(operation_id)
        current = self.repo.get_operation_unscoped(operation_id)
        if current and current.state == SpeechState.QUEUED.value:
            current = self.repo.transition(
                current,
                SpeechState.CANCELLED,
                completed_at=self.store._now(),
                streaming_state="cancelled",
            )
            self.repo.create_evidence(
                current,
                event_type="speech.cancelled",
                summary="Queued speech request was cancelled.",
            )
        final = self.repo.get_operation_unscoped(operation_id) or operation
        self._audit(ctx, "voice.speech.cancel.requested", operation=final)
        return final.to_public()

    def artifact(self, ctx, operation_id: str) -> tuple[SpeechOperation, Path]:
        operation = self.get_operation(ctx, operation_id)
        if (
            operation.state != SpeechState.COMPLETED.value
            or not operation.artifact_name
            or not operation.artifact_id
        ):
            raise PlatformContextError("NOT_FOUND", "speech artifact not found")
        path = self._artifact_path(operation.operation_id, operation.output_format)
        if path.name != operation.artifact_name or not path.is_file():
            raise PlatformContextError("NOT_FOUND", "speech artifact not found")
        self._audit(ctx, "voice.speech.artifact.read", operation=operation)
        return operation, path

    def evidence(self, ctx, *, all_owners: bool = False) -> list[dict[str, Any]]:
        ctx.require_permission(PlatformPermission.VOICE_AUDIT_READ)
        owner = "" if all_owners and ctx.role in {"owner", "admin"} else ctx.user_id
        return self.repo.list_evidence(
            org_id=ctx.org_id, workspace_id=ctx.workspace_id, user_id=owner
        )

    def _artifact_path(self, operation_id: str, output_format: str) -> Path:
        if not operation_id.startswith("speech_"):
            raise ValueError("invalid speech operation identifier")
        suffix = ".aiff" if output_format == "aiff" else ".wav"
        path = (self.artifact_root / f"{operation_id}{suffix}").resolve()
        if path.parent != self.artifact_root:
            raise ValueError("speech artifact path escaped root")
        return path

    def _worker(self) -> None:
        while not self._shutdown.is_set():
            try:
                _, _, operation_id = self._queue.get(timeout=0.1)
            except queue.Empty:
                continue
            try:
                self._execute(operation_id)
            finally:
                self._queue.task_done()

    def _select_candidates(
        self, request: SpeechRequest
    ) -> list[tuple[SpeechProvider, bool, str]]:
        candidates: list[tuple[SpeechProvider, bool, str]] = []
        if request.provider == "unavailable":
            return [(self.providers["unavailable"], False, "")]
        if request.provider in {"auto", "voxcpm"} and "voxcpm" in self.providers:
            candidates.append((self.providers["voxcpm"], False, ""))
        if request.provider in {"auto", "voxcpm", "macos_system"} and "macos_system" in self.providers:
            fallback = request.provider == "voxcpm"
            candidates.append(
                (
                    self.providers["macos_system"],
                    fallback,
                    "voxcpm_unavailable" if fallback else "",
                )
            )
        candidates.append(
            (
                self.providers["unavailable"],
                request.provider not in {"unavailable", "auto"},
                "requested_provider_unavailable",
            )
        )
        unique: list[tuple[SpeechProvider, bool, str]] = []
        seen = set()
        for candidate in candidates:
            if candidate[0].provider_id not in seen:
                unique.append(candidate)
                seen.add(candidate[0].provider_id)
        return unique

    def _execute(self, operation_id: str) -> None:
        request = self._requests.get(operation_id)
        operation = self.repo.get_operation_unscoped(operation_id)
        if not request or not operation or operation.is_terminal():
            self._finish_memory(operation_id)
            return
        event = self._cancel.get(operation_id) or threading.Event()
        if operation.cancel_requested or event.is_set():
            self._cancel_operation(operation)
            return
        try:
            operation = self.repo.transition(
                operation,
                SpeechState.PREPARING,
                started_at=self.store._now(),
                streaming_state="preparing",
            )
            last_error = "provider_unavailable"
            for provider, fallback, fallback_reason in self._select_candidates(request):
                current = self.repo.get_operation_unscoped(operation_id)
                if not current or current.is_terminal():
                    return
                if current.cancel_requested or event.is_set():
                    self._cancel_operation(current)
                    return
                health = provider.health()
                if health["state"] not in {"ready", "ready_unverified"}:
                    continue
                provider_request = request
                if provider.provider_id == "macos_system":
                    # Prefer browser-playable WAV; AIFF remains available when requested.
                    if request.output_format not in {"aiff", "wav"}:
                        provider_request = replace(
                            request, output_format="wav", streaming=False
                        )
                    else:
                        provider_request = replace(request, streaming=False)
                if provider.provider_id == "voxcpm" and request.output_format != "wav":
                    provider_request = replace(request, output_format="wav")
                operation = self.repo.get_operation_unscoped(operation_id) or current
                if operation.state == SpeechState.PREPARING.value:
                    operation = self.repo.transition(
                        operation,
                        SpeechState.SYNTHESIZING,
                        provider=provider.provider_id,
                        output_format=provider_request.output_format,
                        fallback_used=fallback,
                        fallback_reason=fallback_reason,
                        streaming_state="synthesizing",
                    )
                artifact_path = self._artifact_path(
                    operation_id, provider_request.output_format
                )
                semaphore = self._provider_semaphores[provider.provider_id]
                acquired = semaphore.acquire(timeout=5.0)
                if not acquired:
                    last_error = "concurrency_limit"
                    continue
                try:
                    result = provider.synthesize(
                        provider_request,
                        artifact_path,
                        cancel_check=lambda: event.is_set()
                        or bool(
                            (
                                self.repo.get_operation_unscoped(operation_id)
                                or operation
                            ).cancel_requested
                        ),
                    )
                except ProviderCancelled:
                    current = self.repo.get_operation_unscoped(operation_id) or operation
                    self._cancel_operation(current)
                    return
                except ProviderError as exc:
                    last_error = exc.category
                    if artifact_path.exists():
                        artifact_path.unlink()
                    continue
                finally:
                    semaphore.release()
                current = self.repo.get_operation_unscoped(operation_id) or operation
                if current.cancel_requested or event.is_set():
                    if artifact_path.exists():
                        artifact_path.unlink()
                    self._cancel_operation(current)
                    return
                artifact_id = f"voice-artifact:{operation_id}"
                completed = self.repo.transition(
                    current,
                    SpeechState.COMPLETED,
                    provider=result.provider,
                    artifact_id=artifact_id,
                    artifact_name=artifact_path.name,
                    output_format=result.output_format,
                    sample_rate=result.sample_rate,
                    duration_seconds=result.duration_seconds,
                    artifact_bytes=result.artifact_bytes,
                    streaming_state=result.streaming_state,
                    fallback_used=fallback,
                    fallback_reason=fallback_reason,
                    completed_at=self.store._now(),
                )
                evidence = self.repo.create_evidence(
                    completed,
                    event_type="speech.completed",
                    summary="Local speech artifact completed.",
                    artifact_id=artifact_id,
                    metadata={
                        "provider": result.provider,
                        "artifact_bytes": result.artifact_bytes,
                        "sample_rate": result.sample_rate,
                        "total_ms": round(result.total_ms, 2),
                        "first_audio_ms": round(result.first_audio_ms, 2),
                        "fallback_used": fallback,
                    },
                )
                self.store.append_audit(
                    "voice.speech.completed",
                    user_id=completed.user_id,
                    org_id=completed.organization_id,
                    workspace_id=completed.workspace_id,
                    outcome="success",
                    evidence=evidence,
                    detail={
                        "operation_id": completed.operation_id,
                        "provider": completed.provider,
                        "artifact_bytes": completed.artifact_bytes,
                        "fallback_used": completed.fallback_used,
                    },
                )
                return
            current = self.repo.get_operation_unscoped(operation_id) or operation
            target = (
                SpeechState.UNAVAILABLE
                if last_error == "provider_unavailable"
                else SpeechState.FAILED
            )
            failed = self.repo.transition(
                current,
                target,
                error_category=last_error,
                completed_at=self.store._now(),
                streaming_state=target.value,
            )
            self.repo.create_evidence(
                failed,
                event_type=f"speech.{target.value}",
                summary="Speech synthesis ended without an audio artifact.",
                metadata={"error_category": last_error},
            )
        except Exception:
            current = self.repo.get_operation_unscoped(operation_id)
            if current and not current.is_terminal():
                try:
                    self.repo.transition(
                        current,
                        SpeechState.FAILED,
                        error_category="internal_failure",
                        completed_at=self.store._now(),
                        streaming_state="failed",
                    )
                except Exception:
                    pass
        finally:
            self._finish_memory(operation_id)

    def _cancel_operation(self, operation: SpeechOperation) -> None:
        if not operation.is_terminal():
            try:
                cancelled = self.repo.transition(
                    operation,
                    SpeechState.CANCELLED,
                    cancel_requested=True,
                    completed_at=self.store._now(),
                    streaming_state="cancelled",
                )
                self.repo.create_evidence(
                    cancelled,
                    event_type="speech.cancelled",
                    summary="Speech synthesis cancellation was confirmed.",
                )
            except (ValueError, RuntimeError):
                pass
        for suffix in (".aiff", ".wav"):
            path = (self.artifact_root / f"{operation.operation_id}{suffix}").resolve()
            if path.parent == self.artifact_root and path.exists():
                path.unlink()
        self._finish_memory(operation.operation_id)

    def _finish_memory(self, operation_id: str) -> None:
        self._requests.pop(operation_id, None)
        self._cancel.pop(operation_id, None)

    def wait(self, operation_id: str, timeout: float = 5.0) -> SpeechOperation:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            operation = self.repo.get_operation_unscoped(operation_id)
            if operation and operation.is_terminal():
                return operation
            time.sleep(0.01)
        operation = self.repo.get_operation_unscoped(operation_id)
        if not operation:
            raise KeyError(operation_id)
        return operation

    def cleanup_expired(self) -> int:
        now = self.store._now()
        completed = self.repo.list_operations(
            org_id="",
            workspace_id="",
            states=(SpeechState.COMPLETED.value,),
            limit=500,
        )
        cleaned = 0
        for operation in completed:
            if operation.expires_at and operation.expires_at <= now:
                path = self._artifact_path(operation.operation_id, operation.output_format)
                if path.exists():
                    path.unlink()
                self.repo.transition(
                    operation,
                    SpeechState.EXPIRED,
                    artifact_id="",
                    artifact_name="",
                    artifact_bytes=0,
                    streaming_state="expired",
                )
                cleaned += 1
        return cleaned

    def shutdown(self) -> None:
        self._shutdown.set()
        for event in self._cancel.values():
            event.set()
        for provider in self.providers.values():
            provider.shutdown()
        for worker in self._workers:
            worker.join(timeout=1.0)


_DEFAULT_LOCK = threading.RLock()


def default_speech_service(platform_service) -> SpeechService:
    with _DEFAULT_LOCK:
        existing = getattr(platform_service, "_speech_service", None)
        if existing is None:
            existing = SpeechService(platform_service.store)
            setattr(platform_service, "_speech_service", existing)
        return existing


def reset_speech_service_for_tests(platform_service=None) -> None:
    if platform_service is None:
        return
    existing = getattr(platform_service, "_speech_service", None)
    if existing is not None:
        existing.shutdown()
        delattr(platform_service, "_speech_service")
