"""Map owner-authenticated browser observations → frozen PortfolioSnapshot, and answer
chat/voice from the snapshot. Read-only; source = OWNER_AUTHENTICATED_BROWSER_OBSERVED.
Account values are browser-displayed (explicitly NOT canonical exchange data); higher-
authority market price is applied where legitimately available.
"""
from __future__ import annotations

import re
import time
import uuid
from decimal import Decimal

from saathi.platform.finance.portfolio import (
    Position, PortfolioSnapshot, PortfolioSourceType, PortfolioFreshness, dec,
)

DATA_CLASS = "OWNER_AUTHENTICATED_BROWSER_OBSERVATION"


def _instrument(provider: str, sym: str) -> tuple[str, str]:
    s = (sym or "").strip().upper()
    if provider == "TMS":
        try:
            from saathi.platform.nepse.instruments import instrument_id_for
            return instrument_id_for(s), "EQUITY"
        except Exception:
            return "", "EQUITY"
    # BINANCE
    stable = s in {"USDT", "USDC", "FDUSD", "DAI", "TUSD", "BUSD", "USDP", "PYUSD"}
    return f"BINANCE:{s}", ("STABLECOIN" if stable else "CRYPTO")


def build_snapshot(provider: str, rows: list[dict], *, owner_id: str = "owner",
                   now: float | None = None) -> PortfolioSnapshot:
    now = now if now is not None else time.time()
    provider = provider.upper()
    ccy = "NPR" if provider == "TMS" else "USDT"
    positions = []
    for r in rows:
        sym = r.get("symbol") or r.get("asset") or ""
        if not sym:
            continue
        inst, atype = _instrument(provider, sym)
        qty = dec(r.get("quantity"))
        avail = dec(r.get("available"))
        locked = dec(r.get("locked"))
        disp = dec(r.get("displayed_value"))
        positions.append(Position(
            instrument_id=inst, symbol=str(sym).upper(), asset_type=atype,
            quantity=qty, available_quantity=avail, locked_quantity=locked,
            average_cost=dec(r.get("wacc")), current_price=None,
            current_price_source="BROWSER_DISPLAYED" if disp is not None else "",
            market_value=disp,                          # browser-displayed value (not canonical)
            cost_basis=None, unrealized_pnl=dec(r.get("pnl")), realized_pnl=None,
            currency=ccy, source=f"{provider}_BROWSER", observed_at=now))
    total = sum((p.market_value for p in positions if p.market_value is not None), Decimal(0))
    lims = ["OWNER_AUTHENTICATED_BROWSER_OBSERVED",
            "account values are browser-displayed, not canonical exchange data"]
    if provider == "BINANCE":
        lims.append("apply Binance public market price where legitimately reachable")
    if provider == "TMS":
        lims.append("current price authority = Official NEPSE pipeline; WACC/qty from broker page")
    return PortfolioSnapshot(
        snapshot_id=f"obs_{uuid.uuid4().hex[:12]}", owner_id=owner_id, provider=provider,
        account_type=("NEPSE_DEMAT" if provider == "TMS" else "CRYPTO"), observed_at=now,
        currency=ccy, source_type=PortfolioSourceType.OWNER_AUTHENTICATED_BROWSER_OBSERVED,
        data_class=DATA_CLASS, source_authority="OWNER_ACCOUNT_BROWSER",
        freshness=PortfolioFreshness.FRESH, positions=tuple(positions),
        total_market_value=total if positions else None, limitations=tuple(lims))


def portfolio_view(snap: PortfolioSnapshot) -> dict:
    from saathi.platform.finance.portfolio import snapshot_metrics
    m = snapshot_metrics(snap)
    return {"provider": snap.provider, "currency": snap.currency, "asset_count": len(snap.positions),
            "total_value": None if snap.total_market_value is None else str(snap.total_market_value),
            "allocation": m["allocation"], "largest_position": m["largest_position"],
            "top_concentration_pct": m["top_concentration_pct"],
            "source": "OWNER_AUTHENTICATED_BROWSER_OBSERVED", "data_class": snap.data_class,
            "cost_basis": "COST_BASIS_UNAVAILABLE", "pnl": "PNL_UNAVAILABLE",
            "positions": [p.to_public() for p in snap.positions], "limitations": list(snap.limitations)}


def chat_answer(query: str, *, view: dict | None = None) -> dict:
    q = (query or "").lower()
    if view is None:
        return {"answer": "Not connected. Open the provider in the Financial Browser, log in "
                          "yourself, then enable Saathi Read.", "source": None,
                "state": "OWNER_FINANCIAL_LOGIN_REQUIRED"}
    src = f"{view['provider']} owner-authenticated browser (read-only)"
    if any(w in q for w in ("profit", "p/l", "pnl", "gain", "loss")):
        return {"answer": "P/L unavailable from the read-only browser observation "
                          "(PNL_UNAVAILABLE).", "source": src}
    if "largest" in q or "biggest" in q:
        lp = view.get("largest_position")
        return {"answer": (f"Largest: {lp['symbol']} at {lp['weight_pct']}%." if lp else "No positions."),
                "source": src}
    if "worth" in q or "total" in q or "value" in q:
        return {"answer": f"{view['provider']} portfolio ≈ {view['total_value']} {view['currency']} "
                          f"across {view['asset_count']} holdings. Source: {src}.", "source": src}
    for tok in re.findall(r"[A-Za-z0-9]{2,10}", query or ""):
        row = next((p for p in view["positions"] if p["symbol"] == tok.upper()), None)
        if row:
            return {"answer": f"You hold {row['quantity']} {row['symbol']} "
                              f"(value {row['market_value']} {view['currency']}). Source: {src}.",
                    "source": src}
    return {"answer": f"{view['provider']} portfolio: {view['asset_count']} holdings ≈ "
                      f"{view['total_value']} {view['currency']}. Source: {src}.", "source": src}


