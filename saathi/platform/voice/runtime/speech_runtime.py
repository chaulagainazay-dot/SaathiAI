"""SpeechRuntime — incremental speak path over canonical SpeechService."""
from __future__ import annotations

from typing import Any, Callable

from saathi.voice_os.segmentation import segment_for_speech


class SpeechRuntime:
    """Routes assistant text to SpeechService without replacing it.

    Supports partial/incremental segments so the assistant can begin speaking
    before the full completion is ready.
    """

    def __init__(
        self,
        speech_service,
        *,
        create_speech: Callable[..., dict[str, Any]] | None = None,
        cancel_speech: Callable[..., dict[str, Any]] | None = None,
    ):
        self.speech_service = speech_service
        self._create = create_speech or speech_service.create_speech
        self._cancel = cancel_speech or speech_service.cancel
        self._active_ops: list[str] = []

    def speak_text(
        self,
        ctx,
        text: str,
        *,
        voice_profile_id: str = "yeti_teacher",
        language: str = "en-US",
        source: str = "voice_runtime",
        correlation_id: str = "",
        streaming: bool = True,
        output_format: str = "wav",
        speaking_rate: float = 1.0,
    ) -> list[dict[str, Any]]:
        segments = segment_for_speech(text or "")
        if not segments:
            return []
        operations: list[dict[str, Any]] = []
        for index, segment in enumerate(segments):
            payload = {
                "text": segment,
                "source": source,
                "language": language,
                "voice_profile_id": voice_profile_id,
                "streaming": streaming,
                "output_format": output_format,
                "speaking_rate": speaking_rate,
                "priority": 80 if index == 0 else 60,
                "correlation_id": correlation_id or "",
                "provider": "auto",
            }
            operation = self._create(ctx, payload)
            self._active_ops.append(operation.get("operation_id", ""))
            operations.append(operation)
        return operations

    def speak_partial(
        self,
        ctx,
        partial_text: str,
        *,
        already_spoken: str = "",
        voice_profile_id: str = "yeti_teacher",
        language: str = "en-US",
        correlation_id: str = "",
    ) -> tuple[list[dict[str, Any]], str]:
        """Speak only newly completed sentence boundaries from a partial stream."""
        full = (partial_text or "").strip()
        spoken = already_spoken or ""
        if not full.startswith(spoken):
            # Stream reset — speak from full cleaned segments not yet covered.
            spoken = ""
        remainder = full[len(spoken) :].lstrip()
        # Only emit completed sentences (ending punctuation).
        cut = max(remainder.rfind("."), remainder.rfind("!"), remainder.rfind("?"))
        if cut < 0:
            return [], spoken
        chunk = remainder[: cut + 1].strip()
        if not chunk:
            return [], spoken
        ops = self.speak_text(
            ctx,
            chunk,
            voice_profile_id=voice_profile_id,
            language=language,
            correlation_id=correlation_id,
            streaming=True,
        )
        return ops, spoken + ((" " if spoken else "") + chunk)

    def cancel_all(self, ctx) -> int:
        cancelled = 0
        for operation_id in list(self._active_ops):
            if not operation_id:
                continue
            try:
                self._cancel(ctx, operation_id)
                cancelled += 1
            except Exception:
                pass
        self._active_ops.clear()
        return cancelled

    def forget(self, operation_id: str) -> None:
        self._active_ops = [op for op in self._active_ops if op != operation_id]
