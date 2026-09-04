"""M320–M327 credentialless provider contract and mock/replay tests."""
from __future__ import annotations

import inspect
import json
import socket
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from saathi.platform.tg.provider_contracts.capabilities import (
    negotiate_capabilities,
)
from saathi.platform.tg.provider_contracts.contracts import (
    AccountProvider,
    ConnectivityProvider,
    MarketDataProvider,
    OrderProvider,
    Provider,
    ProviderContract,
    SessionProvider,
)
from saathi.platform.tg.provider_contracts.errors import (
    ProviderContractError,
    ProviderErrorCode,
    normalize_error,
)
from saathi.platform.tg.provider_contracts.models import (
    AUTHORITY_LOCKS,
    CURRENT_MATURITY,
    HARD_AUTHORITY_KEYS,
    ISOLATION_ASSERTIONS,
    MAX_STATE,
    MOCK_PROVIDER_ID,
    REPLAY_PROVIDER_ID,
    SCHEMA_VERSION,
    TERMINAL_VERDICT,
    Capability,
    CapabilityAccess,
    CapabilityContract,
    ProviderDescriptor,
    ProviderResponse,
    ResponseStatus,
    SessionState,
    TransportKind,
    authority_locks_intact,
)
from saathi.platform.tg.provider_contracts.provider import (
    DeterministicMockProvider,
    DeterministicReplayProvider,
)
from saathi.platform.tg.provider_contracts.schema import (
    validate_capability_contract,
    validate_descriptor,
    validate_request_payload,
    validate_response,
)
from saathi.platform.tg.provider_contracts.session import (
    FORBIDDEN_SESSION_STATES,
    ProviderSession,
)
from saathi.platform.tg.provider_contracts.service import (
    ProviderContractService,
    reset_provider_contracts_for_tests,
)
from saathi.platform.tg.provider_contracts.fixtures import FixtureCatalog, with_provenance
from saathi.platform.tg.provider_contracts.transport import (
    MockTransport,
    ReplayRecord,
    ReplayTransport,
    TransportRegistry,
    reject_transport_kind,
)


@pytest.fixture()
def service(tmp_path: Path) -> ProviderContractService:
    return reset_provider_contracts_for_tests(tmp_path / "provider_contracts.db")


@pytest.fixture()
def api_client(tmp_path: Path, monkeypatch, service: ProviderContractService):
    from saathi.platform.service import reset_platform_for_tests
    from saathi.tool_runtime.registry import reset_registry_for_tests

    reset_registry_for_tests()
    platform = reset_platform_for_tests(tmp_path / "platform_api.db")
    import saathi.platform.api as api_module
    import saathi.platform.service as service_module

    monkeypatch.setattr(service_module, "_DEFAULT", platform)
    monkeypatch.setattr(api_module, "default_platform", lambda: platform)
    monkeypatch.setattr(api_module, "_tg_provider_contracts", lambda: service)
    from saathi.server import app

    client = TestClient(app)
    bootstrap = client.post(
        "/api/v1/platform/bootstrap",
        json={"email": "m327@local", "name": "M327 Owner"},
    )
    assert bootstrap.status_code == 200
    login = client.post(
        "/api/v1/platform/auth/login",
        json={"email": "m327@local"},
    )
    assert login.status_code == 200
    return client, {"X-Platform-Token": login.json()["token"]}


def request_payload(
    *,
    provider_id: str = MOCK_PROVIDER_ID,
    operation: str = "quotes.get",
    params: dict | None = None,
    key: str = "test:request:quote:AAPL:v1",
) -> dict:
    return {
        "provider_id": provider_id,
        "operation": operation,
        "params": {"symbol": "AAPL"} if params is None else params,
        "idempotency_key": key,
        "schema_version": SCHEMA_VERSION,
    }


def test_provider_neutral_interfaces_are_abstract():
    for contract in (
        ProviderContract,
        Provider,
        MarketDataProvider,
        AccountProvider,
        OrderProvider,
        ConnectivityProvider,
        SessionProvider,
    ):
        assert inspect.isabstract(contract)
    assert {"list_balances", "list_positions"} <= AccountProvider.__abstractmethods__
    assert {"list_orders", "submit_order"} <= OrderProvider.__abstractmethods__


