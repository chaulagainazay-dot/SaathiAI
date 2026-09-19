"""M — NATIVE_EMBEDDED_FINANCIAL_BROWSER_VIEWPORT tests (fakes; no real browser).

Proves the OWNER-only viewport plane: on-demand screenshot lifecycle, coordinate scaling,
keyboard values never stored, bounded/domain-policed navigation, private-input state, no
second Chromium, and — critically — that owner input is NOT an agent tool and the frozen
observation bridge gained no viewport surface. Pure Playwright page APIs (no CDP session).
"""
from __future__ import annotations

import base64
import json

import pytest

from saathi.platform.finance import viewport as vp
from saathi.platform.finance.policy import Provider


class FakeMouse:
    def __init__(self): self.calls = []
    def move(self, x, y): self.calls.append(("move", x, y))
    def down(self, button="left"): self.calls.append(("down", button))
    def up(self, button="left"): self.calls.append(("up", button))
    def click(self, x, y, button="left"): self.calls.append(("click", x, y, button))
    def wheel(self, dx, dy): self.calls.append(("wheel", dx, dy))


class FakeKeyboard:
    def __init__(self): self.calls = []
    def press(self, key): self.calls.append(("press", key))
    def insert_text(self, text): self.calls.append(("insert_text", text))
    def down(self, key): self.calls.append(("down", key))
    def up(self, key): self.calls.append(("up", key))


class FakePage:
    def __init__(self, url="https://nepalstock.com/"):
        self.url = url
        self.mouse = FakeMouse()
        self.keyboard = FakeKeyboard()
        self.nav = []
        self.shots = 0
    def evaluate(self, js): return [1000, 500]
    def screenshot(self, type="jpeg", quality=60): self.shots += 1; return b"JPEGBYTES"
    def go_back(self, **k): self.nav.append("back")
    def go_forward(self, **k): self.nav.append("forward")
    def reload(self, **k): self.nav.append("reload")
    def goto(self, url, **k): self.nav.append(("goto", url)); self.url = url


class FakeCtx:
    def __init__(self, page): self._pages = [page]; self.launched = 0
    @property
    def pages(self): return self._pages
    def launch_persistent_context(self, **k):    # must NEVER be called by the viewport
        self.launched += 1; return self


class FakeManager:
    def __init__(self, page): self._page = page; self._ctx = FakeCtx(page)
    def runtime_for_provider(self, p): return type("RT", (), {"runtime_id": "ofr_test"})()
    def is_real_runtime(self, p): return True
    def on_context_page(self, provider, fn, *, timeout=30.0):
        return fn(self._ctx, self._ctx.pages[-1])


@pytest.fixture(autouse=True)
def _clean():
    vp.drop(Provider.NEPSE)
    yield
    vp.drop(Provider.NEPSE)


def _sess(url="https://nepalstock.com/"):
    page = FakePage(url)
    m = FakeManager(page)
    s = vp.get_or_create(Provider.NEPSE, "ofr_test", m)
    return s, m, page


# 1 — start → STREAMING (no free-running screencast); stop → CLOSED + buffer cleared
def test_lifecycle():
    s, m, page = _sess()
    st = s.start()
    assert st["state"] == vp.ViewportState.STREAMING.value
    assert s._css_w == 1000.0 and s._css_h == 500.0   # sized from page.evaluate
    s.stop()
    assert s.state == vp.ViewportState.CLOSED and s._latest_b64 is None


# 2 — each poll captures exactly one fresh JPEG on-demand (newest wins, no buffer growth)
def test_frame_on_demand():
    s, m, page = _sess(); s.start()
    out = s.frame()
    assert out["ok"] and base64.b64decode(out["frame_b64"]) == b"JPEGBYTES"
    n1 = page.shots
    s.frame()
    assert page.shots == n1 + 1                        # one screenshot per frame(): backpressured


# 3 — every frame refreshes layout size for coordinate mapping
def test_frame_metrics():
    s, m, page = _sess(); s.start(); s.frame()
    assert s._css_w == 1000.0 and s._css_h == 500.0


# 4 — private-input on a sensitive URL; frames still transit, note is ephemeral-only
def test_private_input():
    s, m, page = _sess("https://nepalstock.com/login"); s.start()
    out = s.frame()
    assert out["private_input"] is True
    assert out["state"] == vp.ViewportState.OWNER_PRIVATE_INPUT.value
    assert out["note"] == "OWNER_PRIVATE_INPUT_EPHEMERAL_LOCAL_TRANSIT_ONLY"
    page.url = "https://nepalstock.com/today-price"
    assert s.frame()["state"] == vp.ViewportState.STREAMING.value


# 5 — coordinate scaling: normalized → css px via layout size
def test_coordinate_scaling():
    s, m, page = _sess(); s.start(); s.frame()
    s.owner_input({"type": "click", "nx": 0.5, "ny": 0.4})
    assert ("click", 500.0, 200.0, "left") in page.mouse.calls


# 6 — keyboard dispatched (insert_text for printable; press for control) but never stored
def test_keyboard_not_stored():
    s, m, page = _sess(); s.start()
    s.owner_input({"type": "keydown", "key": "a", "text": "a"})
    s.owner_input({"type": "char", "text": "secret123"})
    s.owner_input({"type": "keydown", "key": "Enter"})
    blob = json.dumps({k: str(v) for k, v in vars(s).items()})
    assert "secret123" not in blob                     # no keystroke persistence on the session
    assert ("insert_text", "secret123") in page.keyboard.calls
    assert ("press", "Enter") in page.keyboard.calls


# 7 — navigation: back/reload work; goto off-domain blocked, on-domain allowed
def test_navigation_domain():
    s, m, page = _sess(); s.start()
    assert s.navigate("back")["ok"] and "back" in page.nav
    assert s.navigate("reload")["ok"]
    bad = s.navigate("goto", "https://evil.example.com/x")
    assert bad["ok"] is False and bad["reason"] == "PROVIDER_DOMAIN_BLOCKED"
    assert s.navigate("goto", "https://nepalstock.com/today-price")["ok"] is True


# 8 — no second Chromium: viewport never calls launch_persistent_context
def test_no_second_chromium():
    s, m, page = _sess()
    s.start(); s.frame(); s.owner_input({"type": "mousemove", "nx": 0.1, "ny": 0.1}); s.navigate("reload")
    assert m._ctx.launched == 0


# 9 — CRITICAL: owner-input endpoints are NOT agent tools / not in the frozen bridge
def test_owner_input_not_agent_tool():
    from saathi.platform.finance.observation_bridge import FinancialBrowserObservationService
    for banned in ("owner_input", "navigate", "frame", "viewport", "dispatch", "start_screencast", "mouse", "keyboard"):
        assert not hasattr(FinancialBrowserObservationService, banned), banned
    assert not hasattr(vp, "TOOLS") and not hasattr(vp, "AGENT_TOOLS")


# 10 — frame payload carries no raw DOM / HTML / cookie / token channels
def test_frame_no_raw_channels():
    s, m, page = _sess(); s.start()
    blob = json.dumps(s.frame()).lower()
    for bad in ('"html"', '"dom"', '"cookie"', '"token"', '"storage"', 'outerhtml', 'innerhtml'):
        assert bad not in blob


# 11 — registry keeps ONE active viewport per provider (new runtime replaces old)
def test_single_viewport_per_provider():
    s1, m1, _ = _sess()
    s2 = vp.get_or_create(Provider.NEPSE, "ofr_other", m1)
    assert s2 is not s1 and vp.get(Provider.NEPSE) is s2
