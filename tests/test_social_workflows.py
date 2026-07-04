"""LinkedIn + TikTok browser workflows (same engine as YouTube), fake page."""
from saathi.infrastructure.human_browser import (
    BrowserPrimitives, LinkedInPostWorkflow, TikTokUploadWorkflow, WORKFLOWS,
)
from saathi.infrastructure.human_browser.pages import linkedin as LI, tiktok as TT


class FakePage:
    def __init__(self): self.calls = []
    def goto(self, u, **k): self.calls.append(("goto", u))
    def click(self, s, **k): self.calls.append(("click", s))
    def fill(self, s, t, **k): self.calls.append(("fill", s, t))
    def wait_for_selector(self, s, **k): self.calls.append(("wait", s))
    def set_input_files(self, s, p, **k): self.calls.append(("upload", p))
    def query_selector(self, s): return None
    def screenshot(self, **k): return b"PNG"


def test_all_three_workflows_registered():
    assert set(WORKFLOWS) == {"youtube_upload", "linkedin_post", "tiktok_upload"}


def test_linkedin_text_post():
    page = FakePage()
    r = LinkedInPostWorkflow().run(BrowserPrimitives(page), text="Mr Yeti Lesson #43 is live!")
    assert r["published"] and r["platform"] == "linkedin" and r["media"] is False
    assert ("goto", LI.FEED) in page.calls
    assert any(c[0] == "fill" and c[2] == "Mr Yeti Lesson #43 is live!" for c in page.calls)
    assert sum(1 for c in page.calls if c[0] == "click") >= 2   # start post + post


def test_linkedin_post_with_media():
    page = FakePage()
    r = LinkedInPostWorkflow().run(BrowserPrimitives(page), text="hi", media="/img.png")
    assert r["media"] is True
    assert ("upload", "/img.png") in page.calls


def test_tiktok_upload():
    page = FakePage()
    r = TikTokUploadWorkflow().run(BrowserPrimitives(page), path="/clip.mp4", caption="#mryeti ielts tip")
    assert r["published"] and r["platform"] == "tiktok"
    assert ("goto", TT.UPLOAD_URL) in page.calls
    assert ("upload", "/clip.mp4") in page.calls
    assert any(c[0] == "fill" and c[2] == "#mryeti ielts tip" for c in page.calls)


def test_page_objects_are_self_healing():
    # the fragile, likely-to-change elements carry multiple strategies
    assert LI.POST_BUTTON.count(",") >= 1 and LI.EDITOR.count(",") >= 1
    assert TT.CAPTION.count(",") >= 2 and TT.POST_BUTTON.count(",") >= 1
