"""Provider-neutral contracts with no concrete account or order implementation."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Mapping

from saathi.platform.tg.provider_contracts.models import (
    CapabilityContract,
    ProviderDescriptor,
    ProviderRequest,
    ProviderResponse,
    SessionState,
    TransportKind,
)


class Provider(ABC):
    @property
    @abstractmethod
    def descriptor(self) -> ProviderDescriptor:
        raise NotImplementedError

    @abstractmethod
    def capability_contracts(self) -> tuple[CapabilityContract, ...]:
        raise NotImplementedError


ProviderContract = Provider


class MarketDataProvider(Provider):
    @abstractmethod
    def get_quote(self, symbol: str, *, idempotency_key: str) -> ProviderResponse:
        raise NotImplementedError

    @abstractmethod
    def list_candles(
        self,
        symbol: str,
        interval: str,
        *,
        idempotency_key: str,
    ) -> ProviderResponse:
        raise NotImplementedError

    @abstractmethod
    def get_orderbook(self, symbol: str, *, idempotency_key: str) -> ProviderResponse:
        raise NotImplementedError

    @abstractmethod
    def list_trades(
        self,
        symbol: str,
        *,
        cursor: str | None = None,
        limit: int = 2,
        idempotency_key: str,
    ) -> ProviderResponse:
        raise NotImplementedError

    @abstractmethod
    def list_symbols(
        self,
        *,
        cursor: str | None = None,
        limit: int = 2,
        idempotency_key: str,
    ) -> ProviderResponse:
        raise NotImplementedError

    @abstractmethod
    def get_market_status(self, venue: str, *, idempotency_key: str) -> ProviderResponse:
        raise NotImplementedError


class AccountProvider(Provider):
    """Future account-read interface only; intentionally has no implementation."""

    @abstractmethod
    def list_balances(self, *, idempotency_key: str) -> ProviderResponse:
        raise NotImplementedError

    @abstractmethod
    def list_positions(self, *, idempotency_key: str) -> ProviderResponse:
        raise NotImplementedError


class OrderProvider(Provider):
    """Future order interface only; intentionally has no implementation."""

    @abstractmethod
    def list_orders(self, *, idempotency_key: str) -> ProviderResponse:
        raise NotImplementedError

    @abstractmethod
    def submit_order(
        self,
        order: Mapping[str, Any],
        *,
        idempotency_key: str,
    ) -> ProviderResponse:
        raise NotImplementedError


class ConnectivityProvider(Provider):
    @property
    @abstractmethod
    def transport_kind(self) -> TransportKind:
        raise NotImplementedError

    @property
    @abstractmethod
    def offline_only(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def request(self, request: ProviderRequest) -> ProviderResponse:
        raise NotImplementedError


class SessionProvider(Provider):
    @property
    @abstractmethod
    def session_state(self) -> SessionState:
        raise NotImplementedError

    @abstractmethod
    def session_snapshot(self) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def transition_session(self, state: SessionState, *, reason: str = "") -> dict[str, Any]:
        raise NotImplementedError
