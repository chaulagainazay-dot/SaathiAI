"""M28 — Compatibility shims for legacy connector managers.

Wrappers call the governed path, emit deprecation evidence, contain no
second transport, and fail closed when governance context is absent.
"""
from __future__ import annotations

import time
from typing import Any, Optional

from saathi.connectors.gov.gateway_bridge import emit_deprecation
from saathi.connectors.gov.side_effects import (
    SideEffectClass,
    capability_to_side_effect,
    evaluate_side_effect,
)


def governed_manager_execute(
    account_id: str,
    capability: str,
    params: dict | None = None,
    *,
    mission: str = "",
    store=None,
    caller_id: str = "legacy.manager",
    caller_class: str = "compat",
    actor_id: str = "",
    approval_token: str = "",
) -> dict:
    """Compatibility entry for ``connectors.manager.execute``.

    * Simulated (no live adapter): local metadata-only simulation under
      governance checks; no external side effect. Emits deprecation.
    * Live adapter: blocked unless explicitly routed through full gateway
      with ACTIVE mode and approvals (M28 default: fail closed for live).
    * FINANCIAL / ACCOUNT_CHANGE / PROHIBITED: always blocked.
    """
    from saathi.connectors.catalog import PROVIDERS, capabilities_for
    from saathi.connectors.accounts import default_store

    emit_deprecation(
        legacy_path="saathi.connectors.manager.execute",
        canonical_path="ExecutionGateway→GovernedConnectorRuntime",
        caller_id=caller_id,
        detail=f"capability={capability}",
    )

    st = store or default_store()
    acct = st.get(account_id)
    if not acct:
        return {"ok": False, "error": "account not found", "bypass": False, "governed": True}
    provider = acct["provider"]
    verb = capability.split(".", 1)[-1] if capability else ""
    category = PROVIDERS.get(provider, ("", ""))[0]
    if verb not in capabilities_for(provider):
        return {
            "ok": False,
            "error": f"{provider} has no capability '{verb}' ({category})",
            "bypass": False,
            "governed": True,
        }
    if acct["status"] != "connected":
        return {
            "ok": False,
            "error": f"account status is '{acct['status']}' — reconnect first",
            "bypass": False,
            "governed": True,
        }

    sec = capability_to_side_effect(capability)
    se = evaluate_side_effect(sec, has_approval=bool(approval_token))
    if se.blocked or sec in (
        SideEffectClass.FINANCIAL,
        SideEffectClass.PROHIBITED,
        SideEffectClass.ACCOUNT_CHANGE,
    ):
        return {
            "ok": False,
            "error": se.reason or f"blocked:{sec.value}",
            "mode": "blocked",
            "provider": provider,
            "capability": capability,
            "side_effect_class": sec.value,
            "bypass": False,
            "governed": True,
            "at": time.time(),
        }

    # Live adapters: do not invoke directly — fail closed in M28 unless
    # production ACTIVE path is used via execute_via_gateway (not wired to live
    # SaaS in this milestone).
    from saathi.connectors import manager as mgr
    live = getattr(mgr, "_LIVE_ADAPTERS", {}).get(provider)
    if live is not None and hasattr(live, verb):
        return {
            "ok": False,
            "error": "live_adapter_requires_governed_ACTIVE_path",
            "mode": "blocked",
            "provider": provider,
            "capability": capability,
            "side_effect_class": sec.value,
            "bypass": False,
            "governed": True,
            "deprecation": True,
            "at": time.time(),
        }

    # COMMUNICATION / EXTERNAL_MUTATION: simulation only without approval
    # is allowed as non-side-effect metadata (mode=simulated). Real send blocked
    # without approval when caller asks for live — already blocked above for live.
    # Simulated path: no external SE.
    result = {
        "simulated": True,
        "capability": capability,
        "params_keys": list((params or {}).keys()),
        "side_effect_class": sec.value,
        "governed": True,
    }
    mode = "simulated"
    ok = True

    # Soft approval signal for external/communication (documented)
    if se.requires_approval and not approval_token:
        # Still simulate but mark approval_state for observability
        result["approval_state"] = "not_granted_simulation_only"
    else:
        result["approval_state"] = "not_required" if not se.requires_approval else "granted"

    try:
        st.touch(account_id)
    except Exception:
        pass

    from saathi.connectors.manager import _EVENT  # type: ignore

    evt_type = _EVENT.get(f"{category}.{verb}") or _EVENT.get(capability) or f"{category}.{verb}"
    try:
        from saathi.events.bus import default_bus
        default_bus().emit(
            evt_type,
            source="connector.compat",
            payload={
                "provider": provider,
                "account": account_id,
                "capability": capability,
                "mode": mode,
                "ok": ok,
                "result": result,
                "governed": True,
            },
            project=mission,
            subject=account_id,
        )
    except Exception:
        pass
    if mission:
        try:
            from saathi.missions.store import default_store as m_store
            from saathi.missions.timeline import default_store as tl
            m = m_store().get_by_key(mission) or m_store().get(mission)
            if m:
                tl().record(
                    m["id"],
                    "note",
                    f"Connector(compat): {provider} {capability} ({mode})",
                    detail=f"account {acct['display_name']}",
                )
        except Exception:
            pass

    return {
        "ok": ok,
        "mode": mode,
        "provider": provider,
        "event": evt_type,
        "capability": capability,
        "result": result,
        "at": time.time(),
        "bypass": False,
        "governed": True,
        "side_effect_class": sec.value,
        "deprecation": True,
    }
