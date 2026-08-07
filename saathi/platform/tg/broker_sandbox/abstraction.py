"""M216 — Broker Abstraction Layer.

Generic broker interfaces and concept models only.
No implementation for any real broker. No network I/O. No credentials.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from typing import Any, Protocol, runtime_checkable

from saathi.platform.tg.broker_sandbox.models import (
    AssetClass,
    AuthMethodDeclared,
    ConnectionStatus,
    EmulatorOrderState,
)


def _d(v: Any) -> str:
    if v is None:
        return "0"
    if isinstance(v, Decimal):
        return format(v, "f")
    return str(v)


@dataclass(frozen=True)
class Asset:
    symbol: str
    asset_class: AssetClass = AssetClass.EQUITY
    currency: str = "USD"
    exchange: str = "SANDBOX"
    tradable: bool = True
    paper_only: bool = True

    def to_public(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "asset_class": self.asset_class.value,
            "currency": self.currency,
            "exchange": self.exchange,
            "tradable": self.tradable,
            "paper_only": self.paper_only,
        }


@dataclass(frozen=True)
class Balance:
    currency: str
    cash: str
    reserved: str = "0"
    equity: str = "0"
    simulated: bool = True

    def to_public(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Position:
    symbol: str
    quantity: str
    avg_price: str
    side: str = "LONG"
    market_value: str = "0"
    unrealized_pnl: str = "0"
    simulated: bool = True

    def to_public(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Portfolio:
    portfolio_id: str
    balances: list[Balance] = field(default_factory=list)
    positions: list[Position] = field(default_factory=list)
    simulated: bool = True
    paper_only: bool = True

    def to_public(self) -> dict[str, Any]:
        return {
            "portfolio_id": self.portfolio_id,
            "balances": [b.to_public() for b in self.balances],
            "positions": [p.to_public() for p in self.positions],
            "simulated": self.simulated,
            "paper_only": self.paper_only,
        }


@dataclass
class Account:
    account_id: str
    broker_id: str
    display_name: str = ""
    currency: str = "USD"
    status: str = "SANDBOX"
    connection_status: ConnectionStatus = ConnectionStatus.NOT_CONNECTED
    paper_only: bool = True
    live_capable: bool = False

    def to_public(self) -> dict[str, Any]:
        return {
            "account_id": self.account_id,
            "broker_id": self.broker_id,
            "display_name": self.display_name,
            "currency": self.currency,
            "status": self.status,
            "connection_status": self.connection_status.value,
            "paper_only": self.paper_only,
            "live_capable": False,  # hard lock
        }


@dataclass
class Order:
    order_id: str
    client_order_id: str
    symbol: str
    side: str
    order_type: str
    quantity: str
    limit_price: str | None = None
    stop_price: str | None = None
    state: EmulatorOrderState = EmulatorOrderState.PENDING
    filled_qty: str = "0"
    avg_price: str = "0"
    simulated: bool = True
    paper_only: bool = True

    def to_public(self) -> dict[str, Any]:
        return {
            "order_id": self.order_id,
            "client_order_id": self.client_order_id,
            "symbol": self.symbol,
            "side": self.side,
            "order_type": self.order_type,
            "quantity": self.quantity,
            "limit_price": self.limit_price,
            "stop_price": self.stop_price,
            "state": self.state.value if isinstance(self.state, EmulatorOrderState) else self.state,
            "filled_qty": self.filled_qty,
            "avg_price": self.avg_price,
            "simulated": True,
            "paper_only": True,
            "live_order": False,
        }


@dataclass
class Trade:
    trade_id: str
    order_id: str
    symbol: str
    side: str
    quantity: str
    price: str
    simulated: bool = True

    def to_public(self) -> dict[str, Any]:
        d = asdict(self)
        d["simulated"] = True
        d["live_trade"] = False
        return d


@dataclass
class ExecutionReport:
    report_id: str
    order_id: str
    state: str
    filled_qty: str = "0"
    remaining_qty: str = "0"
    avg_price: str = "0"
    reason: str = ""
    simulated: bool = True

    def to_public(self) -> dict[str, Any]:
        d = asdict(self)
        d["simulated"] = True
        return d


@dataclass
class MarketData:
    symbol: str
    bid: str
    ask: str
    last: str
    ts: float
    source: str = "SANDBOX_EMULATOR"
    simulated: bool = True

    def to_public(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Connection:
    broker_id: str
    status: ConnectionStatus = ConnectionStatus.NOT_CONNECTED
    endpoint: str = ""
    last_error: str = ""
    real_network: bool = False  # always False

    def to_public(self) -> dict[str, Any]:
        return {
            "broker_id": self.broker_id,
            "status": self.status.value,
            "endpoint": self.endpoint,
            "last_error": self.last_error,
            "real_network": False,
            "live_connected": False,
        }


@dataclass
class Capability:
    broker_id: str
    supported_assets: list[str] = field(default_factory=list)
    paper_support: bool = True
    market_orders: bool = False
    limit_orders: bool = False
    stop_orders: bool = False
    margin: bool = False
    options: bool = False
    futures: bool = False
    crypto: bool = False
    equities: bool = False
    rate_limits: dict[str, Any] = field(default_factory=dict)
    authentication_method: AuthMethodDeclared = AuthMethodDeclared.NONE
    streaming_support: bool = False
    order_events: bool = False
    time_zones: list[str] = field(default_factory=list)
    status: ConnectionStatus = ConnectionStatus.NOT_CONNECTED

    def to_public(self) -> dict[str, Any]:
        return {
            "broker_id": self.broker_id,
            "supported_assets": list(self.supported_assets),
            "paper_support": self.paper_support,
            "market_orders": self.market_orders,
            "limit_orders": self.limit_orders,
            "stop_orders": self.stop_orders,
            "margin": self.margin,
            "options": self.options,
            "futures": self.futures,
            "crypto": self.crypto,
            "equities": self.equities,
            "rate_limits": dict(self.rate_limits),
            "authentication_method": (
                self.authentication_method.value
                if isinstance(self.authentication_method, AuthMethodDeclared)
                else self.authentication_method
            ),
            "streaming_support": self.streaming_support,
            "order_events": self.order_events,
            "time_zones": list(self.time_zones),
            "status": self.status.value if isinstance(self.status, ConnectionStatus) else self.status,
            "connected": False,
            "live_capable": False,
        }


@dataclass
class Broker:
    """Conceptual broker record. Never holds sockets or secrets."""
    broker_id: str
    display_name: str
    provider: str
    description: str = ""
    is_emulator: bool = False
    connection_status: ConnectionStatus = ConnectionStatus.NOT_CONNECTED
    lifecycle: str = "CATALOGED"
    paper_only: bool = True

    def to_public(self) -> dict[str, Any]:
        return {
            "broker_id": self.broker_id,
            "display_name": self.display_name,
            "provider": self.provider,
            "description": self.description,
            "is_emulator": self.is_emulator,
            "connection_status": self.connection_status.value,
            "lifecycle": self.lifecycle,
            "paper_only": True,
            "live_capable": False,
            "real_connection": False,
        }


@runtime_checkable
class BrokerAdapter(Protocol):
    """Protocol for future adapters. Implementations must remain sandbox-only."""

    def broker_id(self) -> str: ...
    def connection(self) -> Connection: ...
    def capabilities(self) -> Capability: ...
    def is_live_capable(self) -> bool: ...


class AbstractBrokerAdapter(ABC):
    """Base class enforcing paper/sandbox invariants for any future adapter."""

    def __init__(self, broker_id: str):
        self._broker_id = broker_id

    def broker_id(self) -> str:
        return self._broker_id

    def is_live_capable(self) -> bool:
        return False

    def connection(self) -> Connection:
        return Connection(broker_id=self._broker_id, status=ConnectionStatus.NOT_CONNECTED)

    @abstractmethod
    def capabilities(self) -> Capability:
        raise NotImplementedError

    def connect(self, *args: Any, **kwargs: Any) -> Connection:
        """Hard-blocked: real connections are never established in this architecture."""
        raise RuntimeError(
            "BROKER_CONNECT_FORBIDDEN: real broker connections are not implemented. "
            "Use the sandbox emulator only."
        )

    def authenticate(self, *args: Any, **kwargs: Any) -> None:
        raise RuntimeError(
            "BROKER_AUTH_FORBIDDEN: exchange authentication is not implemented. "
            "No API credentials accepted."
        )

    def place_live_order(self, *args: Any, **kwargs: Any) -> None:
        raise RuntimeError("LIVE_ORDER_FORBIDDEN: live orders are not authorized.")


class CatalogOnlyAdapter(AbstractBrokerAdapter):
    """Adapter for catalog brokers — capability declaration only, never connects."""

    def __init__(self, broker_id: str, capability: Capability):
        super().__init__(broker_id)
        self._capability = capability

    def capabilities(self) -> Capability:
        return self._capability

    def connection(self) -> Connection:
        return Connection(
            broker_id=self._broker_id,
            status=ConnectionStatus.NOT_CONNECTED,
            last_error="CATALOG_ONLY_NOT_CONNECTED",
        )


# Concept surface for documentation / control center
ABSTRACTION_CONCEPTS = [
    "Broker", "Account", "Portfolio", "Position", "Order", "Trade",
    "ExecutionReport", "MarketData", "Asset", "Balance", "Connection", "Capability",
]


def abstraction_surface() -> dict[str, Any]:
    return {
        "milestone": "M216",
        "concepts": ABSTRACTION_CONCEPTS,
        "adapters_implemented": ["CatalogOnlyAdapter", "SandboxEmulatorAdapter"],
        "real_brokers_implemented": [],
        "live_capable": False,
        "paper_only": True,
        "network_io": False,
        "note": "Generic interfaces only. No real broker implementation.",
    }


__all__ = [
    "Asset", "Balance", "Position", "Portfolio", "Account", "Order", "Trade",
    "ExecutionReport", "MarketData", "Connection", "Capability", "Broker",
    "BrokerAdapter", "AbstractBrokerAdapter", "CatalogOnlyAdapter",
    "ABSTRACTION_CONCEPTS", "abstraction_surface",
]
