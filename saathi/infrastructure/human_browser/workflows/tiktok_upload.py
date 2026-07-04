"""TikTok upload workflow — drop the video, caption, post. Reuses the engine."""
from __future__ import annotations

from ..pages import tiktok as TT
from ..keyed import KeyedBrowser
from .base import Workflow, visual_check


class TikTokUploadWorkflow(Workflow):
    name = "tiktok_upload"

    def run(self, b, *, path: str = "", video_path: str = "", caption: str = "",
            verifier=None, registry=None, on_teach=None, upload_wait_ms: int = 180000, **_) -> dict:
        video = path or video_path
        kb = KeyedBrowser(b, registry=registry, keys=TT.KEYS, on_teach=on_teach)

        kb.goto(TT.UPLOAD_URL)
        kb.wait_for("tiktok/file_input", state="attached")
        kb.upload("tiktok/file_input", video)

        kb.wait_for("tiktok/caption", timeout_ms=upload_wait_ms)
        visual_check(b, verifier, "Is the TikTok upload page showing a caption field for the video?")
        kb.fill("tiktok/caption", caption)

        visual_check(b, verifier, "Is a Post button available to publish the TikTok?")
        kb.click("tiktok/post")
        return {"published": True, "platform": "tiktok", "caption": caption[:80],
                "steps": b.log(), "timeline": b.timeline()}
