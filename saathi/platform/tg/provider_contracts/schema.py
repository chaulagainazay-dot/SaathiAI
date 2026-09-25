"""Strict schema validation for offline requests, responses, and descriptors."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from saathi.platform.tg.provider_contracts.errors import (
    ProviderContractError,
    ProviderErrorCode,
)
from saathi.platform.tg.provider_contracts.models import (
    FORBIDDEN_REQUEST_FIELDS,
    IDENTIFIER_RE,
    IDEMPOTENCY_RE,
    OPERATION_CAPABILITIES,
    SCHEMA_VERSION,
    CapabilityContract,
    ProviderDescriptor,
    ProviderRequest,
    ProviderResponse,
    ResponseStatus,
)

REQUEST_FIELDS = frozenset({
    "provider_id",
    "operation",
    "params",
    "idempotency_key",
    "schema_version",
})
SIMULATION_FIELDS = frozenset({"simulate_error", "simulated_latency_ms"})
OPERATION_PARAM_FIELDS = {
    "quotes.get": frozenset({"symbol"}) | SIMULATION_FIELDS,
    "candles.list": frozenset({"symbol", "interval"}) | SIMULATION_FIELDS,
    "trades.list": frozenset({"symbol", "cursor", "limit"}) | SIMULATION_FIELDS,
    "orderbook.get": frozenset({"symbol"}) | SIMULATION_FIELDS,
    "symbols.list": frozenset({"cursor", "limit"}) | SIMULATION_FIELDS,
    "market_status.get": frozenset({"venue"}) | SIMULATION_FIELDS,
    "positions.list": frozenset(),
    "balances.list": frozenset(),
    "orders.list": frozenset(),
    "orders.submit": frozenset(),
    "transfers.create": frozenset(),
}
REQUIRED_OPERATION_FIELDS = {
    "quotes.get": frozenset({"symbol"}),
    "candles.list": frozenset({"symbol", "interval"}),
    "trades.list": frozenset({"symbol"}),
    "orderbook.get": frozenset({"symbol"}),
    "market_status.get": frozenset({"venue"}),
}
PROVENANCE_FIELDS = {
    "source_type": str,
    "live": bool,
    "synthetic": bool,
    "account_derived": bool,
    "execution_capable": bool,
}


def _invalid(message: str, **details: Any) -> ProviderContractError:
    return ProviderContractError(
        ProviderErrorCode.INVALID_REQUEST,
        message,
        details=details,
    )


def _scan_forbidden(value: Any, path: str = "params") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            key_text = str(key).lower()
            if key_text in FORBIDDEN_REQUEST_FIELDS:
                raise _invalid("Forbidden request field", field=f"{path}.{key_text}")
            _scan_forbidden(child, f"{path}.{key_text}")
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _scan_forbidden(child, f"{path}[{index}]")


def validate_request_payload(payload: Mapping[str, Any]) -> ProviderRequest:
    if not isinstance(payload, Mapping):
        raise _invalid("Request must be an object")
    unknown = sorted(set(payload) - REQUEST_FIELDS)
    if unknown:
        raise _invalid("Unknown request fields", fields=unknown)
    missing = sorted(
        field for field in ("provider_id", "operation", "params", "idempotency_key")
        if field not in payload
    )
    if missing:
        raise _invalid("Missing request fields", fields=missing)

    provider_id = payload.get("provider_id")
    operation = payload.get("operation")
    params = payload.get("params")
    idempotency_key = payload.get("idempotency_key")
    schema_version = payload.get("schema_version", SCHEMA_VERSION)

    if not isinstance(provider_id, str) or not IDENTIFIER_RE.fullmatch(provider_id):
        raise _invalid("Invalid provider_id")
    if not isinstance(operation, str) or operation not in OPERATION_CAPABILITIES:
        raise _invalid("Unknown provider operation", operation=operation)
    if not isinstance(params, Mapping):
        raise _invalid("params must be an object")
    if not isinstance(idempotency_key, str) or not IDEMPOTENCY_RE.fullmatch(idempotency_key):
        raise _invalid("Invalid idempotency_key")
    if schema_version != SCHEMA_VERSION:
        raise _invalid(
            "Unsupported request schema version",
            expected=SCHEMA_VERSION,
            actual=schema_version,
        )
    _scan_forbidden(params)
    allowed_params = OPERATION_PARAM_FIELDS[operation]
    unknown_params = sorted(set(params) - allowed_params)
    if unknown_params:
        raise _invalid(
            "Unknown operation parameters",
            operation=operation,
            fields=unknown_params,
        )
    missing_params = sorted(REQUIRED_OPERATION_FIELDS.get(operation, frozenset()) - set(params))
    if missing_params:
        raise _invalid(
            "Missing operation parameters",
            operation=operation,
            fields=missing_params,
        )
    return ProviderRequest(
        provider_id=provider_id,
        operation=operation,
        params=dict(params),
        idempotency_key=idempotency_key,
        schema_version=schema_version,
    )


def validate_descriptor(descriptor: ProviderDescriptor) -> ProviderDescriptor:
    if not IDENTIFIER_RE.fullmatch(descriptor.provider_id):
        raise ProviderContractError(
            ProviderErrorCode.CONTRACT_VIOLATION,
            "Invalid provider descriptor identifier",
        )
    if descriptor.authenticated or not descriptor.credentialless:
        raise ProviderContractError(
            ProviderErrorCode.CONTRACT_VIOLATION,
            "Provider descriptor must remain credentialless",
        )
    if descriptor.network_enabled or descriptor.real_provider:
        raise ProviderContractError(
            ProviderErrorCode.TRANSPORT_FORBIDDEN,
            "Real provider transport is forbidden",
        )
    if not descriptor.capabilities or len(descriptor.capabilities) != len(set(descriptor.capabilities)):
        raise ProviderContractError(
            ProviderErrorCode.INVALID_RESPONSE,
            "Provider descriptor capabilities must be non-empty and unique",
        )
    return descriptor


def validate_capability_contract(contract: CapabilityContract) -> CapabilityContract:
    if not contract.operations:
        raise ProviderContractError(
            ProviderErrorCode.INVALID_RESPONSE,
            "Capability contract requires at least one operation",
        )
    expected = {
        operation
        for operation, capability in OPERATION_CAPABILITIES.items()
        if capability is contract.name
    }
    if set(contract.operations) != expected:
        raise ProviderContractError(
            ProviderErrorCode.INVALID_RESPONSE,
            "Capability contract operations do not match the provider-neutral schema",
            details={"capability": contract.name.value},
        )
    if not contract.reason or not contract.data_class:
        raise ProviderContractError(
            ProviderErrorCode.INVALID_RESPONSE,
            "Capability contract metadata is malformed",
        )
    return contract


def validate_response(response: ProviderResponse) -> ProviderResponse:
    if response.schema_version != SCHEMA_VERSION:
        raise ProviderContractError(
            ProviderErrorCode.INVALID_RESPONSE,
            "Unsupported response schema version",
        )
    if response.status is ResponseStatus.OK and response.error is not None:
        raise ProviderContractError(
            ProviderErrorCode.INVALID_RESPONSE,
            "Successful response cannot contain an error",
        )
    if response.status is ResponseStatus.ERROR and response.error is None:
        raise ProviderContractError(
            ProviderErrorCode.INVALID_RESPONSE,
            "Error response must contain normalized error details",
        )
    if response.status is ResponseStatus.OK:
        for field, expected_type in PROVENANCE_FIELDS.items():
            value = response.data.get(field)
            if not isinstance(value, expected_type):
                raise ProviderContractError(
                    ProviderErrorCode.INVALID_RESPONSE,
                    "Response provenance is missing or malformed",
                    details={"field": field},
                )
        expected_source = "MOCK" if response.transport.value == "mock" else "REPLAY"
        if (
            response.data.get("source_type") != expected_source
            or response.data.get("live") is not False
            or response.data.get("synthetic") is not True
            or response.data.get("account_derived") is not False
            or response.data.get("execution_capable") is not False
        ):
            raise ProviderContractError(
                ProviderErrorCode.INVALID_RESPONSE,
                "Response provenance violates offline-only policy",
            )
    if response.status is ResponseStatus.ERROR:
        validate_error_envelope(response.error or {})
    return response


def validate_error_envelope(error: Mapping[str, Any]) -> Mapping[str, Any]:
    required = {"code", "message", "retryable", "details", "provider_independent"}
    if set(error) != required:
        raise ProviderContractError(
            ProviderErrorCode.INVALID_RESPONSE,
            "Normalized error envelope fields are invalid",
        )
    try:
        ProviderErrorCode(error["code"])
    except (TypeError, ValueError) as exc:
        raise ProviderContractError(
            ProviderErrorCode.INVALID_RESPONSE,
            "Normalized error code is invalid",
        ) from exc
    if (
        not isinstance(error["message"], str)
        or not isinstance(error["retryable"], bool)
        or not isinstance(error["details"], Mapping)
        or error["provider_independent"] is not True
    ):
        raise ProviderContractError(
            ProviderErrorCode.INVALID_RESPONSE,
            "Normalized error envelope is malformed",
        )
    return error


def validate_replay_fixture_payload(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    required = {
        "fixture_id",
        "provider_id",
        "operation",
        "params",
        "response_data",
        "recorded_response_hash",
    }
    if not isinstance(payload, Mapping) or set(payload) != required:
        raise ProviderContractError(
            ProviderErrorCode.INVALID_RESPONSE,
            "Replay fixture fields are invalid",
        )
    if (
        not isinstance(payload["fixture_id"], str)
        or not IDENTIFIER_RE.fullmatch(payload["fixture_id"])
        or not isinstance(payload["provider_id"], str)
        or not IDENTIFIER_RE.fullmatch(payload["provider_id"])
        or payload["operation"] not in OPERATION_CAPABILITIES
        or not isinstance(payload["params"], Mapping)
        or not isinstance(payload["response_data"], Mapping)
        or not isinstance(payload["recorded_response_hash"], str)
        or len(payload["recorded_response_hash"]) != 64
    ):
        raise ProviderContractError(
            ProviderErrorCode.INVALID_RESPONSE,
            "Replay fixture is malformed",
        )
    _scan_forbidden(payload["params"], "fixture.params")
    return payload
