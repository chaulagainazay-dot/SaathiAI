"""Offline-only mock and replay transport abstractions.

No network transport class exists in this package.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from copy import deepcopy
from dataclasses import dataclass
from threading import RLock
from typing import Any, Callable, Iterable, Mapping

from saathi.platform.tg.provider_contracts.errors import (
    ProviderContractError,
    ProviderErrorCode,
)
from saathi.platform.tg.provider_contracts.models import (
    ProviderRequest,
    ProviderResponse,
    ResponseStatus,
    TransportKind,
    digest,
)
from saathi.platform.tg.provider_contracts.schema import validate_response

Resolver = Callable[[str, Mapping[str, Any]], tuple[str, dict[str, Any]]]


class ProviderTransport(ABC):
    network_enabled = False

    @property
    @abstractmethod
    def kind(self) -> TransportKind:
        raise NotImplementedError

    @abstractmethod
    def send(self, request: ProviderRequest) -> ProviderResponse:
        raise NotImplementedError


class _IdempotencyLedger:
    def __init__(self) -> None:
        self._entries: dict[str, tuple[str, ProviderResponse]] = {}
        self._lock = RLock()

    def lookup(self, request: ProviderRequest) -> ProviderResponse | None:
        with self._lock:
            existing = self._entries.get(request.idempotency_key)
            if existing is None:
                return None
            fingerprint, response = existing
            if fingerprint != request.fingerprint:
                raise ProviderContractError(
                    ProviderErrorCode.IDEMPOTENCY_CONFLICT,
                    "Idempotency key was already used for a different request",
                    details={"idempotency_key": request.idempotency_key},
                )
            return deepcopy(response)

    def save(self, request: ProviderRequest, response: ProviderResponse) -> ProviderResponse:
        with self._lock:
            existing = self.lookup(request)
            if existing is not None:
                return existing
            self._entries[request.idempotency_key] = (
                request.fingerprint,
                deepcopy(response),
            )
            return deepcopy(response)

    def size(self) -> int:
        with self._lock:
            return len(self._entries)


class MockTransport(ProviderTransport):
    def __init__(self, provider_id: str, resolver: Resolver):
        self.provider_id = provider_id
        self._resolver = resolver
        self._idempotency = _IdempotencyLedger()

    @property
    def kind(self) -> TransportKind:
        return TransportKind.MOCK

    def send(self, request: ProviderRequest) -> ProviderResponse:
        if request.provider_id != self.provider_id:
            raise ProviderContractError(
                ProviderErrorCode.INVALID_REQUEST,
                "Request provider does not match mock transport",
            )
        cached = self._idempotency.lookup(request)
        if cached is not None:
            return cached
        fixture_id, data = self._resolver(request.operation, request.params)
        response = validate_response(ProviderResponse(
            provider_id=request.provider_id,
            request_id=request.request_id,
            operation=request.operation,
            status=ResponseStatus.OK,
            data=data,
            error=None,
            transport=self.kind,
            fixture_id=fixture_id,
        ))
        return self._idempotency.save(request, response)

    def snapshot(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "network_enabled": False,
            "protocol": "in_process_fixture_resolver",
            "idempotency_entries": self._idempotency.size(),
        }


@dataclass(frozen=True)
class ReplayRecord:
    fixture_id: str
    provider_id: str
    operation: str
    params: Mapping[str, Any]
    response_data: Mapping[str, Any]

    @property
    def request_fingerprint(self) -> str:
        return digest({
            "provider_id": self.provider_id,
            "operation": self.operation,
            "params": dict(self.params),
        })

    @property
    def recorded_response_hash(self) -> str:
        return digest({
            "fixture_id": self.fixture_id,
            "response_data": dict(self.response_data),
        })

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixture_id": self.fixture_id,
            "recorded_request": {
                "provider_id": self.provider_id,
                "operation": self.operation,
                "params": dict(self.params),
            },
            "recorded_response_hash": self.recorded_response_hash,
            "credentialless": True,
            "network_capture": False,
        }


class ReplayTransport(ProviderTransport):
    def __init__(self, provider_id: str, records: Iterable[ReplayRecord]):
        self.provider_id = provider_id
        self._records: dict[str, ReplayRecord] = {}
        for record in records:
            if record.provider_id != provider_id:
                raise ProviderContractError(
                    ProviderErrorCode.CONTRACT_VIOLATION,
                    "Replay record provider mismatch",
                )
            if record.request_fingerprint in self._records:
                raise ProviderContractError(
                    ProviderErrorCode.CONTRACT_VIOLATION,
                    "Duplicate replay request fixture",
                )
            self._records[record.request_fingerprint] = record
        self._idempotency = _IdempotencyLedger()

    @property
    def kind(self) -> TransportKind:
        return TransportKind.REPLAY

    @staticmethod
    def _match_key(request: ProviderRequest) -> str:
        return digest({
            "provider_id": request.provider_id,
            "operation": request.operation,
            "params": dict(request.params),
        })

    def send(self, request: ProviderRequest) -> ProviderResponse:
        if request.provider_id != self.provider_id:
            raise ProviderContractError(
                ProviderErrorCode.INVALID_REQUEST,
                "Request provider does not match replay transport",
            )
        cached = self._idempotency.lookup(request)
        if cached is not None:
            return cached
        record = self._records.get(self._match_key(request))
        if record is None:
            raise ProviderContractError(
                ProviderErrorCode.REPLAY_MISS,
                "No recorded fixture matches the request",
                details={"operation": request.operation},
            )
        response = validate_response(ProviderResponse(
            provider_id=request.provider_id,
            request_id=request.request_id,
            operation=request.operation,
            status=ResponseStatus.OK,
            data=deepcopy(record.response_data),
            error=None,
            transport=self.kind,
            fixture_id=record.fixture_id,
        ))
        return self._idempotency.save(request, response)

    def manifest(self) -> list[dict[str, Any]]:
        return [
            record.to_dict()
            for record in sorted(self._records.values(), key=lambda item: item.fixture_id)
        ]

    def snapshot(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "network_enabled": False,
            "protocol": "recorded_fixture_replay",
            "fixture_count": len(self._records),
            "idempotency_entries": self._idempotency.size(),
        }


def reject_transport_kind(kind: str) -> None:
    if kind not in (TransportKind.MOCK.value, TransportKind.REPLAY.value):
        raise ProviderContractError(
            ProviderErrorCode.TRANSPORT_FORBIDDEN,
            "Only mock and replay transports are permitted",
            details={"transport": kind},
        )
