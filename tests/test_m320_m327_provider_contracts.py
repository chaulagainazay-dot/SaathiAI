"""M320–M327 credentialless provider contract and mock/replay tests."""
from __future__ import annotations

import inspect
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
    MAX_STATE,
    MOCK_PROVIDER_ID,
    REPLAY_PROVIDER_ID,
    SCHEMA_VERSION,
    TERMINAL_VERDICT,
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
    validate_descriptor,
    validate_request_payload,
    validate_response,
)
from saathi.platform.tg.provider_contracts.service import (
    ProviderContractService,
    reset_provider_contracts_for_tests,
)
from saathi.platform.tg.provider_contracts.transport import reject_transport_kind


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
        ["quotes", "candles", "orderbook", "positions", "balances", "orders", "transfers"],
    )
    assert result["granted"] == ["quotes", "candles", "orderbook"]
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
    assert result["error"]["code"] == "unavailable"
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
        assert result["error"]["code"] == "capability_denied"


def test_idempotency_key_conflict_fails_closed(service):
    key = "test:idempotency:conflict:v1"
    service.dispatch(request_payload(key=key))
    with pytest.raises(ProviderContractError) as error:
        service.dispatch(request_payload(params={"symbol": "BTC-USD"}, key=key))
    assert error.value.code is ProviderErrorCode.IDEMPOTENCY_CONFLICT


def test_replay_manifest_contains_recorded_request_response_contract(service):
    manifest = service.replay_fixtures()
    assert manifest["count"] == 3
    assert manifest["deterministic"] is True
    assert manifest["network_capture"] is False
    for fixture in manifest["fixtures"]:
        assert fixture["recorded_request"]["provider_id"] == REPLAY_PROVIDER_ID
        assert len(fixture["recorded_response_hash"]) == 64
        assert fixture["credentialless"] is True


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
    assert result["error"]["code"] == "replay_miss"


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
    assert error.value.code is ProviderErrorCode.CONTRACT_VIOLATION


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
        "disconnected",
        "mock_ready",
        "replay_ready",
        "unavailable",
    }
    assert {item["state"] for item in sessions["sessions"]} == {
        "mock_ready",
        "replay_ready",
    }
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
    assert result["error"]["code"] == "session_unavailable"


@pytest.mark.parametrize("kind", ["http", "https", "websocket", "rest", "broker_sdk"])
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
