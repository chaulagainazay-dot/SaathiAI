"""LinkedIn post workflow — text post, optional media. Reuses the whole engine."""
from __future__ import annotations

from ..pages import linkedin as LI
from ..keyed import KeyedBrowser
from .base import Workflow, visual_check


class LinkedInPostWorkflow(Workflow):
    name = "linkedin_post"

    def run(self, b, *, text: str = "", media: str = "", verifier=None,
            registry=None, on_teach=None, upload_wait_ms: int = 120000, **_) -> dict:
        kb = KeyedBrowser(b, registry=registry, keys=LI.KEYS, on_teach=on_teach)

        kb.goto(LI.FEED)
        kb.click("linkedin/start_post")
        kb.wait_for("linkedin/editor")
        visual_check(b, verifier, "Is the LinkedIn post composer open with a text field?")
        kb.fill("linkedin/editor", text)

        if media:
            kb.click("linkedin/add_media")
            kb.wait_for("linkedin/media_input", state="attached")
            kb.upload("linkedin/media_input", media)
            if kb.exists("linkedin/media_done"):
                kb.click("linkedin/media_done")

        visual_check(b, verifier, "Is a Post button available to submit the post?")
        kb.click("linkedin/post_button")
        return {"published": True, "platform": "linkedin", "text": text[:80],
                "media": bool(media), "steps": b.log(), "timeline": b.timeline()}
