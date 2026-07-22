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


def _register_defaults() -> None:
    try:
        from saathi.connectors.adapters.telegram import register as reg_tg
        reg_tg(register_adapter)
    except Exception:
        pass


_register_defaults()


def _rate_ok(account_id: str, capability: str) -> bool:
    # placeholder token-bucket hook — real per-provider limits plug in with the adapter
    return True


def execute(account_id: str, capability: str, params: dict | None = None, *,
            mission: str = "", store=None,
            caller_id: str = "legacy.manager",
            caller_class: str = "compat",
            actor_id: str = "",
            approval_token: str = "") -> dict:
    """Compatibility entry for external actions (M28).

    Routes through ``saathi.connectors.gov.compat.governed_manager_execute`` —
    no second transport. Live adapters fail closed without governed ACTIVE path.
    Simulated catalog capabilities remain metadata-only (no external side effect).
    """
    if not _rate_ok(account_id, capability):
        return {"ok": False, "error": "rate limited", "bypass": False, "governed": True}
    from saathi.connectors.gov.compat import governed_manager_execute
    return governed_manager_execute(
        account_id,
        capability,
        params,
        mission=mission,
        store=store,
        caller_id=caller_id,
        caller_class=caller_class,
        actor_id=actor_id or caller_id,
        approval_token=approval_token,
    )


def provider_health() -> dict:
    """Which providers have a live adapter vs simulated."""
    out = {}
    for p in PROVIDERS:
        out[p] = "live" if p in _LIVE_ADAPTERS else "simulated"
    return out
