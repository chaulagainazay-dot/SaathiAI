"""Financial Browser Observation Bridge (Phases 1-23).

A NARROW, in-process service that lets a local authenticated SaathiOS consumer (UI / chat /
voice / a co-located validation process) request *normalized observations* from the process
that owns the live Financial Browser runtime — WITHOUT ever exposing browser control, a
Playwright Page/Context, raw DOM/HTML, cookies, tokens, or screenshots.

It exposes only:
    status(provider)              — safe runtime metadata + gate states (no page read)
    observe_portfolio(provider)   — gated → authorized PortfolioSnapshot projection
    observe_account_summary(...)  — gated → account summary projection
    observe_structure(provider)   — owner-authorized → sanitized structural metadata
    evidence(provider)            — privacy-minimized projection for certification/validation

There is NO click / type / navigate / submit / evaluate / download / screenshot path here.
The observer runs INSIDE the browser-owning process; only its typed/redacted result is
returned. This module never imports Playwright and never touches a raw DOM.
"""
from __future__ import annotations

import threading
import time

from saathi.platform.finance import audit
from saathi.platform.finance.browser_runtime import (
    AuthState, ObservationState, RuntimeState, get_runtime_manager,
)
from saathi.platform.finance.observer import (
    ReadOnlyPageReader, get_structure_observer,
)
from saathi.platform.finance.policy import POLICIES, Provider

# Typed states crossing the bridge (never free-text / never a raw exception).
S_OK = "OK"
S_NO_RUNTIME = "FINANCIAL_BROWSER_RUNTIME_NOT_FOUND"
S_LOGIN_REQUIRED = "OWNER_FINANCIAL_LOGIN_REQUIRED"
S_REAUTH_REQUIRED = "OWNER_REAUTHENTICATION_REQUIRED"
S_READ_OFF = "SAATHI_READ_DISABLED"
S_PROVIDER_MISMATCH = "PROVIDER_RUNTIME_MISMATCH"
S_UNKNOWN_PROVIDER = "UNKNOWN_PROVIDER"
S_PAGE_REQUIRED = "OWNER_FINANCIAL_PORTFOLIO_PAGE_REQUIRED"
S_DOMAIN_OUT_OF_SCOPE = "PROVIDER_DOMAIN_OUT_OF_SCOPE"
S_SENSITIVE_BLOCKED = "SENSITIVE_PAGE_OBSERVATION_BLOCKED"
S_STRUCTURE_NOT_AUTHORIZED = "STRUCTURE_INSPECTION_NOT_AUTHORIZED"

# Sensitive URL-path tokens (Phase 16): never observe portfolio on these surfaces.
_SENSITIVE_PATH_TOKENS = (
    "login", "signin", "sign-in", "logout", "otp", "2fa", "two-factor", "verify",
    "security", "settings", "password", "withdraw", "withdrawal", "transfer", "deposit",
    "order", "buy", "sell", "purchase", "trade", "convert", "swap", "api-management",
    "add-bank", "whitelist",
)

_CACHE_TTL_SEC = 5.0            # bounded cache; kill/close/expiry invalidate regardless


def _host_of(url: str) -> str:
    u = (url or "").split("://", 1)[-1]
    return u.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0].lower()


def _path_of(url: str) -> str:
    u = (url or "").split("://", 1)[-1]
    return ("/" + u.split("/", 1)[1]).lower() if "/" in u else "/"


