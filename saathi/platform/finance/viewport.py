"""OWNER-ONLY embedded Financial Browser viewport (Plane 1 OWNER_VISUAL + Plane 2 OWNER_INPUT).

Streams the EXISTING provider-scoped Playwright page into SaathiOS via CDP screencast and
forwards bounded owner mouse/keyboard/scroll/navigation back to the SAME page. This is a
separate security plane from the frozen Observation Bridge (Plane 3 SAATHI_OBSERVATION):

  * It NEVER produces structured financial evidence — pixels are for the owner's eyes only.
  * Its input/navigation entrypoints are OWNER_INPUT, gated at the route by owner session +
    loopback + provider + OWNER_CONTROL. They are deliberately NOT agent tools and appear in
    no tool registry / LLM schema / MCP surface.
  * During OWNER_PRIVATE_INPUT (login/OTP/CAPTCHA/2FA), frames and input may transit the
    local transport ephemerally so the owner can authenticate, but nothing is persisted,
    audited, observed, or exposed to any model/agent (OWNER_PRIVATE_INPUT_EPHEMERAL_LOCAL_TRANSIT_ONLY).

No second Chromium is launched: the CDP session attaches to the runtime's live page.
"""
from __future__ import annotations

import base64
import threading
import time
from enum import Enum

from saathi.platform.finance.policy import POLICIES, Provider

# Bounded screencast defaults (measure/adapt; conservative for M2/8GB).
_JPEG_QUALITY = 60
_MAX_W = 1280
_MAX_H = 800
_FRAME_MAX_AGE = 2.0            # seconds; older buffered frame is considered stale


class ViewportState(str, Enum):
    OPEN = "OPEN"                            # attached, not yet streaming
    STREAMING = "STREAMING"                  # frames flowing to owner
    OWNER_PRIVATE_INPUT = "OWNER_PRIVATE_INPUT"
    DISCONNECTED = "DISCONNECTED"
    BROWSER_CRASHED = "BROWSER_CRASHED"
    CLOSED = "CLOSED"


_SENSITIVE_PATH_TOKENS = (
    "login", "signin", "sign-in", "logout", "otp", "2fa", "two-factor", "verify",
    "security", "password", "captcha", "challenge", "auth", "webauthn", "passkey",
)


def _host(url: str) -> str:
    u = (url or "").split("://", 1)[-1]
    return u.split("/", 1)[0].split("?", 1)[0].lower()


def _path(url: str) -> str:
    u = (url or "").split("://", 1)[-1]
    return ("/" + u.split("/", 1)[1]).lower() if "/" in u else "/"


