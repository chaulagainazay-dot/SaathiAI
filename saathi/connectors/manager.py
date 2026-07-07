"""Connector Manager — every external action goes through here.

Directors/Missions/Workflows call `execute(account_id, "email.send", params)`. The
manager resolves the account, checks the capability is valid for the provider,
dispatches to the provider ADAPTER, emits an event onto the Event Bus (→ Evidence →
Learning → Mission Timeline), and returns a normalised result. No caller ever touches
a provider SDK. Adapters are the only place real OAuth/API calls live; until an
adapter is wired for a provider it runs in SIMULATED mode — honest, never pretends
an API call happened.
"""
from __future__ import annotations

import time

from saathi.connectors.catalog import PROVIDERS, capabilities_for

# capability → emitted event type (what lands in Evidence)
_EVENT = {
    "email.send": "email.sent", "email.reply": "email.replied", "email.draft": "email.drafted",
    "social.post": "social.posted", "social.schedule": "social.scheduled",
    "video.upload": "youtube.uploaded", "drive.upload": "drive.file_uploaded",
    "calendar.create_event": "meeting.created", "docs.create": "document.created",
    "payments.charge": "payment.charged",
}

# adapters that are actually wired (real API). Everything else runs simulated.
_LIVE_ADAPTERS: dict[str, object] = {}   # provider → adapter instance (register when built)


def register_adapter(provider: str, adapter) -> None:
    _LIVE_ADAPTERS[provider] = adapter


def _rate_ok(account_id: str, capability: str) -> bool:
    # placeholder token-bucket hook — real per-provider limits plug in with the adapter
    return True


def execute(account_id: str, capability: str, params: dict | None = None, *,
            mission: str = "", store=None) -> dict:
    """The single entry point for any external action."""
    from saathi.connectors.accounts import default_store
    st = store or default_store()
    acct = st.get(account_id)
    if not acct:
        return {"ok": False, "error": "account not found"}
    provider = acct["provider"]
    verb = capability.split(".", 1)[-1]
    category = PROVIDERS.get(provider, ("", ""))[0]
    if verb not in capabilities_for(provider):
        return {"ok": False, "error": f"{provider} has no capability '{verb}' ({category})"}
    if acct["status"] != "connected":
        return {"ok": False, "error": f"account status is '{acct['status']}' — reconnect first"}
    if not _rate_ok(account_id, capability):
        return {"ok": False, "error": "rate limited"}

    adapter = _LIVE_ADAPTERS.get(provider)
    try:
        if adapter and hasattr(adapter, verb):
            result = getattr(adapter, verb)(acct, params or {})
            mode = "live"
        else:
            result = {"simulated": True, "capability": capability, "params_keys": list((params or {}).keys())}
            mode = "simulated"
    except Exception as e:
        result = {"error": str(e)[:150]}
        mode = "error"

    st.touch(account_id)
    ok = mode != "error"

    # emit the event → Event Bus routes it into Evidence + Mission Timeline
    evt_type = _EVENT.get(f"{category}.{verb}") or _EVENT.get(capability) or f"{category}.{verb}"
    try:
        from saathi.events.bus import default_bus
        default_bus().emit(evt_type, source="connector",
                           payload={"provider": provider, "account": account_id, "capability": capability,
                                    "mode": mode, "ok": ok, "result": result},
                           project=mission, subject=account_id)
    except Exception:
        pass
    if mission:
        try:
            from saathi.missions.store import default_store as m_store
            from saathi.missions.timeline import default_store as tl
            m = m_store().get_by_key(mission) or m_store().get(mission)
            if m:
                tl().record(m["id"], "note", f"Connector: {provider} {capability} ({mode})",
                            detail=f"account {acct['display_name']}")
        except Exception:
            pass

    return {"ok": ok, "mode": mode, "provider": provider, "event": evt_type,
            "capability": capability, "result": result, "at": time.time()}


def provider_health() -> dict:
    """Which providers have a live adapter vs simulated."""
    out = {}
    for p in PROVIDERS:
        out[p] = "live" if p in _LIVE_ADAPTERS else "simulated"
    return out
