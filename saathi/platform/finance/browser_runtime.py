"""Owner-controlled financial browser runtime (manual login) + read-only observation gate.

The OWNER personally opens a provider site in a headed, provider-scoped browser and enters
every credential (password/OTP/2FA/CAPTCHA/passkey) themselves. SaathiOS NEVER enters,
captures, reads, logs, or sends credentials to any model. After the owner authenticates and
explicitly enables "Saathi Read", the agent may run a DETERMINISTIC read-only observer over
an allowlist of DOM fields — it can never click/type/navigate/submit or execute any financial
action. No API key is required. Credentials/cookies live in the browser's own per-provider
user-data-dir and are never surfaced through these contracts.
"""
from __future__ import annotations

import os
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from saathi.platform.finance import audit
from saathi.platform.finance.policy import POLICIES, Provider

# provider-scoped persistent profiles (cookies isolated per provider; never read into app/LLM)
PROFILE_ROOT = Path.home() / ".saathi" / "finance_browser"


class RuntimeState(str, Enum):
    NOT_OPEN = "NOT_OPEN"
    OPEN_OWNER_CONTROL = "OPEN_OWNER_CONTROL"
    DISPLAY_UNAVAILABLE = "DISPLAY_UNAVAILABLE"          # no desktop session to show the window
    PROVIDER_ACCESS_UNAVAILABLE = "PROVIDER_ACCESS_UNAVAILABLE"
    CLOSED = "CLOSED"


class AuthState(str, Enum):
    UNKNOWN = "AUTH_STATE_UNKNOWN"
    OWNER_AUTHENTICATED = "OWNER_AUTHENTICATED"
    OWNER_REAUTH_REQUIRED = "OWNER_REAUTHENTICATION_REQUIRED"


class ObservationState(str, Enum):
    SAATHI_READ_OFF = "SAATHI_READ_OFF"                  # default after login
    SAATHI_READ_ON = "SAATHI_READ_ON"                    # owner explicitly enabled


@dataclass
class OwnerFinancialBrowserRuntime:
    runtime_id: str
    provider: Provider
    allowed_domain: str
    created_at: float
    last_active_at: float
    runtime_state: RuntimeState = RuntimeState.NOT_OPEN
    auth_state: AuthState = AuthState.UNKNOWN
    observation_state: ObservationState = ObservationState.SAATHI_READ_OFF
    ttl_sec: float = 1800.0
    # NOTE: deliberately NO password/otp/cookie/secret/storage_state/token fields.

    def to_public(self) -> dict:
        return {"runtime_id": self.runtime_id, "provider": self.provider.value,
                "allowed_domain": self.allowed_domain, "created_at": self.created_at,
                "last_active_at": self.last_active_at, "runtime_state": self.runtime_state.value,
                "auth_state": self.auth_state.value,
                "observation_state": self.observation_state.value,
                "owner_control": True, "agent_read": self.observation_state == ObservationState.SAATHI_READ_ON}


