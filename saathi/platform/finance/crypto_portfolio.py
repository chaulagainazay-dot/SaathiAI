"""Binance crypto portfolio: snapshot builder, CryptoPortfolioView, connection manager,
chat/voice. Read-only, deterministic, no P/L fabrication, no trade semantics.
"""
from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum

from saathi.platform.finance import audit
from saathi.platform.finance.binance_account import (
    STABLECOINS, VALUATION_CCY, DUST_THRESHOLD, BinanceHealth, BinanceReadOnlyAccountAdapter,
    PermissionAssessment, is_safe,
)
from saathi.platform.finance.portfolio import (
    Position, PortfolioSnapshot, PortfolioSourceType, PortfolioFreshness, dec,
)

CACHE_TTL_SEC = 60.0


class ConnectionState(str, Enum):
    NOT_CONNECTED = "NOT_CONNECTED"
    OWNER_ACTION_REQUIRED = "OWNER_ACTION_REQUIRED"
    VERIFYING = "VERIFYING"
    READ_ONLY_CONNECTED = "READ_ONLY_CONNECTED"
    PERMISSION_UNSAFE = "PERMISSION_UNSAFE"
    AUTH_FAILED = "AUTH_FAILED"
    RATE_LIMITED = "RATE_LIMITED"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    STALE = "STALE"


def _asset_type(asset: str) -> str:
    return "STABLECOIN" if asset.upper() in STABLECOINS else "CRYPTO"


def _price_for(adapter: BinanceReadOnlyAccountAdapter, asset: str) -> Decimal | None:
    a = asset.upper()
    if a == VALUATION_CCY:
        return Decimal(1)
    return adapter.price(f"{a}{VALUATION_CCY}")     # real quote; stablecoins NOT assumed 1:1


def build_snapshot(adapter: BinanceReadOnlyAccountAdapter, *, owner_id: str = "owner",
                   now: float | None = None) -> tuple[PortfolioSnapshot | None, ConnectionState]:
    now = now if now is not None else time.time()
    assessment = adapter.assess()
    if not is_safe(assessment):
        audit.record(provider="BINANCE", actor="AGENT_INPUT", capability="BINANCE_ACCOUNT_READ",
                     result="BLOCKED", detail=assessment.value)
        state = (ConnectionState.PERMISSION_UNSAFE
                 if assessment.value.startswith("UNSAFE") else ConnectionState.AUTH_FAILED)
        return None, state
    try:
        bals = adapter.balances()
    except Exception as e:
        audit.record(provider="BINANCE", actor="AGENT_INPUT", capability="BINANCE_ACCOUNT_READ",
                     result="ERROR", detail=type(e).__name__)
        return None, ConnectionState.PROVIDER_UNAVAILABLE
    positions: list[Position] = []
    unpriced = dust = 0
    for b in bals:
        free = dec(b.get("free")) or Decimal(0)
        locked = dec(b.get("locked")) or Decimal(0)
        qty = free + locked
        if qty <= 0:
            continue                                 # zero-balance filtered (Phase 9)
        asset = str(b.get("asset", "")).upper()
        price = _price_for(adapter, asset)
        mv = (qty * price) if price is not None else None
        if price is None:
            unpriced += 1
        elif mv is not None and mv < DUST_THRESHOLD:
            dust += 1
        positions.append(Position(
            instrument_id=f"BINANCE:{asset}", symbol=asset, asset_type=_asset_type(asset),
            quantity=qty, available_quantity=free, locked_quantity=locked,
            current_price=price, current_price_source="BINANCE_PUBLIC", market_value=mv,
            average_cost=None, cost_basis=None, unrealized_pnl=None, realized_pnl=None,
            currency=VALUATION_CCY, source="BINANCE", observed_at=now))
    total = sum((p.market_value for p in positions if p.market_value is not None), Decimal(0))
    lims = ["COST_BASIS_UNAVAILABLE", "PNL_UNAVAILABLE"]
    if unpriced:
        lims.append(f"{unpriced} asset(s) PRICE_UNAVAILABLE")
    if dust:
        lims.append(f"{dust} dust asset(s) (<{DUST_THRESHOLD} {VALUATION_CCY}) retained")
    snap = PortfolioSnapshot(
        snapshot_id=f"bpf_{uuid.uuid4().hex[:12]}", owner_id=owner_id, provider="BINANCE",
        account_type="CRYPTO", observed_at=now, currency=VALUATION_CCY,
        source_type=PortfolioSourceType.READ_ONLY_API_ACCOUNT_DATA,
        data_class="READ_ONLY_ACCOUNT_OBSERVATION", source_authority="BINANCE_READONLY_API",
        freshness=PortfolioFreshness.FRESH, positions=tuple(positions),
        total_market_value=total if positions else None, limitations=tuple(lims))
    audit.record(provider="BINANCE", actor="AGENT_INPUT", capability="BINANCE_ACCOUNT_READ",
                 result="OK", detail=f"assets={len(positions)} priced={len(positions)-unpriced}")
    return snap, ConnectionState.READ_ONLY_CONNECTED


