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
    return descriptor


def validate_response(response: ProviderResponse) -> ProviderResponse:
    if response.schema_version != SCHEMA_VERSION:
        raise ProviderContractError(
            ProviderErrorCode.CONTRACT_VIOLATION,
            "Unsupported response schema version",
        )
    if response.status is ResponseStatus.OK and response.error is not None:
        raise ProviderContractError(
            ProviderErrorCode.CONTRACT_VIOLATION,
            "Successful response cannot contain an error",
        )
    if response.status is ResponseStatus.ERROR and response.error is None:
        raise ProviderContractError(
            ProviderErrorCode.CONTRACT_VIOLATION,
            "Error response must contain normalized error details",
        )
    return response