def test_hard_authority_boundary_is_false():
    assert authority_locks_intact() is True
    assert set(AUTHORITY_LOCKS) == set(HARD_AUTHORITY_KEYS)
    assert all(value is False for value in AUTHORITY_LOCKS.values())
    assert len(HARD_AUTHORITY_KEYS) == 17
    assert all(value is True for value in ISOLATION_ASSERTIONS.values())


def test_mock_provider_contract_is_credentialless():
    provider = DeterministicMockProvider()
    descriptor = provider.descriptor.to_dict()
    assert isinstance(provider, MarketDataProvider)
    assert isinstance(provider, ConnectivityProvider)
    assert isinstance(provider, SessionProvider)
    assert not isinstance(provider, AccountProvider)
    assert not isinstance(provider, OrderProvider)
    assert descriptor["authenticated"] is False
    assert descriptor["credentialless"] is True
    assert descriptor["network_enabled"] is False
    assert descriptor["real_provider"] is False


def test_replay_provider_contract_is_credentialless():
    provider = DeterministicReplayProvider()
    assert provider.transport_kind is TransportKind.REPLAY
    assert provider.offline_only is True
    assert provider.session_state is SessionState.REPLAY_READY
    assert provider.session_snapshot()["authenticated"] is False


def test_descriptor_rejects_real_or_authenticated_provider():
    with pytest.raises(ProviderContractError) as real:
        validate_descriptor(ProviderDescriptor(
            provider_id="bad.real.provider",
            display_name="bad",
            transport=TransportKind.MOCK,
            capabilities=(),
            network_enabled=True,
            real_provider=True,
        ))
    assert real.value.code is ProviderErrorCode.TRANSPORT_FORBIDDEN
    with pytest.raises(ProviderContractError) as authenticated:
        validate_descriptor(ProviderDescriptor(
            provider_id="bad.auth.provider",
            display_name="bad",
            transport=TransportKind.MOCK,
            capabilities=(),
            authenticated=True,
        ))
    assert authenticated.value.code is ProviderErrorCode.CONTRACT_VIOLATION


def test_capability_negotiation_grants_only_public_offline_fixtures(service):
    result = service.negotiate(
        MOCK_PROVIDER_ID,
        [
            "quotes",
            "candles",
            "trades",
            "orderbook",
            "symbols",
            "market_status",
            "positions",
            "balances",
            "orders",
            "transfers",
        ],
    )
    assert result["granted"] == [
        "quotes",
        "candles",
        "trades",
        "orderbook",
        "symbols",
        "market_status",
    ]
    assert result["denied"] == ["positions", "balances", "orders", "transfers"]
    assert result["negotiation_only"] is True
    assert result["executes"] is False


def test_capability_negotiation_rejects_unknown_and_duplicate():
    with pytest.raises(ProviderContractError) as unknown:
        negotiate_capabilities(MOCK_PROVIDER_ID, ["quotes", "withdrawals"])
    assert unknown.value.code is ProviderErrorCode.UNSUPPORTED
    with pytest.raises(ProviderContractError) as duplicate:
        negotiate_capabilities(MOCK_PROVIDER_ID, ["quotes", "quotes"])
    assert duplicate.value.code is ProviderErrorCode.INVALID_REQUEST


def test_schema_accepts_canonical_request():
    request = validate_request_payload(request_payload())
    assert request.provider_id == MOCK_PROVIDER_ID
    assert request.operation == "quotes.get"
    assert request.fingerprint
    assert request.request_id.startswith("req_")


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {**request_payload(), "unknown": True},
        {**request_payload(), "schema_version": "future"},
        {**request_payload(), "idempotency_key": "short"},
        {**request_payload(), "operation": "network.get"},
        {**request_payload(), "params": []},
        {**request_payload(), "params": {"nested": {"api_key": "forbidden"}}},
        {**request_payload(), "params": {"account_id": "forbidden"}},
    ],
)
def test_schema_rejects_malformed_or_sensitive_requests(payload):
    with pytest.raises(ProviderContractError) as error:
        validate_request_payload(payload)
    assert error.value.code is ProviderErrorCode.INVALID_REQUEST


