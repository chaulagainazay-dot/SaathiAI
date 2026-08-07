"""Centralized audio playback controller — single active stream, no overlap."""
from __future__ import annotations

from dataclasses import dataclass, field
import threading
import time
from typing import Any
import uuid

from .models import MAX_QUEUE_PLAYBACK, PlaybackState


@dataclass
class PlaybackItem:
    playback_id: str
    speech_operation_id: str = ""
    text: str = ""
    state: str = PlaybackState.IDLE.value
    created_at: float = field(default_factory=time.time)
    started_at: float = 0.0
    completed_at: float = 0.0

    def to_public(self) -> dict[str, Any]:
        return {
            "playback_id": self.playback_id,
            "speech_operation_id": self.speech_operation_id,
            "text_length": len(self.text or ""),
            "state": self.state,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }


class AudioPlaybackController:
    """Server-side playback authority.

    Actual audio rendering may occur in the browser; this controller prevents
    concurrent authorized playback for a session and coordinates cancel/stop.
    """

    def __init__(self, *, max_queue: int = MAX_QUEUE_PLAYBACK):
        self.max_queue = max(1, min(int(max_queue), MAX_QUEUE_PLAYBACK))
        self._lock = threading.RLock()
        self._queue: list[PlaybackItem] = []
        self._current: PlaybackItem | None = None
        self._paused = False

    @property
    def state(self) -> str:
        with self._lock:
            if self._paused and self._current:
                return PlaybackState.PAUSED.value
            if self._current:
                return PlaybackState.PLAYING.value
            if self._queue:
                return PlaybackState.PLAYING.value
            return PlaybackState.IDLE.value

    def current(self) -> PlaybackItem | None:
        with self._lock:
            return self._current

    def queue_snapshot(self) -> list[dict[str, Any]]:
        with self._lock:
            items = []
            if self._current:
                items.append(self._current.to_public())
            items.extend(item.to_public() for item in self._queue)
            return items

    def play(
        self,
        *,
        speech_operation_id: str = "",
        text: str = "",
        playback_id: str = "",
    ) -> PlaybackItem:
        with self._lock:
            # Never allow overlapping playback — stop current first.
            self._stop_locked(reason="superseded")
            item = PlaybackItem(
                playback_id=playback_id or f"play_{uuid.uuid4().hex[:12]}",
                speech_operation_id=speech_operation_id,
                text=text or "",
                state=PlaybackState.PLAYING.value,
                started_at=time.time(),
            )
            self._current = item
            self._paused = False
            return item

    def queue(
        self,
        *,
        speech_operation_id: str = "",
        text: str = "",
    ) -> PlaybackItem:
        with self._lock:
            if self._current is None and not self._paused:
                return self.play(
                    speech_operation_id=speech_operation_id, text=text
                )
            if len(self._queue) >= self.max_queue:
                raise RuntimeError("playback queue limit reached")
            item = PlaybackItem(
                playback_id=f"play_{uuid.uuid4().hex[:12]}",
                speech_operation_id=speech_operation_id,
                text=text or "",
                state=PlaybackState.IDLE.value,
            )
            self._queue.append(item)
            return item

    def pause(self) -> PlaybackItem | None:
        with self._lock:
            if not self._current:
                return None
            self._paused = True
            self._current.state = PlaybackState.PAUSED.value
            return self._current

    def resume(self) -> PlaybackItem | None:
        with self._lock:
            if not self._current:
                return self._promote_locked()
            self._paused = False
            self._current.state = PlaybackState.PLAYING.value
            return self._current

    def stop(self) -> None:
        with self._lock:
            self._stop_locked(reason="stop")

    def cancel(self) -> None:
        with self._lock:
            self._stop_locked(reason="cancel")
            self._queue.clear()

    def complete(self, playback_id: str) -> PlaybackItem | None:
        with self._lock:
            if self._current and self._current.playback_id == playback_id:
                self._current.state = PlaybackState.STOPPED.value
                self._current.completed_at = time.time()
                finished = self._current
                self._current = None
                self._paused = False
                self._promote_locked()
                return finished
            return None

    def _promote_locked(self) -> PlaybackItem | None:
        if self._current or not self._queue:
            return self._current
        item = self._queue.pop(0)
        item.state = PlaybackState.PLAYING.value
        item.started_at = time.time()
        self._current = item
        self._paused = False
        return item

    def _stop_locked(self, *, reason: str) -> None:
        if self._current:
            self._current.state = (
                PlaybackState.CANCELLED.value
                if reason == "cancel"
                else PlaybackState.STOPPED.value
            )
            self._current.completed_at = time.time()
            self._current = None
        self._paused = False

    def to_public(self) -> dict[str, Any]:
        with self._lock:
            return {
                "state": self.state,
                "current": self._current.to_public() if self._current else None,
                "queue": [item.to_public() for item in self._queue],
                "queue_depth": len(self._queue),
                "max_queue": self.max_queue,
            }