class FinancialBrowserRuntimeManager:
    """Owns owner-controlled runtimes, one per provider. On-demand; provider-isolated."""

    def __init__(self):
        self._rt: dict[str, OwnerFinancialBrowserRuntime] = {}
        self._pw = {}          # provider -> (playwright, context) live handles (real Mac only)

    def _profile_dir(self, provider: Provider) -> Path:
        d = PROFILE_ROOT / provider.value.lower()
        d.mkdir(parents=True, exist_ok=True)
        return d

    def open(self, provider: Provider, *, now: float | None = None, launch=True
             ) -> OwnerFinancialBrowserRuntime:
        now = now if now is not None else time.time()
        pol = POLICIES[provider]
        rt = OwnerFinancialBrowserRuntime(
            runtime_id=f"ofr_{uuid.uuid4().hex[:12]}", provider=provider,
            allowed_domain=pol.allowed_domains[0] if pol.allowed_domains else "",
            created_at=now, last_active_at=now)
        # A headed window needs a real desktop session. Without one, defer to owner env.
        if launch and not (os.environ.get("DISPLAY") or os.uname().sysname == "Darwin" and _has_gui()):
            rt.runtime_state = RuntimeState.DISPLAY_UNAVAILABLE
        elif launch and _headed_launch_available():
            try:
                self._launch_headed(provider)
                rt.runtime_state = RuntimeState.OPEN_OWNER_CONTROL
            except Exception:
                rt.runtime_state = RuntimeState.DISPLAY_UNAVAILABLE
        else:
            rt.runtime_state = RuntimeState.NOT_OPEN
        self._rt[rt.runtime_id] = rt
        audit.record(provider=provider.value, actor="OWNER_INPUT", capability="OPEN_BROWSER",
                     result=rt.runtime_state.value, session_id=rt.runtime_id)
        return rt

    def _launch_headed(self, provider: Provider):
        """Headed, provider-scoped persistent context for OWNER manual login (real Mac only).
        SaathiOS opens the window and navigates ONCE to the provider's allowed domain; the
        owner does everything else. No credential automation."""
        from playwright.sync_api import sync_playwright
        pol = POLICIES[provider]
        pw = sync_playwright().start()
        ctx = pw.chromium.launch_persistent_context(
            user_data_dir=str(self._profile_dir(provider)), headless=False,
            args=["--no-first-run", "--no-default-browser-check"])
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        seed = f"https://{pol.allowed_domains[0]}/" if pol.allowed_domains else "about:blank"
        page.goto(seed, wait_until="domcontentloaded")     # one owner-facing navigation only
        self._pw[provider] = (pw, ctx)
        return ctx

    def mark_owner_authenticated(self, runtime_id: str) -> OwnerFinancialBrowserRuntime | None:
        rt = self._rt.get(runtime_id)
        if rt is None:
            return None
        rt.auth_state = AuthState.OWNER_AUTHENTICATED
        rt.last_active_at = time.time()
        return rt

    def set_saathi_read(self, runtime_id: str, on: bool) -> OwnerFinancialBrowserRuntime | None:
        rt = self._rt.get(runtime_id)
        if rt is None:
            return None
        if on and rt.auth_state != AuthState.OWNER_AUTHENTICATED:
            return rt                                       # cannot enable read before owner auth
        rt.observation_state = ObservationState.SAATHI_READ_ON if on else ObservationState.SAATHI_READ_OFF
        audit.record(provider=rt.provider.value, actor="OWNER_INPUT",
                     capability="SAATHI_READ_" + ("ON" if on else "OFF"), result="OK",
                     session_id=runtime_id)
        return rt

    def read_allowed(self, runtime_id: str) -> bool:
        rt = self._rt.get(runtime_id)
        return bool(rt and rt.auth_state == AuthState.OWNER_AUTHENTICATED
                    and rt.observation_state == ObservationState.SAATHI_READ_ON
                    and rt.runtime_state != RuntimeState.CLOSED)

    def disable_saathi_read(self, runtime_id: str) -> bool:
        """Kill switch: revoke agent read; owner browser may stay open."""
        rt = self._rt.get(runtime_id)
        if rt is None:
            return False
        rt.observation_state = ObservationState.SAATHI_READ_OFF
        audit.record(provider=rt.provider.value, actor="OWNER_INPUT", capability="DISABLE_SAATHI_READ",
                     result="OK", session_id=runtime_id)
        return True

    def close(self, runtime_id: str) -> bool:
        rt = self._rt.get(runtime_id)
        if rt is None:
            return False
        rt.runtime_state = RuntimeState.CLOSED
        rt.observation_state = ObservationState.SAATHI_READ_OFF
        rt.auth_state = AuthState.UNKNOWN
        handle = self._pw.pop(rt.provider, None)
        if handle:
            pw, ctx = handle
            try:
                ctx.close()
            except Exception:
                pass
            try:
                pw.stop()
            except Exception:
                pass
        audit.record(provider=rt.provider.value, actor="OWNER_INPUT", capability="CLOSE_BROWSER",
                     result="OK", session_id=runtime_id)
        return True

    def get(self, runtime_id: str):
        return self._rt.get(runtime_id)

    def list(self) -> list[dict]:
        return [r.to_public() for r in self._rt.values()]


def _has_gui() -> bool:
    """macOS has a window server available to the user session? Heuristic; owner env only."""
    return bool(os.environ.get("SAATHI_FINANCE_HEADED") == "1")


def _headed_launch_available() -> bool:
    return _has_gui() or bool(os.environ.get("DISPLAY"))


_MANAGER: FinancialBrowserRuntimeManager | None = None


def get_runtime_manager() -> FinancialBrowserRuntimeManager:
    global _MANAGER
    if _MANAGER is None:
        _MANAGER = FinancialBrowserRuntimeManager()
    return _MANAGER
