"""Base agent session adapter contract."""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from saathi.engineering.models import AgentSessionResult, SessionStatus, new_id


class AdapterLaunchError(RuntimeError):
    pass


@dataclass
class LaunchRequest:
    prompt: str
    working_directory: str
    session_id: str = ""
    timeout_sec: float = 3600.0
    env_allowlist: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.session_id:
            self.session_id = new_id("sess")


class AgentSessionAdapter(ABC):
    """Governed adapter: start, poll, stop. No unrestricted shell."""

    name: str = "base"

    def __init__(self, *, max_output_chars: int = 8000):
        self.max_output_chars = max_output_chars
        self._sessions: dict[str, dict[str, Any]] = {}

    def _redact(self, text: str) -> str:
        try:
            from saathi.repair.secrets_scan import redact
            return redact(text or "")
        except Exception:
            return (text or "")[: self.max_output_chars]

    def _tail(self, text: str) -> str:
        t = self._redact(text)
        if len(t) > self.max_output_chars:
            return t[-self.max_output_chars :]
        return t

    def validate_working_directory(self, path: str, allowed_root: str) -> Path:
        root = Path(allowed_root).resolve()
        wd = Path(path).resolve()
        if not str(wd).startswith(str(root)):
            raise AdapterLaunchError("working_directory_outside_allowed_root")
        if not wd.is_dir():
            raise AdapterLaunchError("working_directory_missing")
        # Symlink escape check: require same resolved root ancestry
        try:
            wd.relative_to(root)
        except ValueError as exc:
            raise AdapterLaunchError("path_traversal_denied") from exc
        return wd

    @abstractmethod
    def start(self, request: LaunchRequest, *, allowed_root: str) -> AgentSessionResult:
        ...

    @abstractmethod
    def poll(self, session_id: str) -> AgentSessionResult:
        ...

    @abstractmethod
    def request_stop(self, session_id: str, *, force: bool = False) -> AgentSessionResult:
        ...

    def list_active(self) -> list[str]:
        return [
            sid for sid, s in self._sessions.items()
            if s.get("status") in (
                SessionStatus.RUNNING.value,
                SessionStatus.STARTING.value,
                SessionStatus.STALLED.value,
            )
        ]