def test_mock_quote_is_repeatable_and_idempotent(service):
    payload = request_payload()
    first = service.dispatch(payload)
    second = service.dispatch(payload)
    assert first == second
    response = first["response"]
    assert response["fixture_id"] == "quote:AAPL"
    assert response["transport"] == "mock"
    assert response["data"]["fixture"]["last"] == "218.12"
    assert response["data"]["synthetic"] is True
    assert response["idempotent"] is True
    assert response["real_connectivity"] is False


def test_mock_candles_and_orderbook_are_deterministic(service):
    candles = service.dispatch(request_payload(
        operation="candles.list",
        params={"symbol": "AAPL", "interval": "1d"},
        key="test:request:candles:AAPL:1d:v1",
    ))
    book = service.dispatch(request_payload(
        operation="orderbook.get",
        params={"symbol": "AAPL"},
        key="test:request:orderbook:AAPL:v1",
    ))
    assert len(candles["response"]["data"]["fixture"]) == 3
    assert book["response"]["data"]["fixture"]["depth"] == 3
    assert candles["response"]["response_hash"]
    assert book["response"]["response_hash"]


def test_mock_fixture_unavailable_is_normalized(service):
    result = service.request(request_payload(
        params={"symbol": "UNKNOWN"},
        key="test:request:quote:unknown:v1",
    ))
    assert result["ok"] is False
    assert result["error"]["code"] == "fixture_missing"
    assert result["REAL_CONNECTIVITY_AUTHORIZED"] is False


def test_sensitive_provider_operations_are_denied(service):
    matrix = (
        ("positions.list", "test:denied:positions:v1"),
        ("balances.list", "test:denied:balances:v1"),
        ("orders.list", "test:denied:orders:list:v1"),
        ("orders.submit", "test:denied:orders:submit:v1"),
        ("transfers.create", "test:denied:transfers:v1"),
    )
    for operation, key in matrix:
        result = service.request(request_payload(
            operation=operation,
            params={},
            key=key,
        ))
        assert result["ok"] is False
        assert result["error"]["code"] == "capability_forbidden"


def test_idempotency_key_conflict_fails_closed(service):
    key = "test:idempotency:conflict:v1"
    service.dispatch(request_payload(key=key))
    with pytest.raises(ProviderContractError) as error:
        service.dispatch(request_payload(params={"symbol": "BTC-USD"}, key=key))
    assert error.value.code is ProviderErrorCode.IDEMPOTENCY_CONFLICT


def test_replay_manifest_contains_recorded_request_response_contract(service):
    manifest = service.replay_fixtures()
    assert manifest["count"] == 6
    assert manifest["deterministic"] is True
    assert manifest["network_capture"] is False
    for fixture in manifest["fixtures"]:
        assert fixture["recorded_request"]["provider_id"] == REPLAY_PROVIDER_ID
        assert len(fixture["recorded_response_hash"]) == 64
        assert fixture["credentialless"] is True
        assert fixture["integrity_valid"] is True


def test_replay_request_is_repeatable(service):
    payload = request_payload(
        provider_id=REPLAY_PROVIDER_ID,
        key="test:replay:quote:AAPL:v1",
    )
    first = service.dispatch(payload)
    second = service.dispatch(payload)
    assert first == second
    assert first["response"]["transport"] == "replay"
    assert first["response"]["fixture_id"] == "replay:quote:AAPL:v1"


def test_replay_miss_is_normalized(service):
    result = service.request(request_payload(
        provider_id=REPLAY_PROVIDER_ID,
        params={"symbol": "BTC-USD"},
        key="test:replay:quote:miss:v1",
    ))
    assert result["ok"] is False
    assert result["error"]["code"] == "fixture_missing"


def test_response_schema_validation_rejects_malformed_response():
    response = ProviderResponse(
        provider_id=MOCK_PROVIDER_ID,
        request_id="req_contract_invalid",
        operation="quotes.get",
        status=ResponseStatus.OK,
        data={},
        error={"code": "should_not_exist"},
        transport=TransportKind.MOCK,
        fixture_id="invalid",
    )
    with pytest.raises(ProviderContractError) as error:
        validate_response(response)
    assert error.value.code is ProviderErrorCode.INVALID_RESPONSE


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (TimeoutError(), ProviderErrorCode.TIMEOUT),
        (ConnectionError(), ProviderErrorCode.UNAVAILABLE),
        (NotImplementedError(), ProviderErrorCode.UNSUPPORTED),
        (ValueError(), ProviderErrorCode.INVALID_REQUEST),
        (RuntimeError(), ProviderErrorCode.CONTRACT_VIOLATION),
    ],
)
def test_error_normalization(error, code):
    normalized = normalize_error(error)
    assert normalized.code is code
    assert normalized.to_dict()["provider_independent"] is True