def voice_answer(query: str, *, view: dict | None = None) -> str:
    return chat_answer(query, view=view).get("answer", "")


def _official_ltp(symbol: str):
    """Official NEPSE current LTP for a symbol (authority for current price), or None."""
    try:
        from saathi.platform.market_data.nepse_live_service import get_default_service
        snap = get_default_service().snapshot()
        if snap is None:
            return None
        o = snap.get(symbol)
        return o.ltp if o else None
    except Exception:
        return None


def enrich_with_official(snap: PortfolioSnapshot) -> tuple[PortfolioSnapshot, list[dict]]:
    """For a TMS/NEPSE snapshot, set current price from the Official NEPSE pipeline (authority)
    and reconcile against any TMS-displayed value. Never overwrites the account holding."""
    from dataclasses import replace as _replace
    recon = []
    new_pos = []
    for p in snap.positions:
        official = _official_ltp(p.symbol) if snap.provider == "TMS" else None
        tms_implied = None
        if p.market_value is not None and p.quantity not in (None, Decimal(0)):
            try:
                tms_implied = (p.market_value / p.quantity)
            except Exception:
                tms_implied = None
        if official is not None:
            verdict = "OFFICIAL_UNAVAILABLE" if tms_implied is None else (
                "CONFIRMED" if abs(official - tms_implied) <= official * Decimal("0.01")
                else "SOURCE_DISAGREEMENT")
            mv = official * p.quantity if p.quantity is not None else p.market_value
            new_pos.append(_replace(p, current_price=official,
                                    current_price_source="OFFICIAL_PAGE_OBSERVED", market_value=mv))
        else:
            verdict = "OFFICIAL_UNAVAILABLE"
            new_pos.append(p)
        recon.append({"symbol": p.symbol, "official_ltp": None if official is None else str(official),
                      "tms_implied_ltp": None if tms_implied is None else str(tms_implied),
                      "verdict": verdict})
    total = sum((x.market_value for x in new_pos if x.market_value is not None), Decimal(0))
    return _replace(snap, positions=tuple(new_pos),
                    total_market_value=total if new_pos else None), recon


def read_portfolio(runtime_id: str, *, manager=None, reader=None, enrich: bool = True) -> dict:
    """One deterministic read-only observation of the owner-authenticated page → snapshot.
    Read-only; no clicks/navigation. Returns typed states, never fabricated data."""
    from saathi.platform.finance.browser_runtime import get_runtime_manager, AuthState
    from saathi.platform.finance.observer import ReadOnlyPageReader, get_observer
    m = manager or get_runtime_manager()
    rt = m.get(runtime_id)
    if rt is None:
        return {"available": False, "state": "NO_RUNTIME"}
    if rt.auth_state != AuthState.OWNER_AUTHENTICATED:
        return {"available": False, "state": "OWNER_TMS_LOGIN_REQUIRED"}
    if not m.read_allowed(runtime_id):
        return {"available": False, "state": "SAATHI_READ_OFF"}
    if reader is None:
        page = m.live_page(rt.provider)
        if page is None:
            return {"available": False, "state": "OWNER_TMS_PORTFOLIO_PAGE_REQUIRED"}
        reader = ReadOnlyPageReader(page)
    obs = get_observer(rt.provider.value)
    if obs is None:
        return {"available": False, "state": "NO_OBSERVER"}
    if obs.authentication_state(reader) != AuthState.OWNER_AUTHENTICATED:
        return {"available": False, "state": "TMS_AUTH_STATE_UNKNOWN"}
    rows, lims = obs.observe_portfolio(reader)
    if not rows:
        # distinguish empty vs failure: an authenticated page with a container but no rows =
        # EMPTY_PORTFOLIO; missing container/selectors = SCHEMA_CHANGED
        state = "EMPTY_PORTFOLIO" if obs.SELECTORS_VERIFIED else "SCHEMA_CHANGED_OR_UNVERIFIED"
        return {"available": False, "state": state, "limitations": lims}
    snap = build_snapshot(rt.provider.value, rows)
    recon = []
    if enrich and rt.provider.value == "TMS":
        snap, recon = enrich_with_official(snap)
    view = portfolio_view(snap)
    view["reconciliation"] = recon
    view["selectors_verified"] = obs.SELECTORS_VERIFIED
    return {"available": True, "state": "OK", "view": view, "limitations": lims}