def crypto_view(snap: PortfolioSnapshot) -> dict:
    """CryptoPortfolioView — descriptive only, no recommendation."""
    total = snap.total_market_value or Decimal(0)

    def pct(v):
        return str((v / total * 100).quantize(Decimal("0.01"))) if total and v is not None else None
    rows = []
    stable = crypto = locked_val = Decimal(0)
    for p in sorted(snap.positions, key=lambda x: (x.market_value or Decimal(0)), reverse=True):
        mv = p.market_value or Decimal(0)
        if p.asset_type == "STABLECOIN":
            stable += mv
        else:
            crypto += mv
        if p.locked_quantity and p.current_price:
            locked_val += p.locked_quantity * p.current_price
        rows.append({"asset": p.symbol, "asset_type": p.asset_type,
                     "quantity": str(p.quantity), "available": str(p.available_quantity),
                     "locked": str(p.locked_quantity), "price": (None if p.current_price is None else str(p.current_price)),
                     "market_value": (None if p.market_value is None else str(p.market_value)),
                     "allocation_pct": pct(p.market_value), "source": "BINANCE + BINANCE_PUBLIC"})
    return {"provider": "BINANCE", "valuation_currency": VALUATION_CCY,
            "total_value": str(total) if snap.positions else None, "asset_count": len(snap.positions),
            "largest_position": rows[0] if rows else None,
            "stablecoin_allocation_pct": pct(stable), "crypto_allocation_pct": pct(crypto),
            "locked_allocation_pct": pct(locked_val), "positions": rows,
            "cost_basis": "COST_BASIS_UNAVAILABLE", "pnl": "PNL_UNAVAILABLE",
            "source_authority": snap.source_authority, "data_class": snap.data_class,
            "freshness": snap.freshness.value, "observed_at": snap.observed_at,
            "note": "descriptive read-only account observation; not investment advice",
            "limitations": list(snap.limitations)}


# ── connection manager (state + bounded cache + kill/disconnect) ────────────────
@dataclass
class BinanceConnection:
    adapter: BinanceReadOnlyAccountAdapter | None = None
    state: ConnectionState = ConnectionState.NOT_CONNECTED
    _snap: PortfolioSnapshot | None = None
    _snap_at: float = 0.0

    def snapshot(self, *, force: bool = False, now: float | None = None):
        now = now if now is not None else time.time()
        if self.adapter is None:
            self.state = ConnectionState.OWNER_ACTION_REQUIRED
            return None, self.state
        if not force and self._snap is not None and (now - self._snap_at) < CACHE_TTL_SEC:
            return self._snap, self.state              # one read → many consumers
        snap, st = build_snapshot(self.adapter, now=now)
        self.state = st
        if snap is not None:
            self._snap, self._snap_at = snap, now
        return snap, st

    def disconnect(self) -> None:
        self.adapter = None
        self._snap = None
        self.state = ConnectionState.NOT_CONNECTED
        audit.record(provider="BINANCE", actor="OWNER_INPUT", capability="DISCONNECT", result="OK")

    def kill(self) -> None:
        # revoke agent read capability + clear ephemeral snapshot; secret NOT deleted here
        self._snap = None
        self.adapter = None
        self.state = ConnectionState.NOT_CONNECTED
        audit.record(provider="BINANCE", actor="OWNER_INPUT", capability="KILL_SWITCH", result="OK")


