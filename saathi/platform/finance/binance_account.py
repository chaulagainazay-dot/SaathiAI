"""Read-only Binance account adapter (Gate A: credential-independent).

Signs ONLY an explicit allowlist of READ endpoints. There is NO generic signed-request
method, NO order/withdraw/transfer/margin/futures capability, and NO path to the
ExecutionGateway. Secrets are resolved from CredentialRefs at call time and never stored,
returned, logged, or placed in any model/event/snapshot. Transport is injectable so Gate A
tests run with mocks and no network/credentials.

Official Binance Spot contract used (stable; live-doc fetch was network-blocked in the build
sandbox — real field names are re-verified at Gate B against the live API):
- GET /api/v3/time                         (public) — server time / clock skew
- GET /api/v3/ticker/price                 (public) — current price
- GET /api/v3/account                      (SIGNED) — balances[{asset,free,locked}], canTrade/…
- GET /sapi/v1/account/apiRestrictions     (SIGNED) — enableReading/…/enableWithdrawals/…
Signature: HMAC-SHA256(query, secret); header X-MBX-APIKEY: <key>.
"""
from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from urllib.parse import urlencode

BASE = "https://api.binance.com"
PUBLIC_ALLOWLIST = frozenset({"/api/v3/time", "/api/v3/ticker/price", "/api/v3/exchangeInfo"})
# The ONLY endpoints that may ever be signed. Everything else is structurally blocked.
SIGNED_READ_ALLOWLIST = frozenset({"/api/v3/account", "/sapi/v1/account/apiRestrictions"})
STABLECOINS = frozenset({"USDT", "USDC", "FDUSD", "DAI", "TUSD", "BUSD", "USDP", "PYUSD"})
VALUATION_CCY = "USDT"
DUST_THRESHOLD = Decimal("1")     # market value < 1 USDT flagged as dust (retained, not dropped)
RECV_WINDOW_MS = 5000


class EndpointBlocked(Exception):
    """Raised when any non-allowlisted (e.g. order/withdraw) endpoint is requested."""


class BinanceHealth(str, Enum):
    AVAILABLE = "AVAILABLE"
    RATE_LIMITED = "RATE_LIMITED"
    AUTH_FAILED = "AUTH_FAILED"
    TIMESTAMP_REJECTED = "TIMESTAMP_REJECTED"
    PERMISSION_UNSAFE = "PERMISSION_UNSAFE"
    SCHEMA_CHANGED = "SCHEMA_CHANGED"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    STALE = "STALE"


class PermissionAssessment(str, Enum):
    READ_ONLY_CONFIRMED = "READ_ONLY_CONFIRMED"
    UNSAFE_TRADING_PERMISSION = "UNSAFE_TRADING_PERMISSION"
    UNSAFE_WITHDRAW_PERMISSION = "UNSAFE_WITHDRAW_PERMISSION"
    UNSAFE_MARGIN_PERMISSION = "UNSAFE_MARGIN_PERMISSION"
    UNSAFE_FUTURES_PERMISSION = "UNSAFE_FUTURES_PERMISSION"
    UNSAFE_TRANSFER_PERMISSION = "UNSAFE_TRANSFER_PERMISSION"
    PERMISSION_UNKNOWN = "PERMISSION_UNKNOWN"
    CREDENTIAL_INVALID = "CREDENTIAL_INVALID"


def assess_permissions(restrictions: dict | None, account: dict | None = None
                       ) -> PermissionAssessment:
    """Default-deny permission verification. SAFE only when reading is enabled and NO
    trading/withdraw/margin/futures/transfer authority exists."""
    if not isinstance(restrictions, dict):
        return PermissionAssessment.CREDENTIAL_INVALID
    r = restrictions
    if not r.get("enableReading", False):
        return PermissionAssessment.CREDENTIAL_INVALID
    if r.get("enableWithdrawals", False):
        return PermissionAssessment.UNSAFE_WITHDRAW_PERMISSION
    if r.get("enableInternalTransfer", False) or r.get("permitsUniversalTransfer", False):
        return PermissionAssessment.UNSAFE_TRANSFER_PERMISSION
    if r.get("enableFutures", False):
        return PermissionAssessment.UNSAFE_FUTURES_PERMISSION
    if r.get("enableMargin", False):
        return PermissionAssessment.UNSAFE_MARGIN_PERMISSION
    if r.get("enableSpotAndMarginTrading", False):
        return PermissionAssessment.UNSAFE_TRADING_PERMISSION
    # cross-check the account endpoint if provided
    if isinstance(account, dict):
        if account.get("canWithdraw", False):
            return PermissionAssessment.UNSAFE_WITHDRAW_PERMISSION
        if account.get("canTrade", False):
            return PermissionAssessment.UNSAFE_TRADING_PERMISSION
    # require the presence of the safety keys we checked; else UNKNOWN (still deny)
    required = ("enableWithdrawals", "enableSpotAndMarginTrading", "enableFutures", "enableMargin")
    if not all(k in r for k in required):
        return PermissionAssessment.PERMISSION_UNKNOWN
    return PermissionAssessment.READ_ONLY_CONFIRMED


