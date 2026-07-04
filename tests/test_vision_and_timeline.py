"""Production-grade upgrades — Vision Verifier, Step Timeline, self-healing selectors."""
from saathi.infrastructure.human_browser import (
    VisionVerifier, BrowserPrimitives, YouTubeUploadWorkflow,
)
from saathi.infrastructure.human_browser.pages import youtube as YT


# ── Vision Verifier ──────────────────────────────────────────────────────────
def test_vision_verifier_yes_no():
    v = VisionVerifier(ask=lambda prompt, img: "YES")
    assert v("Is the upload dialog open?", "b64") is True
    v2 = VisionVerifier(ask=lambda prompt, img: "No, wrong page")
    assert v2("Is the upload dialog open?", "b64") is False


def test_vision_verifier_available_gating(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    assert VisionVerifier().available() is False
    assert VisionVerifier(ask=lambda p, i: "YES").available() is True
    monkeypatch.setenv("OPENAI_API_KEY", "sk-x")
    assert VisionVerifier().available() is True


def test_vision_verifier_outage_does_not_block():
    def boom(prompt, img): raise RuntimeError("vision api down")
    v = VisionVerifier(ask=boom)
    assert v("anything", "b64") is True   # degrade gracefully, don't block a valid run


def test_workflow_runs_vision_check_at_each_gate():
    prompts = []
    verifier = VisionVerifier(ask=lambda prompt, img: prompts.append(prompt) or "YES")

    class FakeEl:
        def get_attribute(self, n): return "https://youtu.be/x"

    class FakePage:
        def __init__(self): self.keyboard = self
        def goto(self, u, **k): pass
        def wait_for_selector(self, s, **k): pass
        def set_input_files(self, s, p, **k): pass
        def fill(self, s, t, **k): pass
        def click(self, s, **k): pass
        def screenshot(self, **k): return b"PNG"
        def query_selector(self, s): return FakeEl() if s == YT.SHARE_URL else None

    b = BrowserPrimitives(FakePage())
    YouTubeUploadWorkflow().run(b, video_path="/x.mp4", title="t", verifier=verifier)
    # two visual gates: after upload (details form) and before publish (visibility)
    assert len(prompts) == 2
    assert any("details" in p.lower() for p in prompts)
    assert any("publish" in p.lower() or "visibility" in p.lower() for p in prompts)


# ── Step Timeline ────────────────────────────────────────────────────────────
def test_timeline_is_ordered_with_elapsed():
    class P:
        def goto(self, u, **k): pass
        def click(self, s, **k): pass
    b = BrowserPrimitives(P())
    b.goto("https://x"); b.click("#a"); b.click("#b")
    tl = b.timeline()
    assert [row["action"] for row in tl] == ["goto", "click", "click"]
    assert all("clock" in r and "elapsed_ms" in r and r["ok"] for r in tl)
    assert tl[0]["elapsed_ms"] == 0 and tl[-1]["elapsed_ms"] >= 0


# ── self-healing selectors (multi-strategy comma CSS) ────────────────────────
def test_page_objects_carry_multiple_strategies():
    # each critical element offers ≥3 fallback strategies (id, aria, attribute)
    assert YT.TITLE_BOX.count(",") >= 2
    assert YT.DESCRIPTION_BOX.count(",") >= 2
    assert YT.PUBLISH_BUTTON.count(",") >= 1
    assert YT.visibility_radio("Public").count(",") >= 1
