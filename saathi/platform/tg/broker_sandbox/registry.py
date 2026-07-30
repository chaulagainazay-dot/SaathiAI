"""M217 — Broker Capability Registry.

Every broker remains NOT_CONNECTED. No real connections, no credentials.
"""
from __future__ import annotations

import json
import time
from typing import Any

from saathi.platform.tg.broker_sandbox.abstraction import Capability, CatalogOnlyAdapter, Broker
from saathi.platform.tg.broker_sandbox.models import (
    AuthMethodDeclared,
    BrokerLifecycle,
    CATALOG_BROKERS,
    ConnectionStatus,
)
from saathi.platform.tg.broker_sandbox.store import SandboxStore


# Default capability declarations (design-time metadata only).
_DEFAULT_CAPS: dict[str, dict[str, Any]] = {
    "sandbox.emulator": {
        "supported_assets": ["AAA", "BBB", "CCC", "SIM-USD"],
        "paper_support": True,
        "market_orders": True,
        "limit_orders": True,
        "stop_orders": True,
        "margin": False,
        "options": False,
        "futures": False,
        "crypto": False,
        "equities": True,
        "rate_limits": {"requests_per_sec": 100, "orders_per_min": 60},
        "authentication_method": AuthMethodDeclared.SANDBOX_EMULATOR.value,
        "streaming_support": False,
        "order_events": True,
        "time_zones": ["UTC"],
    },
    "catalog.binance": {
        "supported_assets": ["BTCUSDT", "ETHUSDT"],
        "paper_support": True,
        "market_orders": True,
        "limit_orders": True,
        "stop_orders": True,
        "margin": True,
        "options": False,
        "futures": True,
        "crypto": True,
        "equities": False,
        "rate_limits": {"requests_per_sec": 10, "orders_per_min": 50},
        "authentication_method": AuthMethodDeclared.HMAC_SIGNED.value,
        "streaming_support": True,
        "order_events": True,
        "time_zones": ["UTC"],
    },
    "catalog.alpaca": {
        "supported_assets": ["AAPL", "MSFT", "SPY"],
        "paper_support": True,
        "market_orders": True,
        "limit_orders": True,
        "stop_orders": True,
        "margin": False,
        "options": False,
        "futures": False,
        "crypto": False,
        "equities": True,
        "rate_limits": {"requests_per_sec": 5, "orders_per_min": 30},
        "authentication_method": AuthMethodDeclared.API_KEY_HEADER.value,
        "streaming_support": True,
        "order_events": True,
        "time_zones": ["America/New_York"],
    },
    "catalog.interactive_brokers": {
        "supported_assets": ["AAPL", "ES", "EUR.USD"],
        "paper_support": True,
        "market_orders": True,
        "limit_orders": True,
        "stop_orders": True,
        "margin": True,
        "options": True,
        "futures": True,
        "crypto": False,
        "equities": True,
        "rate_limits": {"requests_per_sec": 5, "orders_per_min": 20},
        "authentication_method": AuthMethodDeclared.SESSION_TOKEN.value,
        "streaming_support": True,
        "order_events": True,
        "time_zones": ["America/New_York", "UTC"],
    },
    "catalog.zerodha": {
        "supported_assets": ["RELIANCE", "TCS", "NIFTY"],
        "paper_support": True,
        "market_orders": True,
        "limit_orders": True,
        "stop_orders": True,
        "margin": True,
        "options": True,
        "futures": True,
        "crypto": False,
        "equities": True,
        "rate_limits": {"requests_per_sec": 3, "orders_per_min": 10},
        "authentication_method": AuthMethodDeclared.API_KEY_HEADER.value,
        "streaming_support": True,
        "order_events": True,
        "time_zones": ["Asia/Kolkata"],
    },
    "catalog.bybit": {
        "supported_assets": ["BTCUSDT", "ETHUSDT"],
        "paper_support": True,
        "market_orders": True,
        "limit_orders": True,
        "stop_orders": True,
        "margin": True,
        "options": False,
        "futures": True,
        "crypto": True,
        "equities": False,
        "rate_limits": {"requests_per_sec": 10, "orders_per_min": 40},
        "authentication_method": AuthMethodDeclared.HMAC_SIGNED.value,
        "streaming_support": True,
        "order_events": True,
        "time_zones": ["UTC"],
    },
    "catalog.coinbase": {
        "supported_assets": ["BTC-USD", "ETH-USD"],
        "paper_support": True,
        "market_orders": True,
        "limit_orders": True,
        "stop_orders": False,
        "margin": False,
        "options": False,
        "futures": False,
        "crypto": True,
        "equities": False,
        "rate_limits": {"requests_per_sec": 5, "orders_per_min": 20},
        "authentication_method": AuthMethodDeclared.HMAC_SIGNED.value,
        "streaming_support": True,
        "order_events": True,
        "time_zones": ["UTC"],
    },
    "catalog.kraken": {
        "supported_assets": ["XBTUSD", "ETHUSD"],
        "paper_support": True,
        "market_orders": True,
        "limit_orders": True,
        "stop_orders": True,
        "margin": True,
        "options": False,
        "futures": False,
        "crypto": True,
        "equities": False,
        "rate_limits": {"requests_per_sec": 3, "orders_per_min": 15},
        "authentication_method": AuthMethodDeclared.API_KEY_HEADER.value,
        "streaming_support": True,
        "order_events": True,
        "time_zones": ["UTC"],
    },
}