def is_safe(assessment: PermissionAssessment) -> bool:
    return assessment == PermissionAssessment.READ_ONLY_CONFIRMED


@dataclass
class BinanceReadOnlyAccountAdapter:
    """Read-only. No trading/withdrawal/transfer/margin/futures methods exist on this class."""
    key_ref: object = None            # CredentialRef (metadata only)
    secret_ref: object = None
    transport: object = None          # callable(method, path, params, *, signed, api_key, secret) -> dict
    public_transport: object = None   # callable(path, params) -> dict
    recv_window: int = RECV_WINDOW_MS

    # ── secret resolution (never stored/returned/logged) ────────────────────────
    def _secrets(self) -> tuple[str, str]:
        from saathi.connectors.platform.credentials import resolve_secret
        return resolve_secret(self.key_ref), resolve_secret(self.secret_ref)

    # ── signed READ (allowlist-enforced; the ONLY signed path) ──────────────────
    def _signed_get(self, path: str, params: dict | None = None) -> dict:
        if path not in SIGNED_READ_ALLOWLIST:
            raise EndpointBlocked(f"BINANCE_ENDPOINT_BLOCKED:{path}")
        params = dict(params or {})
        params["timestamp"] = int(time.time() * 1000)
        params["recvWindow"] = self.recv_window
        if self.transport is not None:                      # test/mock or Gate-B live transport
            return self.transport("GET", path, params, signed=True,
                                  api_key=None, secret=None) if _accepts_kwargs(self.transport) \
                else self.transport("GET", path, params)
        # default live transport (Gate B only): sign locally, secret never leaves this scope
        api_key, secret = self._secrets()
        query = urlencode(params)
        sig = hmac.new(secret.encode(), query.encode(), hashlib.sha256).hexdigest()
        return _live_get(f"{BASE}{path}?{query}&signature={sig}", headers={"X-MBX-APIKEY": api_key})

    def _public_get(self, path: str, params: dict | None = None) -> dict:
        if path not in PUBLIC_ALLOWLIST:
            raise EndpointBlocked(f"BINANCE_ENDPOINT_BLOCKED:{path}")
        if self.public_transport is not None:
            return self.public_transport(path, dict(params or {}))
        return _live_get(f"{BASE}{path}?{urlencode(params or {})}")

    # ── explicit, named READ operations (no generic signed request is exposed) ──
    def get_api_restrictions(self) -> dict:
        return self._signed_get("/sapi/v1/account/apiRestrictions")

    def get_account(self) -> dict:
        return self._signed_get("/api/v3/account")

    def assess(self) -> PermissionAssessment:
        try:
            restr = self.get_api_restrictions()
        except EndpointBlocked:
            raise
        except Exception:
            return PermissionAssessment.CREDENTIAL_INVALID
        try:
            acct = self.get_account()
        except Exception:
            acct = None
        return assess_permissions(restr, acct)

    def server_time_skew_ms(self) -> int | None:
        try:
            d = self._public_get("/api/v3/time")
            return int(d.get("serverTime", 0)) - int(time.time() * 1000)
        except Exception:
            return None

    def price(self, symbol: str) -> Decimal | None:
        try:
            d = self._public_get("/api/v3/ticker/price", {"symbol": symbol})
            p = Decimal(str(d.get("price")))
            return p if p > 0 else None
        except Exception:
            return None

    # ── portfolio snapshot (only after READ_ONLY_CONFIRMED) ─────────────────────
    def balances(self) -> list[dict]:
        acct = self.get_account()
        bals = acct.get("balances") if isinstance(acct, dict) else None
        if not isinstance(bals, list):
            raise ValueError("SCHEMA_CHANGED")
        return bals


def _accepts_kwargs(fn) -> bool:
    try:
        import inspect
        return "signed" in inspect.signature(fn).parameters
    except Exception:
        return False


def _live_get(url: str, headers: dict | None = None) -> dict:
    """Default live GET (Gate B). No POST/PUT/DELETE anywhere in this module."""
    import json
    from urllib.request import Request, urlopen
    with urlopen(Request(url, headers=headers or {"Accept": "application/json"}), timeout=8) as r:
        return json.load(r)
