"""YouTube publisher — primitives, workflow sequence, events, learning hook.

All against a fake page (no real Chrome/YouTube). Live selector correctness is
verified separately with a test clip in the logged-in profile.
"""
import pytest

from saathi.infrastructure.human_browser import (
    BrowserPrimitives, BrowserActionError, YouTubeUploadWorkflow, publish,
)
from saathi.infrastructure.human_browser.pages import youtube as YT


class FakeEl:
    def __init__(self, href): self._href = href
    def get_attribute(self, name): return self._href if name == "href" else None


class FakePage:
    def __init__(self, present=frozenset(), share="https://youtu.be/abc123"):
        self.calls = []
        self._present = set(present)
        self._share = share
        self.keyboard = self
    def goto(self, url, **k): self.calls.append(("goto", url))
    def wait_for_selector(self, sel, **k): self.calls.append(("wait", sel))
    def set_input_files(self, sel, path, **k): self.calls.append(("upload", path))
    def fill(self, sel, text, **k): self.calls.append(("fill", sel, text))
    def click(self, sel, **k): self.calls.append(("click", sel))
    def select_option(self, sel, value, **k): self.calls.append(("select", sel, value))
    def press(self, key): self.calls.append(("press", key))
    def screenshot(self, **k): return b"PNG"
    def query_selector(self, sel):
        if sel == YT.SHARE_URL: return FakeEl(self._share)
        return object() if sel in self._present else None


# ── primitives ───────────────────────────────────────────────────────────────
def test_primitives_record_steps_and_fire_sink():
    seen = []
    b = BrowserPrimitives(FakePage(), on_step=lambda s: seen.append(s.action))
    b.goto("https://x"); b.click("#next"); b.fill("#t", "hello")
    assert [s.action for s in b.steps] == ["goto", "click", "fill"]
    assert seen == ["goto", "click", "fill"]           # live event sink fired


def test_primitive_failure_records_and_raises():
    class BadPage:
        def click(self, sel, **k): raise RuntimeError("no element")
    b = BrowserPrimitives(BadPage())
    with pytest.raises(BrowserActionError):
        b.click("#missing")
    assert b.steps[-1].ok is False and b.steps[-1].action == "click"


def test_retry_recovers():
    calls = {"n": 0}
    def flaky():
        calls["n"] += 1
        if calls["n"] < 3: raise RuntimeError("transient")
        return "ok"
    b = BrowserPrimitives(FakePage())
    assert b.retry(flaky, attempts=3, delay=0) == "ok" and calls["n"] == 3


# ── workflow sequence ────────────────────────────────────────────────────────
def test_youtube_upload_sequence_and_result():
    page = FakePage(present={YT.NOT_FOR_KIDS})
    b = BrowserPrimitives(page)
    res = YouTubeUploadWorkflow().run(
        b, video_path="/tmp/mr_yeti.mp4", title="Mr Yeti Ep1",
        description="First episode", visibility="Public")

    assert res["published"] is True
    assert res["video_url"] == "https://youtu.be/abc123"
    assert res["visibility"] == "Public" and res["steps"]

    actions = [s.action for s in b.steps]
    assert actions[:3] == ["goto", "wait_for", "upload"]          # open → wait → drop file
    # title + description filled with the real values
    fills = [c for c in page.calls if c[0] == "fill"]
    assert ("fill", YT.TITLE_BOX, "Mr Yeti Ep1") in fills
    assert any(c[2] == "First episode" for c in fills)
    # not-for-kids + 3 wizard Nexts + visibility + publish = ≥6 clicks
    assert actions.count("click") >= 6
    # visibility radio + publish were clicked
    clicks = [c[1] for c in page.calls if c[0] == "click"]
    assert YT.visibility_radio("Public") in clicks and YT.PUBLISH_BUTTON in clicks


def test_visual_verifier_can_block_a_bad_page():
    page = FakePage()
    b = BrowserPrimitives(page)
    with pytest.raises(BrowserActionError):
        YouTubeUploadWorkflow().run(
            b, video_path="/tmp/x.mp4", title="t",
            verifier=lambda prompt, shot: False)      # vision says the page is wrong → abort


def test_workflow_selects_unlisted():
    page = FakePage()
    b = BrowserPrimitives(page)
    res = YouTubeUploadWorkflow().run(b, video_path="/tmp/x.mp4", title="t", visibility="Unlisted")
    assert res["visibility"] == "Unlisted"
    assert YT.visibility_radio("Unlisted") in [c[1] for c in page.calls if c[0] == "click"]


# ── learning hook (publish → Episodes) ───────────────────────────────────────
class FakeRegistry:
    def __init__(self, result=None, err=None): self._r, self._e = result, err
    def execute(self, *, capability, **payload):
        if self._e: raise self._e
        return self._r


class FakeBus:
    def __init__(self): self.events = []
    def publish_sync(self, n, p): self.events.append((n, p))


def test_publish_emits_browser_published():
    bus = FakeBus()
    out = publish(FakeRegistry(result={"video_url": "https://youtu.be/x", "steps": [1, 2]}),
                  bus=bus, title="Ep1", profile="ajay/youtube", path="clip.mp4")
    assert out["video_url"] == "https://youtu.be/x"
    ev = [e for e in bus.events if e[0] == "browser.published"][0]
    assert ev[1]["ok"] is True and ev[1]["video_url"] == "https://youtu.be/x" and ev[1]["steps"] == [1, 2]


def test_publish_emits_browser_failed_and_reraises():
    bus = FakeBus()
    with pytest.raises(RuntimeError):
        publish(FakeRegistry(err=RuntimeError("all modes down")), bus=bus, title="Ep1")
    assert any(e[0] == "browser.failed" and e[1]["ok"] is False for e in bus.events)


def test_browser_published_becomes_episode():
    from saathi.events import EventBus
    from saathi import episode_bridge
    bus = EventBus()
    rec = []
    episode_bridge.install(bus, record_episode=lambda **kw: rec.append(kw) or 1)
    bus.publish_sync("browser.published", {"title": "Ep1", "ok": True})
    bus.publish_sync("browser.failed", {"title": "Ep2", "ok": False, "error": "boom"})
    intents = [(r["intent"], r["outcome"]) for r in rec]
    assert ("publish", "success") in intents and ("publish", "failure") in intents
