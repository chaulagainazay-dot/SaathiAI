"""Workflow base + shared helpers (visual verification)."""
from __future__ import annotations

from ..primitives import BrowserPrimitives, BrowserActionError, Step


def visual_check(b: BrowserPrimitives, verifier, prompt: str) -> None:
    """Screenshot → vision model → assert the page looks right. `verifier` is
    injectable: `(prompt, screenshot_b64) -> bool`. Skipped if None. Makes
    workflows resilient to DOM drift — don't trust selectors alone."""
    if verifier is None:
        return
    shot = b.capture()
    try:
        ok = bool(verifier(prompt, shot))
    except Exception as e:
        b._emit(Step("visual_check", prompt, False, f"verifier error: {e}"[:120]))
        return   # a broken verifier must not block a valid run
    b._emit(Step("visual_check", prompt, ok, "" if ok else "vision said the page is wrong"))
    if not ok:
        raise BrowserActionError(f"visual check failed: {prompt}")


class Workflow:
    """Marker base — every workflow implements `run(primitives, **payload) -> dict`."""
    name: str = "workflow"
    def run(self, primitives: BrowserPrimitives, **payload) -> dict:  # pragma: no cover
        raise NotImplementedError
