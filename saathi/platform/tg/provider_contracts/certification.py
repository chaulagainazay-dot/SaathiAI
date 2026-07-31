"""M327 hard-gate certification for credentialless provider contracts."""
from __future__ import annotations

from typing import Any, TYPE_CHECKING

from saathi.platform.tg.connectivity_governance.storage import evidence_hash
from saathi.platform.tg.provider_contracts.contracts import (
    AccountProvider,
    OrderProvider,
)
from saathi.platform.tg.provider_contracts.errors import ProviderContractError
from saathi.platform.tg.provider_contracts.models import (
    AUTHORITY_LOCKS,
    BOUNDARY_VALUES,
    BROWSER_CERT_VERDICT,
    CURRENT_MATURITY,
    MAX_STATE,
    MOCK_PROVIDER_ID,
    REPLAY_PROVIDER_ID,
    TERMINAL_STATEMENTS,
    TERMINAL_VERDICT,
    authority_locks_intact,
)

if TYPE_CHECKING:
    from saathi.platform.tg.provider_contracts.service import ProviderContractService


def certify_provider_contracts(service: "ProviderContractService") -> dict[str, Any]:
    checks: dict[str, bool] = {}
    failures: list[str] = []

    checks["authority_locks_false"] = authority_locks_intact()
    checks["account_contract_abstract"] = bool(AccountProvider.__abstractmethods__)
    checks["order_contract_abstract"] = bool(OrderProvider.__abstractmethods__)
    checks["no_account_provider_implementation"] = not isinstance(
        service.mock_provider,
        AccountProvider,
    )
    checks["no_order_provider_implementation"] = not isinstance(
        service.mock_provider,
        OrderProvider,
    )

    providers = service.list_providers()
    checks["provider_contracts_valid"] = (
        providers["count"] == 2
        and providers["any_real"] is False
        and providers["any_connected"] is False
        and providers["any_authenticated"] is False
    )
    checks["transport_allowlist_exact"] = {
        provider["transport"] for provider in providers["providers"]
    } == {"mock", "replay"}

    capability = service.negotiate(
        MOCK_PROVIDER_ID,
        ["quotes", "candles", "orderbook", "positions", "balances", "orders", "transfers"],
    )
    checks["capability_negotiation_only"] = (
        capability["negotiation_only"] is True
        and capability["executes"] is False
    )
    checks["sensitive_capabilities_denied"] = set(capability["denied"]) == {
        "positions",
        "balances",
        "orders",
        "transfers",
    }

    mock_payload = {
        "provider_id": MOCK_PROVIDER_ID,
        "operation": "quotes.get",
        "params": {"symbol": "AAPL"},
        "idempotency_key": "cert:mock:quote:AAPL:v1",
    }
    mock_first = service.dispatch(mock_payload)
    mock_second = service.dispatch(mock_payload)
    checks["mock_deterministic"] = mock_first == mock_second
    checks["mock_schema_valid"] = (
        mock_first["response"]["status"] == "ok"
        and mock_first["response"]["transport"] == "mock"
        and mock_first["response"]["data"]["synthetic"] is True
        and mock_first["response"]["real_connectivity"] is False
    )

    replay_payload = {
        "provider_id": REPLAY_PROVIDER_ID,
        "operation": "quotes.get",
        "params": {"symbol": "AAPL"},
        "idempotency_key": "cert:replay:quote:AAPL:v1",
    }
    replay_first = service.dispatch(replay_payload)
    replay_second = service.dispatch(replay_payload)
    checks["replay_deterministic"] = replay_first == replay_second
    checks["replay_fixture_bound"] = (
        replay_first["response"]["transport"] == "replay"
        and replay_first["response"]["fixture_id"].startswith("replay:")
    )

    malformed = service.request({
        "provider_id": MOCK_PROVIDER_ID,
        "operation": "quotes.get",
        "params": {"api_key": "forbidden"},
        "idempotency_key": "cert:malformed:request:v1",
    })
    checks["malformed_payload_rejected"] = (
        malformed["ok"] is False
        and malformed["error"]["code"] == "invalid_request"
    )

    denied = service.request({
        "provider_id": MOCK_PROVIDER_ID,
        "operation": "balances.list",
        "params": {},
        "idempotency_key": "cert:denied:balances:v1",
    })
    checks["capability_denied_normalized"] = (
        denied["ok"] is False
        and denied["error"]["code"] == "capability_denied"
    )

    replay_miss = service.request({
        "provider_id": REPLAY_PROVIDER_ID,
        "operation": "quotes.get",
        "params": {"symbol": "BTC-USD"},
        "idempotency_key": "cert:replay:miss:BTC-USD:v1",
    })
    checks["replay_miss_normalized"] = (
        replay_miss["ok"] is False
        and replay_miss["error"]["code"] == "replay_miss"
    )

    conflict_payload = {
        "provider_id": MOCK_PROVIDER_ID,
        "operation": "quotes.get",
        "params": {"symbol": "BTC-USD"},
        "idempotency_key": mock_payload["idempotency_key"],
    }
    try:
        service.dispatch(conflict_payload)
    except ProviderContractError as exc:
        checks["idempotency_conflict_rejected"] = exc.code.value == "idempotency_conflict"
    else:
        checks["idempotency_conflict_rejected"] = False

    sessions = service.sessions()
    checks["session_states_credentialless"] = (
        sessions["authentication_state_exists"] is False
        and all(session["authenticated"] is False for session in sessions["sessions"])
        and {session["state"] for session in sessions["sessions"]}
        == {"mock_ready", "replay_ready"}
    )

    security = service.security_scan()
    checks["transport_isolation"] = security["transport_isolation"]["ok"] is True
    checks["security_scan"] = security["ok"] is True
    checks["governance_composed"] = (
        service.posture()["governance_binding"]["registered"] is True
    )

    for name, passed in checks.items():
        if not passed:
            failures.append(name)
    ok = not failures
    verdict = TERMINAL_VERDICT if ok else "PROVIDER_CONTRACTS_NOT_CERTIFIED"
    result = {
        "ok": ok,
        "verdict": verdict,
        "max_state": MAX_STATE,
        "current_maturity": CURRENT_MATURITY,
        "browser_cert_verdict_target": BROWSER_CERT_VERDICT,
        "checks": checks,
        "failures": failures,
        "statements": list(TERMINAL_STATEMENTS),
        "limitations": [
            "Deterministic mock and replay fixtures only",
            "No HTTP, WebSocket, REST client, or broker SDK",
            "No credentials, OAuth, login, or authentication",
            "No account, balance, or position access",
            "No order submission, paper execution, or live execution",
            "No canary, deployment, or production authority",
        ],
        **BOUNDARY_VALUES,
    }
    result["evidence_hash"] = evidence_hash(result)
    service.governance.store.audit(
        "provider_contracts_certify",
        "system",
        "M320-M327",
        {"verdict": verdict, "ok": ok, "evidence_hash": result["evidence_hash"]},
    )
    return result
