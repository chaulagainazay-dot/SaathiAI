"""Unified infrastructure diagnostics + health score (Audit 11 / Step 5).

One snapshot the CEO dashboard consumes as the platform's "engine warning light":

    Models · Browser · Connectors · Conversation  →  🟢🟡🔴 + latency + a % score

Every component already exposes health, so this is aggregation, not new probing.
"""
from __future__ import annotations


def snapshot(registry=None, engine=None, voice=None) -> dict:
    from .connectors import diagnostics as cdiag
    from .connectors import default_registry
    from .conversation import diagnostics as convdiag

    reg = registry or default_registry()
    models = cdiag.model_router_section()
    browser = cdiag.browser_section()
    connectors = reg.diagnostics()                 # per-connector: status/light/latency_ms/…
    conversation = convdiag.snapshot(engine=engine, voice=voice)
    return {
        "models": models,
        "browser": browser,
        "connectors": connectors,
        "conversation": conversation,
        "score": health_score(models, browser, connectors, conversation),
    }


def _pct(items, pred) -> int:
    items = list(items)
    return round(100 * sum(1 for i in items if pred(i)) / len(items)) if items else 100


# HTTP is essential; the JS/anti-detect tiers are graded but optional.
_BROWSER_WEIGHTS = {"http": 0.6, "playwright": 0.2, "camofox": 0.2}


def health_score(models, browser, connectors, conversation) -> dict:
    models_s = _pct(models, lambda m: m.get("available"))
    browser_s = round(100 * sum(_BROWSER_WEIGHTS.get(b["id"], 0)
                                for b in browser if b.get("available")))
    conn_s = _pct(connectors, lambda c: c.get("status") in ("ok", "degraded"))
    voice_s = 100 if conversation.get("voice", {}).get("available") else 0
    overall = round((models_s + browser_s + conn_s + voice_s) / 4)
    return {"overall": overall, "models": models_s, "browser": browser_s,
            "connectors": conn_s, "voice": voice_s}