def test_session_state_machine_has_no_authentication(service):
    sessions = service.sessions()
    assert sessions["authentication_state_exists"] is False
    assert set(sessions["states"]) == {
        "DISCONNECTED",
        "MOCK_READY",
        "REPLAY_READY",
        "UNAVAILABLE",
        "FAULTED",
        "CLOSED",
    }
    assert {item["state"] for item in sessions["sessions"]} == {
        "MOCK_READY",
        "REPLAY_READY",
    }
    assert set(sessions["forbidden_states"]) == set(FORBIDDEN_SESSION_STATES)
    assert all(item["authenticated"] is False for item in sessions["sessions"])


def test_session_invalid_transition_fails_closed(service):
    provider = service.mock_provider
    provider.transition_session(SessionState.DISCONNECTED, reason="test")
    with pytest.raises(ProviderContractError):
        provider.transition_session(SessionState.REPLAY_READY, reason="wrong_transport")
    assert provider.session_state is SessionState.DISCONNECTED


def test_unready_session_refuses_request(service):
    provider = service.mock_provider
    provider.transition_session(SessionState.UNAVAILABLE, reason="fixture_catalog_offline")
    result = service.request(request_payload(key="test:session:unavailable:v1"))
    assert result["ok"] is False
    assert result["error"]["code"] == "invalid_session_state"


@pytest.mark.parametrize(
    "kind",
    [
        "http",
        "https",
        "websocket",
        "rest",
        "raw_socket",
        "broker_sdk",
        "binance",
        "alpaca",
        "interactive_brokers",
        "browser",
        "subprocess",
    ],
)
def test_transport_allowlist_rejects_network_and_sdk_kinds(kind):
    with pytest.raises(ProviderContractError) as error:
        reject_transport_kind(kind)
    assert error.value.code is ProviderErrorCode.TRANSPORT_FORBIDDEN


def test_transport_source_isolation_scan(service):
    scan = service.transport_isolation_scan()
    assert scan["ok"] is True
    assert scan["findings"] == []
    assert scan["allowed_transports"] == ["mock", "replay"]
    assert scan["network_transport_classes"] == 0
    assert scan["broker_sdk_imports"] == 0


def test_service_composes_existing_governance_and_audit(service):
    posture = service.posture()
    assert posture["governance_binding"]["registered"] is True
    assert posture["governance_binding"]["governance_status"] == "MOCK_ELIGIBLE"
    service.mock_quote()
    audit = service.governance.store.list_audit(10)
    assert any(item["kind"] == "provider_offline_request" for item in audit)
    assert all("api_key" not in str(item["detail"]).lower() for item in audit)


def test_dashboard_has_no_connection_or_credential_controls(service):
    dashboard = service.dashboard()
    assert dashboard["overview"]["network_transports"] == 0
    assert dashboard["overview"]["real_connections"] == 0
    assert dashboard["overview"]["accounts_accessed"] == 0
    assert dashboard["overview"]["orders_submitted"] == 0
    assert "credential_input" in dashboard["forbidden_ui_controls"]
    assert "real_provider_connect_button" in dashboard["forbidden_ui_controls"]


def test_security_and_maturity(service):
    security = service.security_scan()
    maturity = service.maturity()
    assert security["ok"] is True
    assert security["authority_locks_intact"] is True
    assert maturity["current"] == CURRENT_MATURITY
    assert maturity["max_state"] == MAX_STATE
    assert maturity["can_advance_automatically"] is False


def test_final_certification(service):
    result = service.certify()
    assert result["ok"] is True
    assert result["verdict"] == TERMINAL_VERDICT
    assert result["max_state"] == MAX_STATE
    assert result["current_maturity"] == CURRENT_MATURITY
    assert all(result["checks"].values())
    assert result["failures"] == []
    assert len(result["evidence_hash"]) == 64
    assert all(result[key] is False for key in HARD_AUTHORITY_KEYS)


