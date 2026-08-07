"""M224 — Read-Only Provider Adapter Contract.

Generic contract only. No real provider implementation.
Exposes simulated PUBLIC_DATA and READ_ONLY_ACCOUNT operations.
Connection state: SIMULATED_NOT_CONNECTED.
"""
from __future__ import annotations

import json
import time
from typing import Any

from saathi.platform.tg.broker_readiness.models import (
    ADAPTER_OPERATIONS,
    ALLOWED_ADAPTER_AUTHORITIES,
    AuthorityClass,
    SIMULATED_PROVIDERS,
)
from saathi.platform.tg.broker_readiness.store import ReadinessStore, _uid
from saathi.platform.tg.broker_readiness.transport import (
    TransportGuard,
    TransportGuardError,
    REAL_PROVIDER_TRANSPORT_FORBIDDEN,
)


class AdapterContractError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


class ReadOnlyAdapterContract:
    """Simulated adapter contract. Never opens real transport."""

    CONNECTION_STATE = "SIMULATED_NOT_CONNECTED"

    def __init__(self, store: ReadinessStore, transport: TransportGuard):
        self.store = store
        self.transport = transport
        self._seed_ops()
        self._seed_providers()

    def _seed_ops(self) -> None:
        existing = self.store.fetchone("SELECT COUNT(*) AS c FROM br_adapter_ops")
        if existing and existing["c"] > 0:
            return
        now = time.time()
        for op, auth in ADAPTER_OPERATIONS.items():
            available = 1 if auth in ALLOWED_ADAPTER_AUTHORITIES else 0
            self.store.execute(
                """INSERT OR IGNORE INTO br_adapter_ops(
                    id, operation, authority_class, available_in_m224, detail_json, created_at
                ) VALUES(?,?,?,?,?,?)""",
                (
                    _uid("op"), op, auth.value, available,
                    json.dumps({"write": auth not in ALLOWED_ADAPTER_AUTHORITIES}),
                    now,
                ),
            )

    def _seed_providers(self) -> None:
        now = time.time()
        for p in SIMULATED_PROVIDERS:
            self.store.execute(
                """INSERT OR IGNORE INTO br_providers(
                    provider_id, display_name, description, is_emulator,
                    connection_state, capabilities_json, detail_json, created_at, updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?)""",
                (
                    p["provider_id"], p["display_name"], p["description"],
                    1 if p["is_emulator"] else 0, self.CONNECTION_STATE,
                    json.dumps(["PUBLIC_DATA", "READ_ONLY_ACCOUNT"]),
                    json.dumps({"real_implementation": False}),
                    now, now,
                ),
            )

    def list_operations(self) -> dict[str, Any]:
        rows = self.store.fetchall("SELECT * FROM br_adapter_ops ORDER BY operation")
        ops = []
        for r in rows:
            ops.append({
                "operation": r["operation"],
                "authority_class": r["authority_class"],
                "available_in_m224": bool(r["available_in_m224"]),
                "detail": json.loads(r["detail_json"] or "{}"),
            })
        return {
            "operations": ops,
            "exposed_authorities": [a.value for a in ALLOWED_ADAPTER_AUTHORITIES],
            "connection_state": self.CONNECTION_STATE,
            "real_provider_implementation": False,
            "simulation_only": True,
        }

    def list_providers(self) -> dict[str, Any]:
        rows = self.store.fetchall("SELECT * FROM br_providers ORDER BY provider_id")
        providers = []
        for r in rows:
            providers.append({
                "provider_id": r["provider_id"],
                "display_name": r["display_name"],
                "description": r["description"],
                "is_emulator": bool(r["is_emulator"]),
                "connection_state": r["connection_state"],
                "capabilities": json.loads(r["capabilities_json"] or "[]"),
                "detail": json.loads(r["detail_json"] or "{}"),
            })
        return {
            "providers": providers,
            "all_simulated_not_connected": all(
                p["connection_state"] == self.CONNECTION_STATE for p in providers
            ),
            "simulation_only": True,
        }

    def invoke(self, operation: str, *, provider_id: str = "sim.readonly.fixture", **kwargs: Any) -> dict[str, Any]:
        """Simulate a read-only operation via fixtures. Blocks write and real transport."""
        auth = ADAPTER_OPERATIONS.get(operation)
        if auth is None:
            raise AdapterContractError("DENY_UNKNOWN_CAPABILITY", f"Unknown operation: {operation}")
        if auth not in ALLOWED_ADAPTER_AUTHORITIES:
            raise AdapterContractError(
                "DENY_WRITE_SCOPE",
                f"Operation '{operation}' classified {auth.value} is unavailable. "
                "M224 exposes only PUBLIC_DATA and READ_ONLY_ACCOUNT.",
            )
        # Block real URL if provided
        target = kwargs.get("url") or kwargs.get("endpoint") or ""
        if target:
            try:
                self.transport.assert_allowed(str(target))
            except TransportGuardError as e:
                raise AdapterContractError(e.code, e.message) from e

        fixture = self._fixture_response(operation, provider_id)
        self.store.audit(
            "adapter.invoke_simulated",
            subject=operation,
            detail={"provider_id": provider_id, "authority": auth.value},
        )
        return {
            "ok": True,
            "operation": operation,
            "authority_class": auth.value,
            "provider_id": provider_id,
            "connection_state": self.CONNECTION_STATE,
            "result": fixture,
            "simulated": True,
            "real_transport": False,
            "simulation_only": True,
        }

    def _fixture_response(self, operation: str, provider_id: str) -> dict[str, Any]:
        now = time.time()
        fixtures = {
            "provider_identity": {"provider_id": provider_id, "name": "Simulated", "env": "SIM"},
            "provider_capabilities": {"read": True, "write": False, "transfer": False},
            "connection_status": {"state": self.CONNECTION_STATE},
            "server_time": {"server_time": now, "skew_sec": 0},
            "provider_health": {"status": "SIMULATED_HEALTHY"},
            "rate_limit_status": {"remaining": 100, "limit": 100, "reset_at": now + 60},
            "supported_assets": {"assets": ["USD", "BTC", "ETH", "AAPL"]},
            "account_metadata": {
                "account_ref": "sim-acct-001",
                "account_type": "SIMULATED_READ_ONLY",
                "status": "ACTIVE_SIM",
            },
            "account_type": {"type": "SIMULATED_READ_ONLY"},
            "balances": {"balances": [
                {"asset": "USD", "total": "100000.00", "available": "100000.00", "locked": "0"},
            ]},
            "positions": {"positions": []},
            "portfolio_snapshot": {"equity": "100000.00", "currency": "USD"},
            "transaction_history": {"items": []},
            "deposit_history": {"items": []},
            "withdrawal_history": {"items": []},
            "order_history": {"items": []},
            "trade_history": {"items": []},
            "fee_history": {"items": []},
            "market_permissions": {"permissions": ["MARKET_DATA_READ"]},
            "account_permissions": {"permissions": ["BALANCE_READ", "POSITION_READ"]},
            "session_health": {"healthy": True, "simulated": True},
        }
        return fixtures.get(operation, {"simulated": True})

    def contract_summary(self) -> dict[str, Any]:
        ops = self.list_operations()
        return {
            "milestone": "M224",
            "connection_state": self.CONNECTION_STATE,
            "real_provider_implementation": False,
            "available_operations": [
                o["operation"] for o in ops["operations"] if o["available_in_m224"]
            ],
            "unavailable_write_operations": [
                o["operation"] for o in ops["operations"] if not o["available_in_m224"]
            ],
            "transport_guard": REAL_PROVIDER_TRANSPORT_FORBIDDEN,
            "simulation_only": True,
        }


__all__ = ["ReadOnlyAdapterContract", "AdapterContractError"]
