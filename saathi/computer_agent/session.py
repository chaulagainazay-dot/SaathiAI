"""M17 computer session — explicit consent + control boundary.

Desktop/browser control requires an ACTIVE session bound to the authenticated
user, device, allowed apps/origins/file-roots, risk ceiling, and expiry. The
agent must stop immediately on emergency-stop, expiry, identity change, screen
lock, revocation, or an unexpected secure desktop. No control happens without a
live session — enforced before every action.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum


class SessionState(str, Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    STOPPED = "stopped"          # emergency stop
    REVOKED = "revoked"
    LOCKED = "screen_locked"
    IDENTITY_CHANGED = "identity_changed"
    SECURE_DESKTOP = "secure_desktop"


# default emergency-stop shortcut (configurable, collision-checked)
DEFAULT_EMERGENCY_STOP = "ctrl+alt+esc"
# shortcuts that would collide with common OS actions — refused
_RESERVED_SHORTCUTS = {"cmd+q", "cmd+w", "cmd+tab", "cmd+space", "ctrl+c"}


class SessionInactive(Exception):
    def __init__(self, state: str):
        super().__init__(f"computer session not active: {state}")
        self.state = state


@dataclass
class ComputerSession:
    owner: str                            # authenticated user
    device_id: str = "local"
    os_user: str = ""
    session_id: str = ""
    allowed_apps: list = field(default_factory=list)      # empty = none allowed
    allowed_origins: list = field(default_factory=list)
    file_roots: list = field(default_factory=list)
    allowed_displays: list = field(default_factory=lambda: [0])
    risk_ceiling: int = 2                 # session cannot exceed this without re-consent
    emergency_stop: str = DEFAULT_EMERGENCY_STOP
    screenshot_retention_sec: int = 3600
    clipboard_policy: str = "no_secrets"
    created_at: float = 0.0
    ttl_sec: int = 1800
    state: str = SessionState.ACTIVE.value

    def __post_init__(self):
        self.session_id = self.session_id or "sess_" + uuid.uuid4().hex[:12]
        self.created_at = self.created_at or time.time()
        if self.emergency_stop in _RESERVED_SHORTCUTS:
            raise ValueError(f"emergency-stop shortcut {self.emergency_stop} collides with an OS shortcut")

    # ── liveness ────────────────────────────────────────────────────────────
    def is_active(self, *, now: float | None = None) -> bool:
        now = now or time.time()
        if self.state != SessionState.ACTIVE.value:
            return False
        if now - self.created_at > self.ttl_sec:
            self.state = SessionState.EXPIRED.value
            return False
        return True

    def require_active(self, *, now: float | None = None) -> None:
        if not self.is_active(now=now):
            raise SessionInactive(self.state)

    def stop(self, reason: SessionState = SessionState.STOPPED) -> None:
        self.state = reason.value

    def emergency_stop_now(self) -> dict:
        self.state = SessionState.STOPPED.value
        return {"stopped": True, "session_id": self.session_id, "state": self.state}

    # ── consent scope checks ────────────────────────────────────────────────
    def app_allowed(self, app: str) -> bool:
        return app in self.allowed_apps

    def origin_allowed(self, origin: str) -> bool:
        return any(origin == o or origin.startswith(o) for o in self.allowed_origins)

    def risk_permitted(self, risk: int) -> bool:
        return risk <= self.risk_ceiling

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}
