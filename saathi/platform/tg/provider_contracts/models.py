"""M320–M327 provider contract models.

Credentialless and offline-only. This module grants no provider, account, order,
credential, OAuth, canary, deployment, or live-trading authority.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from saathi.platform.tg.connectivity_governance.models import (
    AUTHORITY_VALUES as GOVERNANCE_AUTHORITY_VALUES,
)

SCHEMA_VERSION = "m320.provider_contracts.v1"
ENGINE_VERSION = "m320.provider_contracts.engine.v1"
TERMINAL_VERDICT = "PROVIDER_CONTRACTS_AND_MOCK_CONNECTIVITY_CERTIFIED_WITH_LIMITATIONS"
MAX_STATE = "MOCK_PROVIDER_READY_NO_REAL_CONNECTIVITY"
CURRENT_MATURITY = "MOCK_CONNECTIVITY_ONLY"
BROWSER_CERT_VERDICT = (
    "PROVIDER_CONTRACTS_MOCK_CONNECTIVITY_BROWSER_CERT_PASSED_WITH_LIMITATIONS"
)

MOCK_PROVIDER_ID = "saathi.mock.market.v1"
REPLAY_PROVIDER_ID = "saathi.replay.market.v1"

HARD_AUTHORITY_KEYS = (
    "REAL_CONNECTIVITY_AUTHORIZED",
    "BROKER_CONNECTIVITY_AUTHORIZED",
    "OAUTH_AUTHORIZED",
    "CREDENTIAL_PROVISIONING_AUTHORIZED",
    "CREDENTIAL_VALIDATION_AUTHORIZED",
    "AUTHENTICATION_AUTHORIZED",
    "ACCOUNT_ACCESS_AUTHORIZED",
    "BALANCE_READ_AUTHORIZED",
    "POSITION_READ_AUTHORIZED",
    "ORDER_HISTORY_AUTHORIZED",
    "ORDER_SUBMISSION_AUTHORIZED",
    "ORDER_EXECUTION_AUTHORIZED",
    "TRANSFER_AUTHORIZED",
    "WITHDRAWAL_AUTHORIZED",
    "CANARY_ACTIVATION_AUTHORIZED",
    "LIVE_TRADING_AUTHORIZED",
    "AUTOMATED_INVESTMENT_AUTHORITY",
)

AUTHORITY_LOCKS = {key: False for key in HARD_AUTHORITY_KEYS}
ISOLATION_ASSERTIONS = {
    "NO_REAL_PROVIDER_CONNECTION": True,
    "NO_REAL_CREDENTIALS": True,
    "NO_ACCOUNT_ACCESS": True,
    "NO_ORDER_EXECUTION": True,
    "MOCK_DATA_ONLY": True,
    "REPLAY_DATA_ONLY": True,
    "NETWORK_TRANSPORT_DISABLED": True,
}
BOUNDARY_VALUES = {
    **AUTHORITY_LOCKS,
    **ISOLATION_ASSERTIONS,
    "CREDENTIAL_STORAGE_AUTHORIZED": False,
    "READ_ONLY_PRODUCTION_AUTHORIZED": False,
    "EXTERNAL_PAPER_EXECUTION_AUTHORIZED": False,
    "ORDER_MODIFICATION_AUTHORIZED": False,
    "ORDER_CANCELLATION_AUTHORIZED": False,
    "TRANSFER_AUTHORIZED": False,
    "WITHDRAWAL_AUTHORIZED": False,
    "PRODUCTION_AUTHORIZED": False,
    "API_KEYS_ACCEPTED": False,
    "real_connectivity": False,
    "authenticated": False,
    "credentials_present": False,
    "network_transport_available": False,
    "offline_only": True,
    "mock_only": True,
    "replay_only": True,
    "current_maturity": CURRENT_MATURITY,
    "max_state": MAX_STATE,
}

FORBIDDEN_REQUEST_FIELDS = frozenset({
    "account",
    "account_id",
    "api_key",
    "api_secret",
    "access_token",
    "refresh_token",
    "bearer_token",
    "client_secret",
    "credential",
    "credentials",
    "oauth",
    "order",
    "password",
    "passphrase",
    "position",
    "private_key",
    "secret",
    "session_cookie",
    "token",
})

IDENTIFIER_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._:/-]{2,127}$")
IDEMPOTENCY_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._:-]{7,127}$")


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def authority_locks_intact() -> bool:
    return all(
        GOVERNANCE_AUTHORITY_VALUES.get(key, False) is False
        and AUTHORITY_LOCKS[key] is False
        for key in HARD_AUTHORITY_KEYS
    )


class Capability(str, Enum):
    QUOTES = "quotes"
    CANDLES = "candles"
    TRADES = "trades"
    ORDERBOOK = "orderbook"
    SYMBOLS = "symbols"
    MARKET_STATUS = "market_status"
    POSITIONS = "positions"
    BALANCES = "balances"
    ORDERS = "orders"
    TRANSFERS = "transfers"


class CapabilityAccess(str, Enum):
    SUPPORTED_OFFLINE = "SUPPORTED_OFFLINE"
    UNSUPPORTED = "UNSUPPORTED"
    FORBIDDEN_BY_GOVERNANCE = "FORBIDDEN_BY_GOVERNANCE"
    UNAVAILABLE = "UNAVAILABLE"


class TransportKind(str, Enum):
    MOCK = "mock"
    REPLAY = "replay"


class SessionState(str, Enum):
    DISCONNECTED = "DISCONNECTED"
    MOCK_READY = "MOCK_READY"
    REPLAY_READY = "REPLAY_READY"
    UNAVAILABLE = "UNAVAILABLE"
    FAULTED = "FAULTED"
    CLOSED = "CLOSED"


class ResponseStatus(str, Enum):
    OK = "ok"
    ERROR = "error"


OPERATION_CAPABILITIES = {
    "quotes.get": Capability.QUOTES,
    "candles.list": Capability.CANDLES,
    "trades.list": Capability.TRADES,
    "orderbook.get": Capability.ORDERBOOK,
    "symbols.list": Capability.SYMBOLS,
    "market_status.get": Capability.MARKET_STATUS,
    "positions.list": Capability.POSITIONS,
    "balances.list": Capability.BALANCES,
    "orders.list": Capability.ORDERS,
    "orders.submit": Capability.ORDERS,
    "transfers.create": Capability.TRANSFERS,
}


@dataclass(frozen=True)
class CapabilityContract:
    name: Capability
    access: CapabilityAccess
    operations: tuple[str, ...]
    data_class: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name.value,
            "access": self.access.value,
            "operations": list(self.operations),
            "data_class": self.data_class,
            "reason": self.reason,
            "executes": False,
            "grants_authority": False,
            "activates_connectivity": False,
        }


@dataclass(frozen=True)
class ProviderDescriptor:
    provider_id: str
    display_name: str
    transport: TransportKind
    capabilities: tuple[Capability, ...]
    contract_version: str = SCHEMA_VERSION
    authenticated: bool = False
    credentialless: bool = True
    network_enabled: bool = False
    real_provider: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "display_name": self.display_name,
            "transport": self.transport.value,
            "capabilities": [capability.value for capability in self.capabilities],
            "contract_version": self.contract_version,
            "authenticated": self.authenticated,
            "credentialless": self.credentialless,
            "network_enabled": self.network_enabled,
            "real_provider": self.real_provider,
            "account_access": False,
            "order_execution": False,
            "connected": False,
            **ISOLATION_ASSERTIONS,
        }


@dataclass(frozen=True)
class ProviderRequest:
    provider_id: str
    operation: str
    params: Mapping[str, Any]
    idempotency_key: str
    schema_version: str = SCHEMA_VERSION

    @property
    def fingerprint(self) -> str:
        return digest({
            "provider_id": self.provider_id,
            "operation": self.operation,
            "params": dict(self.params),
            "schema_version": self.schema_version,
        })

    @property
    def request_id(self) -> str:
        return f"req_{digest({'fingerprint': self.fingerprint, 'key': self.idempotency_key})[:20]}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "operation": self.operation,
            "params": dict(self.params),
            "idempotency_key": self.idempotency_key,
            "schema_version": self.schema_version,
            "request_id": self.request_id,
            "fingerprint": self.fingerprint,
        }


@dataclass(frozen=True)
class ProviderResponse:
    provider_id: str
    request_id: str
    operation: str
    status: ResponseStatus
    data: Mapping[str, Any]
    error: Mapping[str, Any] | None
    transport: TransportKind
    fixture_id: str
    schema_version: str = SCHEMA_VERSION

    @property
    def response_hash(self) -> str:
        return digest({
            "provider_id": self.provider_id,
            "request_id": self.request_id,
            "operation": self.operation,
            "status": self.status.value,
            "data": dict(self.data),
            "error": dict(self.error) if self.error else None,
            "transport": self.transport.value,
            "fixture_id": self.fixture_id,
            "schema_version": self.schema_version,
        })

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "request_id": self.request_id,
            "operation": self.operation,
            "status": self.status.value,
            "data": dict(self.data),
            "error": dict(self.error) if self.error else None,
            "transport": self.transport.value,
            "fixture_id": self.fixture_id,
            "schema_version": self.schema_version,
            "response_hash": self.response_hash,
            "authenticated": False,
            "real_connectivity": False,
            "idempotent": True,
            **BOUNDARY_VALUES,
        }


TERMINAL_STATEMENTS = (
    "OFFLINE MOCK DATA",
    "NO PROVIDER CONNECTION",
    "NO ACCOUNT ACCESS",
    "NO ORDER EXECUTION",
    "NO REAL PROVIDER CONNECTION",
    "NO HTTP OR WEBSOCKET TRANSPORT",
    "NO CREDENTIALS OR OAUTH",
    "NO ACCOUNT, BALANCE, OR POSITION ACCESS",
    "NO ORDER SUBMISSION OR EXECUTION",
    "NO CANARY OR LIVE TRADING",
    "DETERMINISTIC MOCK AND REPLAY FIXTURES ONLY",
)
