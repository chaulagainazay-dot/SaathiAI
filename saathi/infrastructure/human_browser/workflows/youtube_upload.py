"""YouTube Studio upload workflow — the sequence, addressed by KEY.

Elements are named ("youtube/publish"), resolved through the Selector Registry
(self-healing + confidence-over-time) with the page-object as the fallback. When
a step can't resolve, `on_teach` fires → Teach Mode. Selectors live in
`pages/youtube.py`; this file is only the ordering.
"""
from __future__ import annotations

from ..pages import youtube as YT
from ..keyed import KeyedBrowser
from .base import Workflow, visual_check


class YouTubeUploadWorkflow(Workflow):
    name = "youtube_upload"

    def run(self, b, *, path: str = "", video_path: str = "", title: str = "",
            description: str = "", visibility: str = "Public", verifier=None,
            wizard_steps: int = 3, upload_wait_ms: int = 180000, registry=None,
            on_teach=None, **_) -> dict:
        video_path = path or video_path
        kb = KeyedBrowser(b, registry=registry, keys=YT.KEYS, on_teach=on_teach)

        # 1. open the upload dialog and drop the file (hidden input → attached)
        kb.goto(YT.STUDIO_UPLOAD)
        kb.wait_for("youtube/file_input", state="attached")
        kb.upload("youtube/file_input", video_path)

        # 2. details form appears once the upload starts processing
        kb.wait_for("youtube/title", timeout_ms=upload_wait_ms)
        visual_check(b, verifier, "Is the video details form visible with a Title field?")
        kb.fill("youtube/title", title)
        if description:
            kb.fill("youtube/description", description)
        if kb.exists("youtube/not_for_kids"):
            kb.click("youtube/not_for_kids")

        # 3. advance the wizard: Details → Video elements → Checks → Visibility
        for _ in range(wizard_steps):
            kb.click("youtube/next")

        # 4. set visibility (dynamic per level) and publish
        kb.click_selector(YT.visibility_radio(visibility))
        visual_check(b, verifier, f"Is visibility set to {visibility} with a Publish/Done button?")
        kb.click("youtube/publish")

        # 5. confirm + read the share URL
        kb.wait_for("youtube/share_url", timeout_ms=upload_wait_ms)
        el = kb.find("youtube/share_url")
        video_url = el.get_attribute("href") if el is not None else ""
        return {"published": True, "video_url": video_url, "visibility": visibility,
                "title": title, "steps": b.log(), "timeline": b.timeline()}
