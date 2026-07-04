"""publish() — the Content-Factory entry point that closes the learning loop.

Runs a publish capability through the Connector Registry (API→Browser→Human
fallback) and emits `browser.published` / `browser.failed` — with the workflow's
step log — so every publish becomes an Episode the Learning Runtime can explain
("why did YouTube publishing fail?") without opening logs.
"""
from __future__ import annotations


def publish(registry, *, bus=None, capability: str = "publish_video", **payload) -> dict:
    def _emit(name, extra):
        if bus is None:
            return
        try:
            bus.publish_sync(name, extra)
        except Exception:
            pass
    try:
        result = registry.execute(capability=capability, **payload) or {}
        _emit("browser.published", {
            "capability": capability, "title": payload.get("title"),
            "profile": payload.get("profile"), "video_url": result.get("video_url"),
            "steps": result.get("steps", []), "ok": True})
        return result
    except Exception as e:
        _emit("browser.failed", {"capability": capability, "error": str(e),
                                 "title": payload.get("title"), "ok": False})
        raise