def test_platform_api_requires_authentication(api_client):
    client, _ = api_client
    for path in (
        "/api/v1/platform/tg/provider-contracts/dashboard",
        "/api/v1/platform/tg/provider-contracts/charter",
        "/api/v1/platform/tg/provider-contracts/providers",
        "/api/v1/platform/tg/provider-contracts/capabilities",
        "/api/v1/platform/tg/provider-contracts/replay/fixtures",
        "/api/v1/platform/tg/provider-contracts/sessions",
    ):
        response = client.get(path)
        assert response.status_code == 401


def test_platform_api_offline_provider_journey(api_client):
    client, headers = api_client
    dashboard = client.get(
        "/api/v1/platform/tg/provider-contracts/dashboard",
        headers=headers,
    )
    assert dashboard.status_code == 200
    assert dashboard.json()["overview"]["network_transports"] == 0

    charter = client.get(
        "/api/v1/platform/tg/provider-contracts/charter",
        headers=headers,
    ).json()
    assert charter["permission_activates_connectivity"] is False

    providers = client.get(
        "/api/v1/platform/tg/provider-contracts/providers",
        headers=headers,
    ).json()
    assert providers["count"] == 2
    assert providers["any_connected"] is False

    negotiation = client.post(
        "/api/v1/platform/tg/provider-contracts/capabilities/negotiate",
        headers=headers,
        json={
            "provider_id": MOCK_PROVIDER_ID,
            "capabilities": ["quotes", "balances", "orders"],
        },
    ).json()
    assert negotiation["granted"] == ["quotes"]
    assert negotiation["denied"] == ["balances", "orders"]

    mock = client.post(
        "/api/v1/platform/tg/provider-contracts/requests",
        headers=headers,
        json=request_payload(key="api:mock:quote:AAPL:v1"),
    ).json()
    assert mock["response"]["transport"] == "mock"

    replay = client.post(
        "/api/v1/platform/tg/provider-contracts/requests",
        headers=headers,
        json=request_payload(
            provider_id=REPLAY_PROVIDER_ID,
            key="api:replay:quote:AAPL:v1",
        ),
    ).json()
    assert replay["response"]["transport"] == "replay"

    certification = client.post(
        "/api/v1/platform/tg/provider-contracts/certify",
        headers=headers,
    ).json()
    assert certification["verdict"] == TERMINAL_VERDICT
    assert certification["ok"] is True


def test_capability_catalog_uses_explicit_contract_states(service):
    catalog = service.capabilities()
    assert set(catalog["known_states"]) == {
        "SUPPORTED_OFFLINE",
        "UNSUPPORTED",
        "FORBIDDEN_BY_GOVERNANCE",
        "UNAVAILABLE",
    }
    assert set(catalog["supported_offline"]) == {
        "quotes",
        "candles",
        "trades",
        "orderbook",
        "symbols",
        "market_status",
    }
    assert set(catalog["forbidden_by_governance"]) == {
        "positions",
        "balances",
        "orders",
        "transfers",
    }


def test_capability_contract_validation_rejects_operation_mismatch():
    malformed = CapabilityContract(
        Capability.QUOTES,
        CapabilityAccess.SUPPORTED_OFFLINE,
        ("orders.submit",),
        "synthetic_public_market_fixture",
        "malformed test contract",
    )
    with pytest.raises(ProviderContractError) as error:
        validate_capability_contract(malformed)
    assert error.value.code is ProviderErrorCode.INVALID_RESPONSE


def test_mock_trades_and_symbols_have_deterministic_pagination(service):
    first = service.dispatch(request_payload(
        operation="trades.list",
        params={"symbol": "AAPL", "limit": 2},
        key="test:trades:AAPL:p1:v1",
    ))
    second = service.dispatch(request_payload(
        operation="trades.list",
        params={"symbol": "AAPL", "cursor": "offset:2", "limit": 2},
        key="test:trades:AAPL:p2:v1",
    ))
    assert first["response"]["data"]["fixture"]["page"] == {
        "cursor": None,
        "next_cursor": "offset:2",
        "limit": 2,
        "count": 2,
        "total": 5,
    }
    assert second["response"]["data"]["fixture"]["page"]["next_cursor"] == "offset:4"
    assert [
        item["trade_id"]
        for item in first["response"]["data"]["fixture"]["items"]
    ] == ["syn-aapl-001", "syn-aapl-002"]

    symbols = service.dispatch(request_payload(
        operation="symbols.list",
        params={"limit": 2},
        key="test:symbols:p1:v1",
    ))
    assert symbols["response"]["data"]["fixture"]["page"]["total"] == 4
    assert symbols["response"]["data"]["source_type"] == "MOCK"


