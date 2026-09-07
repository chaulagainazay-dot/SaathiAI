"""TRADING-RUNTIME-INSTANCE-WIRING-1 — canonical subsystem instances for the serving process.

Central Command reported INSUFFICIENT_EVIDENCE for market data, provider and
approval. That was never a scheduling defect — a timer over absent instances
produces fresh insufficient evidence — so this resolves the REAL instances the
runtime already owns, and says plainly why when one does not exist.

THE OBJECTIVE IS REAL EVIDENCE, NOT GREEN EVIDENCE. Where a canonical instance
exists it is wired and its true state flows through. Where none exists, the
subsystem reports the actual reason — NOT_CONFIGURED, PUBLIC_FEED_DISABLED —
rather than a fabricated supervisor invented to turn a panel green. A health
surface that lies about being wired is worse than one that admits it is not.

WHAT DISCOVERY FOUND:

  APPROVAL      `default_paper_gov().approvals` — a real process-wide
                ActivationApprovalCenter, the same one governed paper flows use.
                WIRED.

  MARKET DATA   `default_market_observation()` exists but is a VALIDATION service
                ("purpose": "validation_not_trading", fixture-sourced). It is not
                a feed supervisor: no transport, no heartbeat, no last-observation
                clock. Wiring it as market-data health would misrepresent a
                fixture harness as a live feed. NOT WIRED, reason reported.

  PROVIDER      `ProviderExecutionRuntime` owns a `ProviderHealthTracker`, but
                nothing constructs one at process level — only the CLI and an
                external verify path do. There is genuinely no shared tracker to
                observe. Adding a second, monitoring-only tracker would populate
                the UI with the health of an object no request ever touches, so
                it is NOT created. Reason reported instead.

NO AUTHORITY IS ADDED. This resolves references. It starts no connectivity, reads
no credential, creates no provider, expires no approval, and constructs nothing
that could execute.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from saathi.platform.tg.trading_ops import Subsystem


class WiringState(str, Enum):
    """Why a subsystem is or is not observable in this process."""

    WIRED = "WIRED"
    #: No instance exists in this runtime — not an outage, an absence.
    NOT_CONFIGURED = "NOT_CONFIGURED"
    #: An instance exists but is deliberately not started here.
    PUBLIC_FEED_DISABLED = "PUBLIC_FEED_DISABLED"
    #: Present but unusable without an external commercial dependency.
    LICENSE_REQUIRED = "LICENSE_REQUIRED"
    #: Would require credentials no health read may touch.
    AUTH_REQUIRED = "AUTH_REQUIRED"
    #: Resolution itself failed.
    RESOLUTION_FAILED = "RESOLUTION_FAILED"


@dataclass(frozen=True)
class WiredSubsystem:
    subsystem: str
    state: str
    instance: object | None = None
    detail: str | None = None
    #: Which module owns this instance's lifecycle. One owner per subsystem —
    #: naming it is what stops a second singleton appearing later.
    owner: str | None = None

    @property
    def available(self) -> bool:
        return self.state == WiringState.WIRED.value and self.instance is not None


def resolve_guardian() -> WiredSubsystem:
    try:
        from saathi.platform.tg.service import default_tg_service

        svc = default_tg_service()
    except Exception as exc:
        return _failed(Subsystem.GUARDIAN.value, exc)
    return WiredSubsystem(
        subsystem=Subsystem.GUARDIAN.value, state=WiringState.WIRED.value,
        instance=svc, owner="saathi.platform.tg.service.default_tg_service",
        detail="guardian posture read from the process-wide service",
    )


def resolve_kill_switch() -> WiredSubsystem:
    """The kill switch belongs to the Guardian service — one owner, not two."""
    g = resolve_guardian()
    if not g.available:
        return WiredSubsystem(subsystem=Subsystem.KILL_SWITCH.value, state=g.state,
                              detail=g.detail, owner=g.owner)
    store = getattr(g.instance, "kill_switches", None)
    if store is None:
        return WiredSubsystem(
            subsystem=Subsystem.KILL_SWITCH.value, state=WiringState.NOT_CONFIGURED.value,
            detail="guardian service exposes no kill switch store",
            owner=g.owner,
        )
    return WiredSubsystem(
        subsystem=Subsystem.KILL_SWITCH.value, state=WiringState.WIRED.value,
        instance=store, owner=g.owner,
        detail="kill switch owned by the guardian service",
    )


def resolve_approval() -> WiredSubsystem:
    """The real approval centre governed paper flows use — not a copy.

    Resolved through `default_paper_gov()` so the instance a health read observes
    is the same one an operator decision mutates. A separate monitoring-only
    centre would report on approvals nobody ever grants.
    """
    try:
        from saathi.platform.tg.paper_activation.service import default_paper_gov

        gov = default_paper_gov()
    except Exception as exc:
        return _failed(Subsystem.APPROVAL.value, exc)
    center = getattr(gov, "approvals", None)
    if center is None:
        return WiredSubsystem(
            subsystem=Subsystem.APPROVAL.value, state=WiringState.NOT_CONFIGURED.value,
            detail="paper governance service exposes no approval centre",
            owner="saathi.platform.tg.paper_activation.service.default_paper_gov",
        )
    return WiredSubsystem(
        subsystem=Subsystem.APPROVAL.value, state=WiringState.WIRED.value,
        instance=center,
        owner="saathi.platform.tg.paper_activation.service.default_paper_gov",
        detail="canonical approval centre shared with governed paper flows",
    )


def resolve_provider() -> WiredSubsystem:
    """The public market-data runtime owns the canonical provider tracker.

    PUBLIC-MARKET-DATA-SUPERVISOR-1 supplied the process-wide instance this
    previously reported as absent — and it is the tracker the runtime itself
    updates from real transport events, not a monitoring-only copy. When the
    runtime is switched off there is still nothing to observe, and that is
    reported rather than papered over.

    SCOPE IS PUBLIC MARKET DATA. A healthy provider here says nothing about a
    trading account, and the capability travels with the health to keep the two
    from being read as one claim.
    """
    try:
        from saathi.platform.crypto.runtime import (
            PROVIDER_ID, RuntimeState, default_public_market_data,
        )

        rt = default_public_market_data()
    except Exception as exc:
        return _failed(Subsystem.PROVIDER.value, exc)

    owner = "saathi.platform.crypto.runtime.default_public_market_data"
    if rt.state is RuntimeState.DISABLED:
        return WiredSubsystem(
            subsystem=Subsystem.PROVIDER.value,
            state=WiringState.NOT_CONFIGURED.value,
            detail="public market-data runtime is disabled; no provider is being observed",
            owner=owner,
        )
    return WiredSubsystem(
        subsystem=Subsystem.PROVIDER.value, state=WiringState.WIRED.value,
        instance=rt.health, owner=owner,
        detail=f"canonical provider tracker owned by the public market-data runtime ({PROVIDER_ID})",
    )


def resolve_market_data() -> WiredSubsystem:
    """The certified public Binance runtime, when it is switched on.

    `market_observation` is deliberately still NOT used as feed health: it is a
    fixture-sourced validation harness with no transport, heartbeat or
    last-observation clock, and presenting it as a feed would be the false-live
    label this program forbids. The real supervisor is
    PUBLIC-MARKET-DATA-SUPERVISOR-1's runtime, which is off by default.
    """
    try:
        from saathi.platform.crypto.runtime import RuntimeState, default_public_market_data

        rt = default_public_market_data()
    except Exception as exc:
        return _failed(Subsystem.MARKET_DATA.value, exc)

    owner = "saathi.platform.crypto.runtime.default_public_market_data"
    if rt.state is RuntimeState.DISABLED:
        return WiredSubsystem(
            subsystem=Subsystem.MARKET_DATA.value,
            state=WiringState.PUBLIC_FEED_DISABLED.value,
            detail=("public market-data runtime is disabled; no live public feed "
                    "is running in this process"),
            owner=owner,
        )
    return WiredSubsystem(
        subsystem=Subsystem.MARKET_DATA.value, state=WiringState.WIRED.value,
        instance=rt, owner=owner,
        detail="live public Binance spot market data (public endpoints only)",
    )


def resolve_execution_gateway() -> WiredSubsystem:
    """Gateway posture from the Guardian service's own declaration.

    Guardian already publishes the gateway-relevant configuration — paper_only,
    live_order_capable, require_approval — as verified read-only facts. Reading
    it there is how gateway health gets REAL evidence without exercising the
    gateway, which has no side-effect-free "how are you" method of its own.
    """
    g = resolve_guardian()
    if not g.available:
        return WiredSubsystem(subsystem=Subsystem.EXECUTION_GATEWAY.value,
                              state=g.state, detail=g.detail, owner=g.owner)
    try:
        posture = g.instance.posture()
    except Exception as exc:
        return _failed(Subsystem.EXECUTION_GATEWAY.value, exc)
    return WiredSubsystem(
        subsystem=Subsystem.EXECUTION_GATEWAY.value, state=WiringState.WIRED.value,
        instance={
            # The gateway exists and is reachable; live execution is off by
            # policy, which is a CAPABILITY not a fault.
            "gateway_available": True,
            "live_execution_enabled": bool(posture.get("live_order_capable")),
            "paper_ready": bool(posture.get("paper_only", True)),
            "approval_required": bool(posture.get("require_approval", True)),
        },
        owner=g.owner,
        detail="gateway posture declared by the guardian service",
    )


def _failed(subsystem: str, exc: BaseException) -> WiredSubsystem:
    return WiredSubsystem(
        subsystem=subsystem, state=WiringState.RESOLUTION_FAILED.value,
        detail=f"{type(exc).__name__}: {exc}"[:200],
    )


def resolve_all() -> dict:
    """Every subsystem's wiring, resolved once."""
    return {w.subsystem: w for w in (
        resolve_market_data(), resolve_provider(), resolve_guardian(),
        resolve_kill_switch(), resolve_approval(), resolve_execution_gateway(),
    )}


