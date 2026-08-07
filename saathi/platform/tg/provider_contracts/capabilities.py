"""Offline capability contracts and negotiation."""
from __future__ import annotations

from typing import Any, Iterable

from saathi.platform.tg.provider_contracts.errors import (
    ProviderContractError,
    ProviderErrorCode,
)
from saathi.platform.tg.provider_contracts.models import (
    MOCK_PROVIDER_ID,
    REPLAY_PROVIDER_ID,
    Capability,
    CapabilityAccess,
    CapabilityContract,
)

CAPABILITY_CONTRACTS = (
    CapabilityContract(
        Capability.QUOTES,
        CapabilityAccess.SUPPORTED_OFFLINE,
        ("quotes.get",),
        "synthetic_public_market_fixture",
        "Deterministic synthetic quote fixtures only",
    ),
    CapabilityContract(
        Capability.CANDLES,
        CapabilityAccess.SUPPORTED_OFFLINE,
        ("candles.list",),
        "synthetic_public_market_fixture",
        "Deterministic synthetic candle fixtures only",
    ),
    CapabilityContract(
        Capability.TRADES,
        CapabilityAccess.SUPPORTED_OFFLINE,
        ("trades.list",),
        "synthetic_public_market_fixture",
        "Deterministic paginated synthetic trade fixtures only",
    ),
    CapabilityContract(
        Capability.ORDERBOOK,
        CapabilityAccess.SUPPORTED_OFFLINE,
        ("orderbook.get",),
        "synthetic_public_market_fixture",
        "Deterministic synthetic orderbook fixtures only",
    ),
    CapabilityContract(
        Capability.SYMBOLS,
        CapabilityAccess.SUPPORTED_OFFLINE,
        ("symbols.list",),
        "synthetic_public_reference_fixture",
        "Deterministic paginated synthetic symbol fixtures only",
    ),
    CapabilityContract(
        Capability.MARKET_STATUS,
        CapabilityAccess.SUPPORTED_OFFLINE,
        ("market_status.get",),
        "synthetic_public_market_fixture",
        "Deterministic synthetic market-status fixtures only",
    ),
    CapabilityContract(
        Capability.POSITIONS,
        CapabilityAccess.FORBIDDEN_BY_GOVERNANCE,
        ("positions.list",),
        "account_private",
        "Interface contract only; position access is not authorized",
    ),
    CapabilityContract(
        Capability.BALANCES,
        CapabilityAccess.FORBIDDEN_BY_GOVERNANCE,
        ("balances.list",),
        "account_private",
        "Interface contract only; balance access is not authorized",
    ),
    CapabilityContract(
        Capability.ORDERS,
        CapabilityAccess.FORBIDDEN_BY_GOVERNANCE,
        ("orders.list", "orders.submit"),
        "execution_private",
        "Order access and submission are prohibited",
    ),
    CapabilityContract(
        Capability.TRANSFERS,
        CapabilityAccess.FORBIDDEN_BY_GOVERNANCE,
        ("transfers.create",),
        "funds_movement",
        "Transfers are prohibited",
    ),
)

CONTRACT_BY_CAPABILITY = {contract.name: contract for contract in CAPABILITY_CONTRACTS}


def capability_catalog() -> dict[str, Any]:
    return {
        "ok": True,
        "capabilities": [contract.to_dict() for contract in CAPABILITY_CONTRACTS],
        "supported_offline": [
            contract.name.value
            for contract in CAPABILITY_CONTRACTS
            if contract.access is CapabilityAccess.SUPPORTED_OFFLINE
        ],
        "unsupported": [
            contract.name.value
            for contract in CAPABILITY_CONTRACTS
            if contract.access is CapabilityAccess.UNSUPPORTED
        ],
        "forbidden_by_governance": [
            contract.name.value
            for contract in CAPABILITY_CONTRACTS
            if contract.access is CapabilityAccess.FORBIDDEN_BY_GOVERNANCE
        ],
        "denied": [
            contract.name.value
            for contract in CAPABILITY_CONTRACTS
            if contract.access is not CapabilityAccess.SUPPORTED_OFFLINE
        ],
        "unavailable": [
            contract.name.value
            for contract in CAPABILITY_CONTRACTS
            if contract.access is CapabilityAccess.UNAVAILABLE
        ],
        "known_states": [state.value for state in CapabilityAccess],
        "negotiation_only": True,
        "executes": False,
    }


def negotiate_capabilities(provider_id: str, requested: Iterable[str]) -> dict[str, Any]:
    if provider_id not in (MOCK_PROVIDER_ID, REPLAY_PROVIDER_ID):
        raise ProviderContractError(
            ProviderErrorCode.PROVIDER_UNAVAILABLE,
            "Offline provider is unavailable",
            details={"provider_id": provider_id},
        )
    names = list(requested)
    if not names:
        raise ProviderContractError(
            ProviderErrorCode.INVALID_REQUEST,
            "At least one capability must be requested",
        )
    if len(names) != len(set(names)):
        raise ProviderContractError(
            ProviderErrorCode.INVALID_REQUEST,
            "Capabilities must be unique",
        )

    decisions = []
    for name in names:
        try:
            capability = Capability(name)
        except ValueError as exc:
            raise ProviderContractError(
                ProviderErrorCode.UNSUPPORTED_CAPABILITY,
                "Unknown provider capability",
                details={"capability": name},
            ) from exc
        contract = CONTRACT_BY_CAPABILITY[capability]
        decisions.append({
            **contract.to_dict(),
            "granted": contract.access is CapabilityAccess.SUPPORTED_OFFLINE,
        })
    return {
        "ok": True,
        "provider_id": provider_id,
        "requested": names,
        "decisions": decisions,
        "granted": [item["name"] for item in decisions if item["granted"]],
        "denied": [item["name"] for item in decisions if not item["granted"]],
        "negotiation_only": True,
        "executes": False,
        "real_connectivity": False,
    }


def require_offline_capability(capability: Capability) -> None:
    contract = CONTRACT_BY_CAPABILITY[capability]
    if contract.access is CapabilityAccess.FORBIDDEN_BY_GOVERNANCE:
        raise ProviderContractError(
            ProviderErrorCode.CAPABILITY_FORBIDDEN,
            contract.reason,
            details={"capability": capability.value, "access": contract.access.value},
        )
    if contract.access is CapabilityAccess.UNSUPPORTED:
        raise ProviderContractError(
            ProviderErrorCode.UNSUPPORTED_CAPABILITY,
            contract.reason,
            details={"capability": capability.value, "access": contract.access.value},
        )
    if contract.access is CapabilityAccess.UNAVAILABLE:
        raise ProviderContractError(
            ProviderErrorCode.PROVIDER_UNAVAILABLE,
            contract.reason,
            details={"capability": capability.value, "access": contract.access.value},
        )