class FinancialBrowserObservationService:
    """Bridge service. One instance per browser-owning process (singleton)."""

    def __init__(self, manager=None):
        self._m = manager or get_runtime_manager()
        self._cache: dict[str, tuple[float, dict]] = {}       # provider -> (ts, envelope)
        self._locks: dict[str, threading.Lock] = {}           # provider -> single-flight lock
        self._glock = threading.Lock()

    # ── resolution + gating ────────────────────────────────────────────────────
    def _provider(self, provider: str) -> Provider | None:
        try:
            return Provider[str(provider).upper()]
        except Exception:
            return None

    def _resolve(self, provider: str, runtime_id: str | None):
        """Return (rt, state). Enforces provider isolation (Phase 14)."""
        prov = self._provider(provider)
        if prov is None:
            return None, S_UNKNOWN_PROVIDER
        if runtime_id:
            rt = self._m.get(runtime_id)
            if rt is None or rt.runtime_state == RuntimeState.CLOSED:
                return None, S_NO_RUNTIME
            if rt.provider != prov:                            # cross-provider request → deny
                return None, S_PROVIDER_MISMATCH
            return rt, S_OK
        rt = self._m.runtime_for_provider(prov)
        return (rt, S_OK) if rt else (None, S_NO_RUNTIME)

    def _gate(self, rt, *, now: float) -> str:
        """Auth + Saathi Read + expiry gate (Phases 4, 21, 22). Cheap; no page read."""
        if rt.runtime_state == RuntimeState.CLOSED:
            return S_NO_RUNTIME
        if rt.auth_state == AuthState.OWNER_REAUTH_REQUIRED:
            return S_REAUTH_REQUIRED
        if rt.auth_state != AuthState.OWNER_AUTHENTICATED:
            return S_LOGIN_REQUIRED
        if rt.ttl_sec and (rt.last_active_at + rt.ttl_sec) < now:
            return S_REAUTH_REQUIRED
        if not self._m.read_allowed(rt.runtime_id):
            return S_READ_OFF
        return S_OK

    def _envelope(self, rt, state: str, *, now: float, **extra) -> dict:
        env = {
            "provider": rt.provider.value if rt else None,
            "runtime_id": rt.runtime_id if rt else None,
            "runtime_state": rt.runtime_state.value if rt else None,
            "authentication_state": rt.auth_state.value if rt else None,
            "saathi_read_state": (
                ObservationState.SAATHI_READ_ON.value if rt and self._m.read_allowed(rt.runtime_id)
                else ObservationState.SAATHI_READ_OFF.value),
            "observation_state": rt.observation_state.value if rt else None,
            "observed_at": now,
            "available": state == S_OK,
            "state": state,
        }
        env.update(extra)
        return env

    def _page_gates(self, rt, prov: Provider):
        """Live-page gates: page present, domain in scope, not a sensitive surface.
        Returns (reader, state)."""
        page = self._m.live_page(prov)
        if page is None:
            return None, S_PAGE_REQUIRED
        reader = ReadOnlyPageReader(page)
        url = reader.current_url()
        if url:
            host = _host_of(url)
            if host and not POLICIES[prov].domain_allowed(host):
                return None, S_DOMAIN_OUT_OF_SCOPE
            path = _path_of(url)
            if any(tok in path for tok in _SENSITIVE_PATH_TOKENS):
                return None, S_SENSITIVE_BLOCKED
        return reader, S_OK

    # ── public operations ──────────────────────────────────────────────────────
    def status(self, provider: str, runtime_id: str | None = None) -> dict:
        now = time.time()
        rt, rstate = self._resolve(provider, runtime_id)
        if rt is None:
            return {"provider": str(provider).upper(), "available": False, "state": rstate,
                    "observed_at": now}
        gate = self._gate(rt, now=now)
        return self._envelope(rt, gate, now=now, read_allowed=(gate == S_OK))

    def observe_portfolio(self, provider: str, runtime_id: str | None = None,
                          *, use_cache: bool = True) -> dict:
        now = time.time()
        rt, rstate = self._resolve(provider, runtime_id)
        if rt is None:
            return {"provider": str(provider).upper(), "available": False, "state": rstate,
                    "observed_at": now}
        prov = rt.provider
        gate = self._gate(rt, now=now)
        if gate != S_OK:
            self._cache.pop(prov.value, None)                  # invalidate on any gate failure
            audit.record(provider=prov.value, actor="AGENT_INPUT", capability="READ_PORTFOLIO",
                         result="BLOCKED", session_id=rt.runtime_id, detail=gate)
            return self._envelope(rt, gate, now=now)
        # cache (Phase 19) — only after gates pass
        if use_cache:
            hit = self._cache.get(prov.value)
            if hit and (now - hit[0]) <= _CACHE_TTL_SEC:
                env = dict(hit[1]); env["freshness"] = "CACHED"; env["observed_at"] = now
                return env
        lock = self._lock_for(prov.value)
        with lock:                                             # single-flight (Phase 18)
            hit = self._cache.get(prov.value)
            if use_cache and hit and (time.time() - hit[0]) <= _CACHE_TTL_SEC:
                env = dict(hit[1]); env["freshness"] = "CACHED"; env["observed_at"] = time.time()
                return env
            reader, pstate = self._page_gates(rt, prov)
            if reader is None:
                audit.record(provider=prov.value, actor="AGENT_INPUT", capability="READ_PORTFOLIO",
                             result="BLOCKED", session_id=rt.runtime_id, detail=pstate)
                return self._envelope(rt, pstate, now=time.time())
            from saathi.platform.finance.browser_portfolio import read_portfolio
            out = read_portfolio(rt.runtime_id, manager=self._m, reader=reader)
            state = S_OK if out.get("available") else out.get("state", "UNAVAILABLE")
            view = out.get("view")
            env = self._envelope(
                rt, state if out.get("available") else state, now=time.time(),
                freshness="FRESH", holding_count=(len(view["positions"]) if view else 0),
                view=view, limitations=out.get("limitations", []))
            env["available"] = bool(out.get("available"))
            if out.get("available"):
                self._cache[prov.value] = (time.time(), dict(env))
            audit.record(provider=prov.value, actor="AGENT_INPUT", capability="READ_PORTFOLIO",
                         result="OK" if out.get("available") else "BLOCKED",
                         session_id=rt.runtime_id,
                         detail=f"holdings={env.get('holding_count', 0)}")
            return env

    def observe_account_summary(self, provider: str, runtime_id: str | None = None) -> dict:
        env = self.observe_portfolio(provider, runtime_id)
        if not env.get("available"):
            return env
        view = env.get("view") or {}
        return self._envelope(
            self._m.get(env["runtime_id"]), S_OK, now=time.time(),
            currency=view.get("currency"), total_value=view.get("total_value"),
            asset_count=view.get("asset_count"), source=view.get("source"))

    def observe_structure(self, provider: str, runtime_id: str | None = None,
                          *, authorize_structure_inspection: bool = False) -> dict:
        now = time.time()
        rt, rstate = self._resolve(provider, runtime_id)
        if rt is None:
            return {"provider": str(provider).upper(), "available": False, "state": rstate,
                    "observed_at": now}
        if not authorize_structure_inspection:                 # explicit owner authorization (Phase 10)
            return self._envelope(rt, S_STRUCTURE_NOT_AUTHORIZED, now=now)
        gate = self._gate(rt, now=now)
        if gate != S_OK:
            return self._envelope(rt, gate, now=now)
        reader, pstate = self._page_gates(rt, rt.provider)
        if reader is None:
            return self._envelope(rt, pstate, now=now)
        sob = get_structure_observer(rt.provider.value)
        if sob is None:
            return self._envelope(rt, S_UNKNOWN_PROVIDER, now=now)
        structure = sob.observe_structure(reader)              # sanitized: no owner values
        audit.record(provider=rt.provider.value, actor="AGENT_INPUT",
                     capability="OBSERVE_STRUCTURE", result="OK", session_id=rt.runtime_id,
                     detail=f"cols={structure.get('column_count', 0)}")
        return self._envelope(rt, S_OK, now=now, structure=structure)

    def evidence(self, provider: str, runtime_id: str | None = None) -> dict:
        """Privacy-minimized projection for certification/validation (Phase 7).
        NO owner quantities / values — only shape + field names + freshness."""
        env = self.observe_portfolio(provider, runtime_id)
        rt = self._m.get(env["runtime_id"]) if env.get("runtime_id") else None
        if not env.get("available"):
            return self._envelope(rt, env.get("state"), now=time.time()) if rt else env
        view = env.get("view") or {}
        positions = view.get("positions", [])
        resolved = sum(1 for p in positions if p.get("symbol"))
        field_names = sorted({k for p in positions for k in p.keys()})
        return self._envelope(
            rt, S_OK, now=time.time(),
            holding_count=len(positions), resolved_symbol_count=resolved,
            unresolved_symbol_count=len(positions) - resolved,
            available_field_names=field_names,
            source_classification=view.get("source"),
            data_class=view.get("data_class"),
            selectors_verified=view.get("selectors_verified"),
            freshness=env.get("freshness"),
            schema_state=("VERIFIED" if view.get("selectors_verified") else "PROVISIONAL"))

    # ── invalidation + internals ────────────────────────────────────────────────
    def invalidate(self, provider: str | Provider | None = None) -> None:
        if provider is None:
            self._cache.clear()
            return
        key = provider.value if isinstance(provider, Provider) else str(provider).upper()
        self._cache.pop(key, None)

    def _lock_for(self, key: str) -> threading.Lock:
        with self._glock:
            lk = self._locks.get(key)
            if lk is None:
                lk = self._locks[key] = threading.Lock()
            return lk


_SERVICE: FinancialBrowserObservationService | None = None


def get_observation_service() -> FinancialBrowserObservationService:
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = FinancialBrowserObservationService()
    return _SERVICE