_CONN: BinanceConnection | None = None


def get_connection() -> BinanceConnection:
    global _CONN
    if _CONN is None:
        _CONN = BinanceConnection()
        _CONN.adapter = _configure_from_env()
        _CONN.state = (ConnectionState.NOT_CONNECTED if _CONN.adapter
                       else ConnectionState.OWNER_ACTION_REQUIRED)
    return _CONN


def _configure_from_env():
    """Build an adapter from owner-configured secret REFERENCES (env-backed). Returns None
    if the owner has not configured them — the agent is never asked for the secret."""
    import os
    from saathi.connectors.platform.credentials import CredentialRef, SecretBackend
    if not (os.getenv("BINANCE_API_KEY") and os.getenv("BINANCE_API_SECRET")):
        return None
    key_ref = CredentialRef(ref_id="binance_key", connector_id="binance", scope="owner",
                            backend=SecretBackend.ENV.value, backend_key="BINANCE_API_KEY")
    sec_ref = CredentialRef(ref_id="binance_secret", connector_id="binance", scope="owner",
                            backend=SecretBackend.ENV.value, backend_key="BINANCE_API_SECRET")
    return BinanceReadOnlyAccountAdapter(key_ref=key_ref, secret_ref=sec_ref)


# ── chat / voice (same snapshot; deterministic; P/L honestly unavailable) ───────
def chat_answer(query: str, *, view: dict | None = None) -> dict:
    q = (query or "").lower()
    src = "Binance read-only account (BINANCE_READONLY_API) + BINANCE_PUBLIC prices"
    if view is None:
        return {"answer": "Binance portfolio not connected. Owner must configure a read-only "
                          "API key via the SaathiOS secret store (never in chat).",
                "source": None, "state": "OWNER_ACTION_REQUIRED"}
    if "profit" in q or "p/l" in q or "pnl" in q or "gain" in q or "loss" in q:
        return {"answer": "Cost basis and P/L are unavailable from the certified read-only "
                          "source (Binance balances expose no cost basis). "
                          "COST_BASIS_UNAVAILABLE / PNL_UNAVAILABLE.", "source": src}
    if "stablecoin" in q or "stable coin" in q:
        return {"answer": f"Stablecoins are {view['stablecoin_allocation_pct']}% of the crypto "
                          f"portfolio. Source: {src}.", "source": src}
    if "largest" in q or "biggest" in q:
        lp = view.get("largest_position")
        return {"answer": (f"Largest position: {lp['asset']} at {lp['allocation_pct']}% "
                           f"({lp['market_value']} {view['valuation_currency']})." if lp else
                           "No positions."), "source": src}
    if "worth" in q or "total" in q or "value" in q:
        return {"answer": f"Binance portfolio value ≈ {view['total_value']} {view['valuation_currency']} "
                          f"across {view['asset_count']} assets. Source: {src}.", "source": src}
    # per-asset (BTC/ETH/USDT/…): quantity + % if named. Map common names → symbols.
    _ALIAS = {"BITCOIN": "BTC", "ETHEREUM": "ETH", "ETHER": "ETH", "TETHER": "USDT",
              "BINANCECOIN": "BNB", "SOLANA": "SOL"}
    for tok in re.findall(r"[A-Za-z0-9]{2,10}", query or ""):
        t = _ALIAS.get(tok.upper(), tok.upper())
        row = next((r for r in view["positions"] if r["asset"] == t), None)
        if row:
            if "percent" in q or "%" in q or "allocation" in q:
                return {"answer": f"{t} is {row['allocation_pct']}% of the crypto portfolio.", "source": src}
            return {"answer": f"You hold {row['quantity']} {t} "
                              f"(value {row['market_value']} {view['valuation_currency']}). Source: {src}.",
                    "source": src}
    return {"answer": f"Binance portfolio: {view['asset_count']} assets, ≈ {view['total_value']} "
                      f"{view['valuation_currency']}. Ask about a specific asset, allocation, or "
                      f"stablecoins. Source: {src}.", "source": src}


def voice_answer(query: str, *, view: dict | None = None) -> str:
    return chat_answer(query, view=view).get("answer", "")