class ViewportSession:
    """One owner viewport bound to a provider's real runtime page."""

    def __init__(self, provider: Provider, runtime_id: str, manager):
        self.provider = provider
        self.runtime_id = runtime_id
        self._m = manager
        self._lock = threading.Lock()
        self._latest_b64: str | None = None
        self._latest_ts = 0.0
        self._css_w = float(_MAX_W)
        self._css_h = float(_MAX_H)
        self.state = ViewportState.OPEN
        self.private_input = False
        self._started = False

    _SIZE_JS = "() => [Math.round(window.innerWidth), Math.round(window.innerHeight)]"

    def _pick_page(self, ctx):
        """Choose the owner's provider page: newest page on the allowed domain, else newest."""
        pol = POLICIES[self.provider]
        try:
            pages = list(ctx.pages)
        except Exception:
            return None
        for pg in reversed(pages):
            try:
                if pol.domain_allowed(_host(pg.url)):
                    return pg
            except Exception:
                continue
        return pages[-1] if pages else None

    # ── setup (runs on the executor thread) — pure Playwright, no CDP session ────
    def start(self) -> dict:
        if self._started:
            return self.status()

        def _setup(ctx, page):
            p = self._pick_page(ctx)
            if p is None:
                return {"ok": False, "reason": "NO_PAGE"}
            out = {"ok": True, "w": None, "h": None}
            try:
                dims = p.evaluate(self._SIZE_JS)
                out["w"], out["h"] = dims[0], dims[1]
            except Exception:
                pass
            return out

        res = self._m.on_context_page(self.provider, _setup, timeout=30.0)
        if not res or not res.get("ok"):
            self.state = ViewportState.BROWSER_CRASHED
            return {"ok": False, "state": self.state.value, "reason": (res or {}).get("reason", "SETUP_FAILED")}
        if res.get("w"):
            self._css_w = float(res["w"])
        if res.get("h"):
            self._css_h = float(res["h"])
        self._started = True
        self.state = ViewportState.STREAMING
        return self.status()

    # ── frame pull (route thread) — ON-DEMAND screenshot, exactly one per poll ──
    # No free-running screencast: each poll captures the current frame, so a slow client
    # simply polls slower (natural backpressure) and nothing buffers/grows unbounded.
    def frame(self) -> dict:
        if self.state == ViewportState.CLOSED:
            return {"ok": False, "state": "CLOSED"}

        def _capture(ctx, page):
            p = self._pick_page(ctx)
            if p is None:
                return {"ok": False, "reason": "PAGE_LOADING"}   # transient during navigation
            out = {"url": None, "w": None, "h": None, "b64": None}
            try:
                out["url"] = p.url
            except Exception:
                pass
            try:
                dims = p.evaluate(self._SIZE_JS)
                out["w"], out["h"] = dims[0], dims[1]
            except Exception:
                pass
            try:
                png = p.screenshot(type="jpeg", quality=_JPEG_QUALITY)   # bytes; viewport only
                out["b64"] = base64.b64encode(png).decode("ascii")
            except Exception as e:
                out["err"] = str(e)[:80]
            return out

        info = self._m.on_context_page(self.provider, _capture, timeout=20.0) or {}
        if info.get("w"):
            self._css_w = float(info["w"])
        if info.get("h"):
            self._css_h = float(info["h"])
        if info.get("b64"):
            with self._lock:
                self._latest_b64 = info["b64"]
                self._latest_ts = time.time()

        # Sensitive-surface detection → OWNER_PRIVATE_INPUT (advisory; owner still sees frames).
        url = info.get("url") or ""
        self.private_input = any(t in _path(url) for t in _SENSITIVE_PATH_TOKENS)
        if self.private_input and self.state == ViewportState.STREAMING:
            self.state = ViewportState.OWNER_PRIVATE_INPUT
        elif not self.private_input and self.state == ViewportState.OWNER_PRIVATE_INPUT:
            self.state = ViewportState.STREAMING

        with self._lock:
            b64 = self._latest_b64
            age = time.time() - self._latest_ts if self._latest_ts else None
        out = {
            "ok": bool(b64), "state": self.state.value, "private_input": self.private_input,
            "frame_b64": b64, "frame_age": age, "css_w": self._css_w, "css_h": self._css_h,
            # NOTE: frames are OWNER_VISUAL only — never persisted / observed / sent to a model.
            "note": ("OWNER_PRIVATE_INPUT_EPHEMERAL_LOCAL_TRANSIT_ONLY"
                     if self.private_input else "OWNER_VISUAL"),
        }
        if not b64:                                  # diagnostics only when no frame (never secrets)
            d = info.get("reason") or info.get("err")
            if d:
                out["detail"] = str(d)[:120]
        return out

    # ── owner input (route thread → executor) — OWNER_INPUT plane only ──────────
    def owner_input(self, ev: dict) -> dict:
        if self.state == ViewportState.CLOSED:
            return {"ok": False, "state": "CLOSED"}
        etype = str(ev.get("type", ""))
        btn = str(ev.get("button", "left"))
        nx = max(0.0, min(1.0, float(ev.get("nx", 0.5))))
        ny = max(0.0, min(1.0, float(ev.get("ny", 0.5))))

        def _dispatch(ctx, page):
            p = self._pick_page(ctx)
            if p is None:
                return {"ok": False, "reason": "NO_PAGE"}
            x = nx * self._css_w
            y = ny * self._css_h
            if etype == "mousemove":
                p.mouse.move(x, y)
            elif etype == "mousedown":
                p.mouse.move(x, y); p.mouse.down(button=btn)
            elif etype == "mouseup":
                p.mouse.up(button=btn)
            elif etype == "click":
                p.mouse.click(x, y, button=btn)
            elif etype == "wheel":
                p.mouse.move(x, y); p.mouse.wheel(float(ev.get("dx", 0)), float(ev.get("dy", 0)))
            elif etype in ("keydown", "char"):
                txt = ev.get("text")
                key = str(ev.get("key", ""))
                if isinstance(txt, str) and len(txt) >= 1:
                    p.keyboard.insert_text(txt)      # printable text; value never logged/stored
                elif key:
                    p.keyboard.press(key)            # control key: Enter/Backspace/Arrow/Tab/…
            elif etype == "keyup":
                pass                                  # press() covers down+up
            else:
                return {"ok": False, "reason": "UNSUPPORTED_EVENT"}
            return {"ok": True}

        return self._m.on_context_page(self.provider, _dispatch, timeout=15.0) or {"ok": False, "reason": "NO_RUNTIME"}

    # ── owner navigation (bounded; domain-policed) ──────────────────────────────
    def navigate(self, action: str, url: str | None = None) -> dict:
        pol = POLICIES[self.provider]

        def _nav(ctx, page):
            p = self._pick_page(ctx)
            if p is None:
                return {"ok": False, "reason": "NO_PAGE"}
            if action == "back":
                p.go_back(wait_until="domcontentloaded")
            elif action == "forward":
                p.go_forward(wait_until="domcontentloaded")
            elif action == "reload":
                p.reload(wait_until="domcontentloaded")
            elif action == "goto" and url:
                if not pol.domain_allowed(_host(url)):        # allowlist only — no arbitrary browsing
                    return {"ok": False, "reason": "PROVIDER_DOMAIN_BLOCKED"}
                p.goto(url, wait_until="domcontentloaded")
            else:
                return {"ok": False, "reason": "UNSUPPORTED_NAV"}
            return {"ok": True, "url": p.url}

        return self._m.on_context_page(self.provider, _nav, timeout=30.0) or {"ok": False, "reason": "NO_RUNTIME"}

    def stop(self) -> None:
        # Nothing to detach (no CDP/screencast); just end streaming and drop any buffer.
        self._started = False
        self.state = ViewportState.CLOSED
        with self._lock:                       # drop any buffered frame (no residue)
            self._latest_b64 = None
            self._latest_ts = 0.0

    def status(self) -> dict:
        return {"ok": True, "provider": self.provider.value, "runtime_id": self.runtime_id,
                "state": self.state.value, "private_input": self.private_input,
                "css_w": self._css_w, "css_h": self._css_h}


# ── registry (one active viewport per provider) ─────────────────────────────────
_SESSIONS: dict[str, ViewportSession] = {}
_REG_LOCK = threading.Lock()


def get_or_create(provider: Provider, runtime_id: str, manager) -> ViewportSession:
    with _REG_LOCK:
        s = _SESSIONS.get(provider.value)
        if s is None or s.runtime_id != runtime_id or s.state == ViewportState.CLOSED:
            if s is not None:
                try:
                    s.stop()
                except Exception:
                    pass
            s = ViewportSession(provider, runtime_id, manager)
            _SESSIONS[provider.value] = s
        return s


def get(provider: Provider) -> ViewportSession | None:
    return _SESSIONS.get(provider.value)


def drop(provider: Provider) -> None:
    with _REG_LOCK:
        s = _SESSIONS.pop(provider.value, None)
    if s is not None:
        try:
            s.stop()
        except Exception:
            pass
