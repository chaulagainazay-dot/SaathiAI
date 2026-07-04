"""publish() — the Content-Factory entry point that closes the learning loop.

Runs a publish capability through the Connector Registry (API→Browser→Human
fallback) and emits `browser.published` / `browser.failed` — with the workflow's
step log — so every publish becomes an Episode the Learning Runtime can explain
("why did YouTube publishing fail?") without opening logs.
"""
from __future__ import annotations


def publish(registry, *, bus=None, store=None, capability: str = "publish_video", **payload) -> dict:
    import time
    from .run_store import default_store
    store = store or default_store()

    def _emit(name, extra):
        if bus is None:
            return
        try:
            bus.publish_sync(name, extra)
        except Exception:
            pass

    t0 = time.time()
    try:
        result = registry.execute(capability=capability, **payload) or {}
        store.record(workflow=payload.get("workflow", ""), profile=payload.get("profile", ""),
                     capability=capability, title=payload.get("title", ""), ok=True,
                     video_url=result.get("video_url", ""), started=t0,
                     duration_ms=round((time.time() - t0) * 1000),
                     timeline=result.get("timeline", result.get("steps", [])))
        _emit("browser.published", {
            "capability": capability, "title": payload.get("title"),
            "profile": payload.get("profile"), "video_url": result.get("video_url"),
            "steps": result.get("steps", []), "ok": True})
        return result
    except Exception as e:
        store.record(workflow=payload.get("workflow", ""), profile=payload.get("profile", ""),
                     capability=capability, title=payload.get("title", ""), ok=False,
                     error=str(e), started=t0, duration_ms=round((time.time() - t0) * 1000))
        _emit("browser.failed", {"capability": capability, "error": str(e),
                                 "title": payload.get("title"), "ok": False})
        raise
