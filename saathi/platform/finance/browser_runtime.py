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

# Embedded viewport render size — the headless browser has no window, so it runs at a fixed
# viewport that the owner-only screencast (viewport.py) captures and streams into SaathiOS.
_EMBED_W = 1280
_EMBED_H = 800


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
    embedded: bool = True                 # True = headless browser rendered inside SaathiOS viewport
    launch_error: str | None = None       # diagnostic only (never a secret) when a launch fails
    # NOTE: deliberately NO password/otp/cookie/secret/storage_state/token fields.

    def to_public(self) -> dict:
        d = {"runtime_id": self.runtime_id, "provider": self.provider.value,
             "allowed_domain": self.allowed_domain, "created_at": self.created_at,
             "last_active_at": self.last_active_at, "runtime_state": self.runtime_state.value,
             "auth_state": self.auth_state.value,
             "observation_state": self.observation_state.value,
             "embedded": self.embedded, "owner_control": True,
             "agent_read": self.observation_state == ObservationState.SAATHI_READ_ON}
        if self.launch_error:
            d["launch_error"] = self.launch_error
        return d


class FinancialBrowserRuntimeManager:
    """Owns owner-controlled runtimes, one per provider. On-demand; provider-isolated."""

    def __init__(self):
        self._rt: dict[str, OwnerFinancialBrowserRuntime] = {}
        # provider -> (marker, context). marker = PlaywrightExecutor for a REAL launch, or
        # None for a test-injected fake context. All real Playwright object access is
        # marshalled onto the executor thread (Playwright objects are thread-affine).
        self._pw = {}
        self._exec = None      # lazily-created single Playwright executor thread (real only)

    def _executor(self):
        from saathi.platform.finance.pw_executor import PlaywrightExecutor
        if self._exec is None:
            self._exec = PlaywrightExecutor()
        return self._exec

    def _profile_dir(self, provider: Provider) -> Path:
        d = PROFILE_ROOT / provider.value.lower()
        d.mkdir(parents=True, exist_ok=True)
        return d

    def open(self, provider: Provider, *, now: float | None = None, launch=True
             ) -> OwnerFinancialBrowserRuntime:
        now = now if now is not None else time.time()
        pol = POLICIES[provider]
        headed = _headed_mode()          # legacy opt-in: real external window on the owner's desktop
        rt = OwnerFinancialBrowserRuntime(
            runtime_id=f"ofr_{uuid.uuid4().hex[:12]}", provider=provider,
            allowed_domain=pol.allowed_domains[0] if pol.allowed_domains else "",
            created_at=now, last_active_at=now, embedded=not headed)
        mode = _open_mode(launch=launch, headed=headed, display=_display_available())
        if mode == "NOT_OPEN":
            rt.runtime_state = RuntimeState.NOT_OPEN
        elif mode == "DISPLAY_UNAVAILABLE":
            # Only reachable when the owner explicitly asked for an external headed window
            # but there is no desktop session. The default embedded path never needs one.
            rt.runtime_state = RuntimeState.DISPLAY_UNAVAILABLE
        else:  # "LAUNCH" — embedded headless (default) or headed-with-display (opt-in)
            try:
                self._launch(provider, headless=not headed)
                rt.runtime_state = RuntimeState.OPEN_OWNER_CONTROL
            except Exception as e:
                rt.runtime_state = RuntimeState.PROVIDER_ACCESS_UNAVAILABLE
                rt.launch_error = str(e)[:200]
        self._rt[rt.runtime_id] = rt
        audit.record(provider=provider.value, actor="OWNER_INPUT", capability="OPEN_BROWSER",
                     result=rt.runtime_state.value, session_id=rt.runtime_id)
        return rt

    def _launch(self, provider: Provider, *, headless: bool):
        """Provider-scoped persistent context for OWNER manual login.

        Default (headless=True): no external window — the browser runs headless at a fixed
        viewport and is seen/driven ONLY through the embedded SaathiOS viewport (screencast +
        owner input). This is the "browser inside SaathiOS" path; it needs no desktop display.
        Opt-in (headless=False, SAATHI_FINANCE_HEADED=1): a real external window on the owner's
        Mac. Either way SaathiOS navigates ONCE to the provider's allowed domain and the owner
        does everything else — no credential automation. All Playwright work runs on the single
        executor thread (thread affinity)."""
        ex = self._executor()
        pol = POLICIES[provider]
        udir = str(self._profile_dir(provider))
        seed = f"https://{pol.allowed_domains[0]}/" if pol.allowed_domains else "about:blank"

        def _do():
            pw = ex.pw_onthread()
            ctx = pw.chromium.launch_persistent_context(
                user_data_dir=udir, headless=headless,
                viewport={"width": _EMBED_W, "height": _EMBED_H},
                args=["--no-first-run", "--no-default-browser-check"])
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            try:
                page.goto(seed, wait_until="domcontentloaded", timeout=45000)  # one nav; owner drives after
            except Exception:
                pass  # slow/blocked seed load is non-fatal — owner can reload in the viewport
            return ctx

        ctx = ex.submit(_do, timeout=90.0)
        self._pw[provider] = (ex, ctx)
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
            marker, ctx = handle
            if marker is not None and hasattr(marker, "submit"):   # real: close on executor thread
                try:
                    marker.submit(lambda: ctx.close(), timeout=20.0)
                except Exception:
                    pass
            else:                                                  # test/fake context
                try:
                    ctx.close()
                except Exception:
                    pass
        # Note: the shared Playwright executor thread is left running for other providers;
        # it is stopped only on full manager shutdown, not per-provider close.
        audit.record(provider=rt.provider.value, actor="OWNER_INPUT", capability="CLOSE_BROWSER",
                     result="OK", session_id=runtime_id)
        return True

    def live_page(self, provider: Provider):
        """The current live page of a provider's owner-controlled context, or None.
        Real runtimes return an executor-bound read-only MarshalledPage (thread-safe); test
        fakes return their injected page directly. Read-only callers wrap it in
        ReadOnlyPageReader; interaction is never exposed here."""
        handle = self._pw.get(provider)
        if not handle:
            return None
        marker, ctx = handle
        if marker is not None and hasattr(marker, "submit"):       # real Playwright path
            try:
                page = marker.submit(lambda: (ctx.pages[-1] if ctx.pages else None), timeout=15.0)
            except Exception:
                return None
            if page is None:
                return None
            from saathi.platform.finance.pw_marshal import MarshalledPage
            return MarshalledPage(marker, page)
        try:                                                       # test/fake path
            return ctx.pages[-1] if ctx.pages else None
        except Exception:
            return None

    def is_real_runtime(self, provider: Provider) -> bool:
        """True when a real (executor-backed) Playwright context is live for the provider."""
        h = self._pw.get(provider)
        return bool(h and h[0] is not None and hasattr(h[0], "submit"))

    def on_context_page(self, provider: Provider, fn, *, timeout: float = 30.0):
        """Run fn(ctx, page) on the Playwright executor thread for a real runtime, else None.
        Used by the owner-only viewport (screencast + owner input) — never an agent path."""
        handle = self._pw.get(provider)
        if not handle:
            return None
        marker, ctx = handle
        if marker is None or not hasattr(marker, "submit"):
            return None
        return marker.submit(lambda: fn(ctx, (ctx.pages[-1] if ctx.pages else None)), timeout=timeout)

    def get(self, runtime_id: str):
        return self._rt.get(runtime_id)

    def runtime_for_provider(self, provider: Provider) -> OwnerFinancialBrowserRuntime | None:
        """Newest non-closed runtime for a provider (single-owner model). Used by the
        observation bridge to resolve a provider-scoped request to its own runtime; a
        cross-provider request never reaches another provider's runtime."""
        cands = [r for r in self._rt.values()
                 if r.provider == provider and r.runtime_state != RuntimeState.CLOSED]
        if not cands:
            return None
        return max(cands, key=lambda r: r.created_at)

    def list(self) -> list[dict]:
        return [r.to_public() for r in self._rt.values()]


def _headed_mode() -> bool:
    """Legacy opt-in: open a REAL external browser window on the owner's desktop instead of the
    default embedded (headless-in-SaathiOS) browser. Off by default — the embedded browser needs
    no external window and no desktop session."""
    return os.environ.get("SAATHI_FINANCE_HEADED") == "1"


def _display_available() -> bool:
    """A desktop session that can show an external headed window (headed mode only)."""
    return bool(os.environ.get("DISPLAY") or os.uname().sysname == "Darwin")


def _open_mode(*, launch: bool, headed: bool, display: bool) -> str:
    """Pure classifier for the open() launch decision (kept side-effect free for tests).
    Returns one of: NOT_OPEN, DISPLAY_UNAVAILABLE, LAUNCH."""
    if not launch:
        return "NOT_OPEN"
    if headed and not display:
        return "DISPLAY_UNAVAILABLE"
    return "LAUNCH"


_MANAGER: FinancialBrowserRuntimeManager | None = None


def get_runtime_manager() -> FinancialBrowserRuntimeManager:
    global _MANAGER
    if _MANAGER is None:
        _MANAGER = FinancialBrowserRuntimeManager()
    return _MANAGER