def test_market_status_is_fixed_and_synthetic(service):
    first = service.dispatch(request_payload(
        operation="market_status.get",
        params={"venue": "SYNTHETIC-US"},
        key="test:market-status:one:v1",
    ))
    second = service.dispatch(request_payload(
        operation="market_status.get",
        params={"venue": "SYNTHETIC-US"},
        key="test:market-status:two:v1",
    ))
    assert first["response"]["data"]["fixture"] == second["response"]["data"]["fixture"]
    assert first["response"]["data"]["fixture"]["status"] == "FIXTURE_OPEN"
    assert first["response"]["data"]["live"] is False


@pytest.mark.parametrize(
    ("simulation", "code", "retryable"),
    [
        ("timeout", "timeout_simulation", True),
        ("unavailable", "provider_unavailable", True),
    ],
)
def test_deterministic_error_injection(service, simulation, code, retryable):
    payload = request_payload(
        params={
            "symbol": "AAPL",
            "simulate_error": simulation,
            "simulated_latency_ms": 500,
        },
        key=f"test:simulation:{simulation}:v1",
    )
    first = service.request(payload)
    second = service.request(payload)
    assert first == second
    assert first["error"]["code"] == code
    assert first["error"]["retryable"] is retryable
    assert first["error"]["details"]["waited"] is False


def test_synthetic_latency_is_metadata_only(service):
    result = service.dispatch(request_payload(
        params={"symbol": "AAPL", "simulated_latency_ms": 60_000},
        key="test:synthetic:latency:max:v1",
    ))
    assert result["response"]["data"]["simulated_latency_ms"] == 60_000
    assert result["response"]["data"]["waited"] is False


def test_every_market_response_has_complete_provenance(service):
    requests = [
        ("quotes.get", {"symbol": "AAPL"}),
        ("candles.list", {"symbol": "AAPL", "interval": "1d"}),
        ("trades.list", {"symbol": "AAPL", "limit": 2}),
        ("orderbook.get", {"symbol": "AAPL"}),
        ("symbols.list", {"limit": 2}),
        ("market_status.get", {"venue": "SYNTHETIC-US"}),
    ]
    for index, (operation, params) in enumerate(requests):
        response = service.dispatch(request_payload(
            operation=operation,
            params=params,
            key=f"test:provenance:{index}:v1",
        ))["response"]["data"]
        assert response["source_type"] == "MOCK"
        assert response["live"] is False
        assert response["synthetic"] is True
        assert response["account_derived"] is False
        assert response["execution_capable"] is False


def test_replay_provenance_is_replay_not_mock(service):
    result = service.dispatch(request_payload(
        provider_id=REPLAY_PROVIDER_ID,
        key="test:replay:provenance:AAPL:v1",
    ))
    data = result["response"]["data"]
    assert data["source_type"] == "REPLAY"
    assert data["live"] is False
    assert data["synthetic"] is True
    assert data["account_derived"] is False
    assert data["execution_capable"] is False


def _replay_record(
    *,
    fixture_id: str = "test:replay:quote:AAPL:v1",
    integrity_hash: str | None = None,
) -> ReplayRecord:
    _, data = FixtureCatalog().resolve("quotes.get", {"symbol": "AAPL"})
    return ReplayRecord(
        fixture_id=fixture_id,
        provider_id=REPLAY_PROVIDER_ID,
        operation="quotes.get",
        params={"symbol": "AAPL"},
        response_data=with_provenance(data, "REPLAY"),
        integrity_hash=integrity_hash,
    )


def test_replay_rejects_duplicate_fixture_fingerprints():
    with pytest.raises(ProviderContractError) as error:
        ReplayTransport(
            REPLAY_PROVIDER_ID,
            (
                _replay_record(fixture_id="test:replay:duplicate:one:v1"),
                _replay_record(fixture_id="test:replay:duplicate:two:v1"),
            ),
        )
    assert error.value.code is ProviderErrorCode.FIXTURE_CONFLICT