class CapabilityRegistry:
    def __init__(self, store: SandboxStore):
        self.store = store
        self._adapters: dict[str, CatalogOnlyAdapter] = {}
        self.ensure_catalog()

    def ensure_catalog(self) -> None:
        now = time.time()
        for entry in CATALOG_BROKERS:
            existing = self.store.fetchone(
                "SELECT broker_id FROM bs_brokers WHERE broker_id=?",
                (entry["broker_id"],),
            )
            if not existing:
                conn_status = (
                    ConnectionStatus.SANDBOX_ONLY.value
                    if entry["is_emulator"]
                    else ConnectionStatus.NOT_CONNECTED.value
                )
                self.store.execute(
                    """INSERT INTO bs_brokers(
                        broker_id, display_name, provider, description, is_emulator,
                        connection_status, lifecycle, created_at, updated_at
                    ) VALUES(?,?,?,?,?,?,?,?,?)""",
                    (
                        entry["broker_id"],
                        entry["display_name"],
                        entry["provider"],
                        entry["description"],
                        1 if entry["is_emulator"] else 0,
                        conn_status,
                        (
                            BrokerLifecycle.SANDBOX_ACTIVE.value
                            if entry["is_emulator"]
                            else BrokerLifecycle.CATALOGED.value
                        ),
                        now,
                        now,
                    ),
                )
            caps = _DEFAULT_CAPS.get(entry["broker_id"], {})
            status = (
                ConnectionStatus.SANDBOX_ONLY.value
                if entry["is_emulator"]
                else ConnectionStatus.NOT_CONNECTED.value
            )
            cap_existing = self.store.fetchone(
                "SELECT broker_id FROM bs_capabilities WHERE broker_id=?",
                (entry["broker_id"],),
            )
            if not cap_existing:
                self.store.execute(
                    """INSERT INTO bs_capabilities(
                        broker_id, supported_assets_json, paper_support, market_orders,
                        limit_orders, stop_orders, margin, options, futures, crypto, equities,
                        rate_limits_json, authentication_method, streaming_support, order_events,
                        time_zones_json, status, detail_json, updated_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        entry["broker_id"],
                        json.dumps(caps.get("supported_assets", [])),
                        1 if caps.get("paper_support", True) else 0,
                        1 if caps.get("market_orders") else 0,
                        1 if caps.get("limit_orders") else 0,
                        1 if caps.get("stop_orders") else 0,
                        1 if caps.get("margin") else 0,
                        1 if caps.get("options") else 0,
                        1 if caps.get("futures") else 0,
                        1 if caps.get("crypto") else 0,
                        1 if caps.get("equities") else 0,
                        json.dumps(caps.get("rate_limits", {})),
                        caps.get("authentication_method", AuthMethodDeclared.NONE.value),
                        1 if caps.get("streaming_support") else 0,
                        1 if caps.get("order_events") else 0,
                        json.dumps(caps.get("time_zones", ["UTC"])),
                        status,
                        json.dumps({"catalog_only": not entry["is_emulator"]}),
                        now,
                    ),
                )
            # Enforce NOT_CONNECTED for non-emulator on every load
            if not entry["is_emulator"]:
                self.store.execute(
                    "UPDATE bs_brokers SET connection_status=?, updated_at=? WHERE broker_id=?",
                    (ConnectionStatus.NOT_CONNECTED.value, now, entry["broker_id"]),
                )
                self.store.execute(
                    "UPDATE bs_capabilities SET status=?, updated_at=? WHERE broker_id=?",
                    (ConnectionStatus.NOT_CONNECTED.value, now, entry["broker_id"]),
                )
            cap_obj = self.get_capability(entry["broker_id"])
            if not entry["is_emulator"]:
                self._adapters[entry["broker_id"]] = CatalogOnlyAdapter(entry["broker_id"], cap_obj)

        self.store.audit("registry.ensure_catalog", detail={"brokers": len(CATALOG_BROKERS)})

    def list_brokers(self) -> list[dict[str, Any]]:
        rows = self.store.fetchall("SELECT * FROM bs_brokers ORDER BY is_emulator DESC, broker_id")
        out = []
        for r in rows:
            out.append({
                "broker_id": r["broker_id"],
                "display_name": r["display_name"],
                "provider": r["provider"],
                "description": r["description"],
                "is_emulator": bool(r["is_emulator"]),
                "connection_status": r["connection_status"],
                "lifecycle": r["lifecycle"],
                "paper_only": True,
                "live_capable": False,
                "real_connection": False,
            })
        return out

    def get_broker(self, broker_id: str) -> dict[str, Any] | None:
        for b in self.list_brokers():
            if b["broker_id"] == broker_id:
                return b
        return None

    def get_capability(self, broker_id: str) -> Capability:
        row = self.store.fetchone("SELECT * FROM bs_capabilities WHERE broker_id=?", (broker_id,))
        if not row:
            return Capability(broker_id=broker_id, status=ConnectionStatus.NOT_CONNECTED)
        return Capability(
            broker_id=broker_id,
            supported_assets=json.loads(row["supported_assets_json"] or "[]"),
            paper_support=bool(row["paper_support"]),
            market_orders=bool(row["market_orders"]),
            limit_orders=bool(row["limit_orders"]),
            stop_orders=bool(row["stop_orders"]),
            margin=bool(row["margin"]),
            options=bool(row["options"]),
            futures=bool(row["futures"]),
            crypto=bool(row["crypto"]),
            equities=bool(row["equities"]),
            rate_limits=json.loads(row["rate_limits_json"] or "{}"),
            authentication_method=AuthMethodDeclared(row["authentication_method"]),
            streaming_support=bool(row["streaming_support"]),
            order_events=bool(row["order_events"]),
            time_zones=json.loads(row["time_zones_json"] or "[]"),
            status=ConnectionStatus(row["status"]),
        )

    def list_capabilities(self) -> list[dict[str, Any]]:
        brokers = self.list_brokers()
        out = []
        for b in brokers:
            cap = self.get_capability(b["broker_id"]).to_public()
            cap["display_name"] = b["display_name"]
            cap["is_emulator"] = b["is_emulator"]
            out.append(cap)
        return out

    def assert_all_not_connected(self) -> dict[str, Any]:
        """Security invariant: no catalog broker is live-connected."""
        brokers = self.list_brokers()
        violations = []
        for b in brokers:
            if b["is_emulator"]:
                if b["connection_status"] not in (
                    ConnectionStatus.SANDBOX_ONLY.value,
                    ConnectionStatus.NOT_CONNECTED.value,
                ):
                    violations.append(b["broker_id"])
            else:
                if b["connection_status"] != ConnectionStatus.NOT_CONNECTED.value:
                    violations.append(b["broker_id"])
        return {
            "ok": len(violations) == 0,
            "violations": violations,
            "all_not_connected": len(violations) == 0,
            "paper_only": True,
        }

    def refuse_connect(self, broker_id: str) -> dict[str, Any]:
        self.store.audit(
            "registry.connect_refused",
            subject=broker_id,
            detail={"reason": "REAL_CONNECTION_FORBIDDEN"},
        )
        return {
            "ok": False,
            "error": "BROKER_CONNECT_FORBIDDEN",
            "broker_id": broker_id,
            "connection_status": ConnectionStatus.NOT_CONNECTED.value,
            "message": "Real broker connections are not implemented. Catalog brokers remain NOT_CONNECTED.",
            "paper_only": True,
        }


__all__ = ["CapabilityRegistry", "_DEFAULT_CAPS"]
