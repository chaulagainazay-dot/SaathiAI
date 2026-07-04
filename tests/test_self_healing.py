"""Self-healing loop — workflow ↔ Selector Registry (reward/penalize/teach)."""
from saathi.infrastructure.human_browser import (
    SelectorRegistry, BrowserPrimitives, YouTubeUploadWorkflow, KeyedBrowser,
)
from saathi.infrastructure.human_browser.pages import youtube as YT


class FakeEl:
    def get_attribute(self, n): return "https://youtu.be/x"


class FakePage:
    def __init__(self, present=frozenset()):
        self.calls = []; self._present = set(present)
    def goto(self, u, **k): self.calls.append(("goto", u))
    def wait_for_selector(self, s, **k): self.calls.append(("wait", s))
    def set_input_files(self, s, p, **k): self.calls.append(("upload", p))
    def fill(self, s, t, **k): self.calls.append(("fill", s, t))
    def click(self, s, **k): self.calls.append(("click", s))
    def screenshot(self, **k): return b"PNG"
    def query_selector(self, s): return FakeEl() if "youtu" in s else (object() if s in self._present else None)


def test_successful_run_rewards_registry(tmp_path):
    reg = SelectorRegistry(db_path=str(tmp_path / "s.db")); YT.seed(reg)
    before = reg.stats("youtube/publish")["confidence"]
    b = BrowserPrimitives(FakePage(present={YT.NOT_FOR_KIDS}))
    YouTubeUploadWorkflow().run(b, video_path="/x.mp4", title="t", registry=reg)
    after = reg.stats("youtube/publish")["confidence"]
    assert after > before                    # each successful keyed step raised confidence


def test_taught_selector_wins_resolution(tmp_path):
    reg = SelectorRegistry(db_path=str(tmp_path / "s.db"))
    reg.seed("youtube/publish", ["#old"]); reg.learn("youtube/publish", "#TAUGHT")
    kb = KeyedBrowser(BrowserPrimitives(FakePage()), registry=reg, keys={})
    assert kb._sel("youtube/publish").startswith("#TAUGHT")   # registry overrides the default


def test_failure_penalizes_and_triggers_teach(tmp_path):
    reg = SelectorRegistry(db_path=str(tmp_path / "s.db")); reg.seed("k", ["#missing"])
    before = reg.stats("k")["confidence"]
    taught = []

    class BadPage:
        def click(self, s, **k): raise RuntimeError("not found")
    kb = KeyedBrowser(BrowserPrimitives(BadPage()), registry=reg, keys={"k": "#missing"},
                      on_teach=lambda key: taught.append(key))
    try:
        kb.click("k")
    except Exception:
        pass
    assert taught == ["k"]                                    # Teach Mode triggered
    assert reg.stats("k")["confidence"] < before             # confidence decayed


def test_no_registry_uses_page_object_defaults(tmp_path):
    # backward-compat: without a registry, keys resolve to the page-object default
    kb = KeyedBrowser(BrowserPrimitives(FakePage()), registry=None, keys=YT.KEYS)
    assert kb._sel("youtube/title") == YT.TITLE_BOX