def test_replay_rejects_integrity_mismatch():
    with pytest.raises(ProviderContractError) as error:
        ReplayTransport(
            REPLAY_PROVIDER_ID,
            (_replay_record(integrity_hash="0" * 64),),
        )
    assert error.value.code is ProviderErrorCode.REPLAY_INTEGRITY_FAILURE


def test_replay_rejects_malformed_fixture():
    malformed = ReplayRecord(
        fixture_id="x",
        provider_id=REPLAY_PROVIDER_ID,
        operation="quotes.get",
        params={"symbol": "AAPL"},
        response_data={},
    )
    with pytest.raises(ProviderContractError) as error:
        ReplayTransport(REPLAY_PROVIDER_ID, (malformed,))
    assert error.value.code is ProviderErrorCode.INVALID_RESPONSE


def test_transport_registry_is_closed_and_duplicate_safe():
    catalog = FixtureCatalog()
    registry = TransportRegistry()
    transport = MockTransport(MOCK_PROVIDER_ID, catalog.resolve)
    registry.register("mock", transport)
    assert registry.get("mock") is transport
    with pytest.raises(ProviderContractError) as duplicate:
        registry.register("mock", transport)
    assert duplicate.value.code is ProviderErrorCode.FIXTURE_CONFLICT
    with pytest.raises(ProviderContractError) as unavailable:
        registry.get("replay")
    assert unavailable.value.code is ProviderErrorCode.TRANSPORT_UNAVAILABLE


def test_execution_succeeds_when_socket_creation_is_blocked(service, monkeypatch):
    def blocked_socket(*_args, **_kwargs):
        raise AssertionError("network socket creation is forbidden")

    monkeypatch.setattr(socket, "socket", blocked_socket)
    response = service.dispatch(request_payload(key="test:network:block:v1"))
    assert response["ok"] is True
    assert response["response"]["transport"] == "mock"
    assert response["NETWORK_TRANSPORT_DISABLED"] is True


def test_sdk_and_dynamic_import_isolation_scan(service):
    scan = service.transport_isolation_scan()
    assert scan["ok"] is True
    assert scan["broker_sdk_imports"] == 0
    assert scan["dynamic_provider_imports"] == 0
    assert scan["runtime_sdk_import_attempted"] is False
    assert scan["runtime_registry"]["dynamic_imports"] is False


def test_session_required_lifecycle_transitions():
    mock = ProviderSession("test.mock.session", TransportKind.MOCK)
    assert mock.transition(SessionState.MOCK_READY)["state"] == "MOCK_READY"
    assert mock.transition(SessionState.CLOSED)["state"] == "CLOSED"

    replay = ProviderSession("test.replay.session", TransportKind.REPLAY)
    assert replay.transition(SessionState.REPLAY_READY)["state"] == "REPLAY_READY"
    assert replay.transition(SessionState.FAULTED)["state"] == "FAULTED"
    assert replay.transition(SessionState.CLOSED)["state"] == "CLOSED"

    unavailable = ProviderSession("test.unavailable.session", TransportKind.MOCK)
    unavailable.transition(SessionState.UNAVAILABLE)
    assert unavailable.transition(SessionState.FAULTED)["state"] == "FAULTED"


@pytest.mark.parametrize("forbidden", sorted(FORBIDDEN_SESSION_STATES))
def test_forbidden_session_states_fail_closed(forbidden):
    session = ProviderSession("test.forbidden.session", TransportKind.MOCK)
    with pytest.raises(ProviderContractError) as error:
        session.transition(forbidden)  # type: ignore[arg-type]
    assert error.value.code is ProviderErrorCode.INVALID_SESSION_STATE
    assert session.state is SessionState.DISCONNECTED


def test_closed_session_is_terminal():
    session = ProviderSession("test.closed.session", TransportKind.MOCK)
    session.transition(SessionState.CLOSED)
    with pytest.raises(ProviderContractError) as error:
        session.transition(SessionState.FAULTED)
    assert error.value.code is ProviderErrorCode.INVALID_SESSION_STATE


def test_idempotency_is_stable_across_fresh_provider_instances():
    payload = request_payload(key="test:restart:idempotency:v1")
    first = DeterministicMockProvider().request(validate_request_payload(payload))
    second = DeterministicMockProvider().request(validate_request_payload(payload))
    assert first.to_dict() == second.to_dict()
    assert all(first.to_dict()[key] is False for key in HARD_AUTHORITY_KEYS)


