"""YouTube Studio upload workflow — the sequence, in generic primitives.

Mirrors the manual flow: open Studio upload → drop the file → fill title/description
→ mark not-for-kids → Next ×3 (Details → Elements → Checks → Visibility) → set
visibility → Publish → read the share URL. Selectors live in `pages/youtube.py`;
this file is only the ordering.
"""
from __future__ import annotations

from ..pages import youtube as YT
from .base import Workflow, visual_check


class YouTubeUploadWorkflow(Workflow):
    name = "youtube_upload"

    def run(self, b, *, video_path: str, title: str, description: str = "",
            visibility: str = "Public", verifier=None, wizard_steps: int = 3,
            upload_wait_ms: int = 180000) -> dict:
        # 1. open the upload dialog and drop the file
        b.goto(YT.STUDIO_UPLOAD)
        b.wait_for(YT.FILE_INPUT)
        b.upload(YT.FILE_INPUT, video_path)

        # 2. details form appears once the upload starts processing
        b.wait_for(YT.TITLE_BOX, timeout_ms=upload_wait_ms)
        visual_check(b, verifier, "Is the video details form visible with a Title field?")
        b.fill(YT.TITLE_BOX, title)
        if description:
            b.fill(YT.DESCRIPTION_BOX, description)
        if b.exists(YT.NOT_FOR_KIDS):
            b.click(YT.NOT_FOR_KIDS)

        # 3. advance the wizard: Details → Video elements → Checks → Visibility
        for _ in range(wizard_steps):
            b.click(YT.NEXT_BUTTON)

        # 4. set visibility and publish
        b.click(YT.visibility_radio(visibility))
        visual_check(b, verifier, f"Is visibility set to {visibility} with a Publish/Done button?")
        b.click(YT.PUBLISH_BUTTON)

        # 5. confirm + read the share URL
        b.wait_for(YT.SHARE_URL, timeout_ms=upload_wait_ms)
        el = b.find(YT.SHARE_URL)
        video_url = el.get_attribute("href") if el is not None else ""
        return {"published": True, "video_url": video_url,
                "visibility": visibility, "title": title,
                "steps": b.log(), "timeline": b.timeline()}
