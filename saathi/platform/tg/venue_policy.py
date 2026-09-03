"""Per-venue Guardian policy module (TRADING-GUARDIAN-V2).

The single Trading Guardian remains the final pre-approval/execution safety
boundary. This module lets crypto and NEPSE carry *different venue policy* under
that one Guardian, without a second Guardian or any candidate-status bypass:

  * a venue can be independently disabled (maintenance, license gap, incident);
  * a session-bound venue (NEPSE) is blocked when its session is not open, and
    fails CLOSED when session state is unknown;
  * crypto is 24/7 so session is not applicable.

Deterministic and side-effect free. Returns a gate result; it does not execute,
approve, or size. A PAPER_CANDIDATE strategy with a valid construction and a
passing risk decision can STILL be blocked here for an independent venue reason —
that is the point.
"""
from __future__ import annotations

from saathi.platform.tg.paper_simulation.conventions import AssetClass, convention_for


# Asset class -> canonical venue identifier used by Guardian venue policy.
_VENUE_BY_ASSET = {
    AssetClass.CRYPTO: "CRYPTO",
    AssetClass.NEPSE_EQUITY: "NEPSE",
    AssetClass.EQUITY: "SIM",
}


def venue_for(symbol: str) -> str:
    """Stable venue id for a symbol (mirrors the convention/calendar routing)."""
    return _VENUE_BY_ASSET[convention_for(symbol).asset_class]


def session_required(symbol: str) -> bool:
    """Session gating applies to session-bound venues only (not 24/7 crypto)."""
    return not convention_for(symbol).is_247


def evaluate_venue(
    symbol: str,
    *,
    disabled_venues=(),
    require_session: bool | None = None,
    session_open: bool | None = None,
) -> dict:
    """Deterministic venue gate.

    Returns {venue, ok, reason, explanation, evidence}. Fail-closed when a
    session-bound venue's session state is unknown.
    """
    venue = venue_for(symbol)
    disabled = {str(v).upper() for v in (disabled_venues or ())}
    evidence = {"symbol": str(symbol).upper(), "venue": venue}

    if venue in disabled:
        return {
            "venue": venue,
            "ok": False,
            "reason": "VENUE_DISABLED",
            "explanation": f"venue {venue} is administratively disabled",
            "evidence": {**evidence, "disabled_venues": sorted(disabled)},
        }

    needs_session = session_required(symbol) if require_session is None else bool(require_session)
    if needs_session:
        if session_open is None:
            return {
                "venue": venue,
                "ok": False,
                "reason": "VENUE_SESSION_UNKNOWN",
                "explanation": f"venue {venue} session state unknown — fail closed",
                "evidence": {**evidence, "session_open": None},
            }
        if session_open is False:
            return {
                "venue": venue,
                "ok": False,
                "reason": "VENUE_SESSION_CLOSED",
                "explanation": f"venue {venue} session is closed",
                "evidence": {**evidence, "session_open": False},
            }

    return {
        "venue": venue,
        "ok": True,
        "reason": "OK",
        "explanation": f"venue {venue} enabled",
        "evidence": {**evidence, "session_open": session_open},
    }