def collector_sources(wiring: dict | None = None) -> dict:
    """Keyword arguments for `collect_trading_health`, from resolved instances.

    Only WIRED subsystems contribute a source. An unwired one contributes
    nothing, so the collector reaches its own insufficient-evidence path rather
    than being handed a stand-in.
    """
    w = wiring if wiring is not None else resolve_all()
    out: dict = {}
    if w[Subsystem.GUARDIAN.value].available:
        out["guardian_service"] = w[Subsystem.GUARDIAN.value].instance
    if w[Subsystem.KILL_SWITCH.value].available:
        out["kill_switch_store"] = w[Subsystem.KILL_SWITCH.value].instance
    if w[Subsystem.APPROVAL.value].available:
        out["approval_center"] = w[Subsystem.APPROVAL.value].instance
    if w[Subsystem.MARKET_DATA.value].available:
        out["market_data_source"] = w[Subsystem.MARKET_DATA.value].instance
    if w[Subsystem.PROVIDER.value].available:
        out["provider_tracker"] = w[Subsystem.PROVIDER.value].instance
        from saathi.platform.crypto.runtime import PROVIDER_ID

        # Named explicitly: the collector never enumerates providers by asking
        # for ones it was not told about, which is how `get` would create them.
        out["provider_ids"] = (PROVIDER_ID,)
    gw = w.get(Subsystem.EXECUTION_GATEWAY.value)
    if gw is not None and gw.available:
        out["gateway"] = gw.instance
    return out


def unavailable_reasons(wiring: dict | None = None) -> dict:
    """Per-subsystem reason text for anything not wired here.

    Handed to the collector so a panel says "no live public feed supervisor in
    this process" rather than a bare "insufficient evidence" — a wiring gap and
    a subsystem fault are different problems and must not read the same.
    """
    w = wiring if wiring is not None else resolve_all()
    return {k: f"{v.state}: {v.detail}" for k, v in w.items()
            if not v.available and v.detail}


def wiring_report(wiring: dict | None = None) -> dict:
    """Serialisable wiring state for the status payload.

    Carried alongside health so an operator can tell "this subsystem is
    unhealthy" from "this subsystem is not wired here" — two facts a single
    UNKNOWN would merge.
    """
    w = wiring if wiring is not None else resolve_all()
    return {
        k: {"state": v.state, "detail": v.detail, "owner": v.owner,
            "available": v.available}
        for k, v in sorted(w.items())
    }