def test_governance_deny_overrides_allow_and_approval_does_not_activate(service):
    from saathi.platform.tg.connectivity_governance.authority import (
        prove_deny_overrides_allow,
    )

    assert prove_deny_overrides_allow()["deny_overrides_allow"] is True
    draft = service.governance.create_approval(
        requestor="m327_requestor",
        approval_type="provider_documentation_review",
        provider="prov_mock_contract",
        environment="governance",
        capability_scope=["offline_fixture_access"],
        operation_scope=["documentation_review"],
        jurisdiction="N/A",
        expiry_time=9_999_999_999,
        allowed_network_destinations=["localhost"],
        evidence_requirements=["provider_contract_charter"],
        revocation_conditions=["operator_request"],
        acknowledgements=["offline_only", "no_activation"],
    )
    approval_id = draft["approval"]["approval_id"]
    service.governance.submit_approval(approval_id, actor="m327_requestor")
    approved = service.governance.review_approval(
        approval_id,
        approver="m327_approver",
        decision="approve",
    )
    assert approved["activates_connectivity"] is False
    assert service.list_providers()["any_connected"] is False


def test_llm_cannot_activate_provider_capability(service):
    security = service.governance.security_scan()
    assert security["llm_authority_scan"] == {
        "llm_may_approve": False,
        "llm_may_activate": False,
    }
    negotiation = service.negotiate(MOCK_PROVIDER_ID, ["quotes"])
    assert negotiation["granted"] == ["quotes"]
    assert negotiation["real_connectivity"] is False
    assert negotiation["executes"] is False
    assert negotiation["REAL_CONNECTIVITY_AUTHORIZED"] is False


def test_charter_non_implication_chain_and_isolation_assertions(service):
    charter = service.charter()
    assert charter["contract_presence_grants_authority"] is False
    assert charter["capability_declaration_grants_permission"] is False
    assert charter["permission_activates_connectivity"] is False
    assert charter["connectivity_grants_account_access"] is False
    assert charter["account_access_grants_order_authority"] is False
    assert all(charter[key] is True for key in ISOLATION_ASSERTIONS)


def test_provider_independent_error_model_is_complete():
    assert {
        "invalid_request",
        "invalid_response",
        "unsupported_capability",
        "capability_forbidden",
        "provider_unavailable",
        "transport_unavailable",
        "fixture_missing",
        "fixture_conflict",
        "timeout_simulation",
        "replay_integrity_failure",
        "invalid_session_state",
        "idempotency_conflict",
    } <= {code.value for code in ProviderErrorCode}


def test_cli_offline_contract_journey(service, capsys):
    from saathi.platform.tg.cli import main

    assert main(["pc-charter"]) == 0
    charter = json.loads(capsys.readouterr().out)
    assert charter["NETWORK_TRANSPORT_DISABLED"] is True

    assert main(["pc-mock-quote"]) == 0
    mock = json.loads(capsys.readouterr().out)
    assert mock["response"]["data"]["source_type"] == "MOCK"

    assert main(["pc-replay-fixtures"]) == 0
    replay = json.loads(capsys.readouterr().out)
    assert replay["count"] == 6
    assert all(item["integrity_valid"] for item in replay["fixtures"])

    assert main(["pc-certify"]) == 0
    certification = json.loads(capsys.readouterr().out)
    assert certification["verdict"] == TERMINAL_VERDICT
    assert certification["ok"] is True


def test_api_rejects_malformed_and_forbidden_requests(api_client):
    client, headers = api_client
    malformed = client.post(
        "/api/v1/platform/tg/provider-contracts/requests",
        headers=headers,
        json=request_payload(
            params={"symbol": "AAPL", "unexpected": True},
            key="api:malformed:params:v1",
        ),
    ).json()
    assert malformed["ok"] is False
    assert malformed["error"]["code"] == "invalid_request"

    forbidden = client.post(
        "/api/v1/platform/tg/provider-contracts/requests",
        headers=headers,
        json=request_payload(
            operation="orders.submit",
            params={},
            key="api:forbidden:order:v1",
        ),
    ).json()
    assert forbidden["ok"] is False
    assert forbidden["error"]["code"] == "capability_forbidden"
