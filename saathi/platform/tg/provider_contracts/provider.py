"""Deterministic offline market-data providers."""
from __future__ import annotations

from abc import ABC
from typing import Any

from saathi.platform.tg.provider_contracts.capabilities import (
    CAPABILITY_CONTRACTS,
    require_offline_capability,
)
from saathi.platform.tg.provider_contracts.contracts import (
    ConnectivityProvider,
    MarketDataProvider,
    SessionProvider,
)
from saathi.platform.tg.provider_contracts.errors import (
    ProviderContractError,
    ProviderErrorCode,
)
from saathi.platform.tg.provider_contracts.fixtures import FixtureCatalog
from saathi.platform.tg.provider_contracts.models import (
    MOCK_PROVIDER_ID,
    REPLAY_PROVIDER_ID,
    OPERATION_CAPABILITIES,
    Capability,
    CapabilityContract,
    ProviderDescriptor,
    ProviderRequest,
    ProviderResponse,
    SessionState,
    TransportKind,
)
from saathi.platform.tg.provider_contracts.schema import (
    validate_descriptor,
    validate_request_payload,
)
from saathi.platform.tg.provider_contracts.session import ProviderSession
from saathi.platform.tg.provider_contracts.transport import (
    MockTransport,
    ProviderTransport,
    ReplayRecord,
    ReplayTransport,
)


def build_replay_records(catalog: FixtureCatalog) -> tuple[ReplayRecord, ...]:
    definitions = (
        ("replay:quote:AAPL:v1", "quotes.get", {"symbol": "AAPL"}),
        ("replay:candles:BTC-USD:1h:v1", "candles.list", {"symbol": "BTC-USD", "interval": "1h"}),
        ("replay:orderbook:AAPL:v1", "orderbook.get", {"symbol": "AAPL"}),
    )
    records = []
    for fixture_id, operation, params in definitions:
        _, data = catalog.resolve(operation, params)
        records.append(ReplayRecord(
            fixture_id=fixture_id,
            provider_id=REPLAY_PROVIDER_ID,
            operation=operation,
            params=params,
            response_data=data,
        ))
    return tuple(records)


class _OfflineMarketProvider(
    MarketDataProvider,
    ConnectivityProvider,
    SessionProvider,
    ABC,
):
    def __init__(
        self,
        descriptor: ProviderDescriptor,
        transport: ProviderTransport,
        ready_state: SessionState,
    ):
        self._descriptor = validate_descriptor(descriptor)
        self._transport = transport
        self._session = ProviderSession(descriptor.provider_id, descriptor.transport)
        self._session.transition(ready_state, reason="offline_fixture_catalog_ready")

    @property
    def descriptor(self) -> ProviderDescriptor:
        return self._descriptor

    def capability_contracts(self) -> tuple[CapabilityContract, ...]:
        return CAPABILITY_CONTRACTS

    @property
    def transport_kind(self) -> TransportKind:
        return self._transport.kind

    @property
    def offline_only(self) -> bool:
        return True

    @property
    def session_state(self) -> SessionState:
        return self._session.state

    def session_snapshot(self) -> dict[str, Any]:
        return self._session.snapshot()

    def transition_session(self, state: SessionState, *, reason: str = "") -> dict[str, Any]:
        return self._session.transition(state, reason=reason)

    def request(self, request: ProviderRequest) -> ProviderResponse:
        if request.provider_id != self.descriptor.provider_id:
            raise ProviderContractError(
                ProviderErrorCode.INVALID_REQUEST,
                "Request provider does not match provider contract",
            )
        capability = OPERATION_CAPABILITIES[request.operation]
        require_offline_capability(capability)
        expected_state = (
            SessionState.MOCK_READY
            if self.transport_kind is TransportKind.MOCK
            else SessionState.REPLAY_READY
        )
        if self.session_state is not expected_state:
            raise ProviderContractError(
                ProviderErrorCode.SESSION_UNAVAILABLE,
                "Offline provider session is not ready",
                details={"state": self.session_state.value},
            )
        return self._transport.send(request)

    def _request(
        self,
        operation: str,
        params: dict[str, Any],
        idempotency_key: str,
    ) -> ProviderResponse:
        request = validate_request_payload({
            "provider_id": self.descriptor.provider_id,
            "operation": operation,
            "params": params,
            "idempotency_key": idempotency_key,
        })
        return self.request(request)

    def get_quote(self, symbol: str, *, idempotency_key: str) -> ProviderResponse:
        return self._request("quotes.get", {"symbol": symbol}, idempotency_key)

    def list_candles(
        self,
        symbol: str,
        interval: str,
        *,
        idempotency_key: str,
    ) -> ProviderResponse:
        return self._request(
            "candles.list",
            {"symbol": symbol, "interval": interval},
            idempotency_key,
        )

    def get_orderbook(self, symbol: str, *, idempotency_key: str) -> ProviderResponse:
        return self._request("orderbook.get", {"symbol": symbol}, idempotency_key)

    def transport_snapshot(self) -> dict[str, Any]:
        snapshot = getattr(self._transport, "snapshot", None)
        return snapshot() if callable(snapshot) else {
            "kind": self.transport_kind.value,
            "network_enabled": False,
        }


class DeterministicMockProvider(_OfflineMarketProvider):
    def __init__(self, catalog: FixtureCatalog | None = None):
        fixture_catalog = catalog or FixtureCatalog()
        descriptor = ProviderDescriptor(
            provider_id=MOCK_PROVIDER_ID,
            display_name="Saathi Deterministic Mock Market Provider",
            transport=TransportKind.MOCK,
            capabilities=(Capability.QUOTES, Capability.CANDLES, Capability.ORDERBOOK),
        )
        super().__init__(
            descriptor,
            MockTransport(MOCK_PROVIDER_ID, fixture_catalog.resolve),
            SessionState.MOCK_READY,
        )
        self.catalog = fixture_catalog


class DeterministicReplayProvider(_OfflineMarketProvider):
    def __init__(
        self,
        catalog: FixtureCatalog | None = None,
        records: tuple[ReplayRecord, ...] | None = None,
    ):
        fixture_catalog = catalog or FixtureCatalog()
        replay_records = records or build_replay_records(fixture_catalog)
        descriptor = ProviderDescriptor(
            provider_id=REPLAY_PROVIDER_ID,
            display_name="Saathi Recorded Fixture Replay Provider",
            transport=TransportKind.REPLAY,
            capabilities=(Capability.QUOTES, Capability.CANDLES, Capability.ORDERBOOK),
        )
        self.replay_transport = ReplayTransport(REPLAY_PROVIDER_ID, replay_records)
        super().__init__(
            descriptor,
            self.replay_transport,
            SessionState.REPLAY_READY,
        )

    def replay_manifest(self) -> list[dict[str, Any]]:
        return self.replay_transport.manifest()
