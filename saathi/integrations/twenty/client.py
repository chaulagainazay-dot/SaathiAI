"""Read-only Twenty client over an injected, governed transport."""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from .errors import (
    TwentyContractError,
    TwentyReadOnlyViolation,
    TwentyScopeViolation,
    TwentyTransportError,
)
from .models import (
    TwentyConfig,
    TwentyHealthCheck,
    TwentyIntegrationStatus,
    TwentyPage,
    TwentyRequest,
    TwentyResponse,
    TwentyScope,
)


READABLE_OBJECTS = frozenset({"companies", "people", "opportunities", "tasks"})
AuditSink = Callable[[str, dict[str, Any]], None]


class TwentyTransport(Protocol):
    """Transport contract; implementations remain under connector governance."""

    def send(self, request: TwentyRequest, *, timeout_seconds: float) -> TwentyResponse: ...


@dataclass
class FixtureTransport:
    """Deterministic transport for contract tests; never opens a socket."""

    fixtures: Mapping[tuple[str, str, str, str], TwentyResponse]
    calls: int = 0

    def send(self, request: TwentyRequest, *, timeout_seconds: float) -> TwentyResponse:
        del timeout_seconds
        self.calls += 1
        key = (request.scope.org_id, request.scope.workspace_id, request.method, request.path)
        try:
            return self.fixtures[key]
        except KeyError as exc:
            raise TwentyTransportError("fixture_missing") from exc


class TwentyClient:
    def __init__(
        self,
        config: TwentyConfig,
        transport: TwentyTransport,
        *,
        audit_sink: AuditSink | None = None,
    ) -> None:
        config.validate(require_credentials=False)
        self.config = config
        self.transport = transport
        self.audit_sink = audit_sink

    def _audit(self, event: str, detail: dict[str, Any]) -> None:
        if self.audit_sink:
            safe = {k: v for k, v in detail.items() if k not in {"authorization", "token", "secret"}}
            self.audit_sink(event, safe)

    def get(self, path: str, *, scope: TwentyScope, query: dict[str, str] | None = None) -> dict[str, Any]:
        request = TwentyRequest(method="GET", path=path, scope=scope, query=query or {})
        request.validate()
        self._audit("twenty.read.requested", {"org_id": scope.org_id, "workspace_id": scope.workspace_id, "path": path})
        try:
            response = self.transport.send(request, timeout_seconds=self.config.timeout_seconds)
        except TimeoutError as exc:
            self._audit("twenty.read.failed", {"path": path, "reason": "timeout"})
            raise TwentyTransportError("twenty_timeout") from exc
        except TwentyTransportError:
            self._audit("twenty.read.failed", {"path": path, "reason": "transport_failure"})
            raise
        except Exception as exc:
            self._audit("twenty.read.failed", {"path": path, "reason": "transport_failure"})
            raise TwentyTransportError("twenty_transport_failure") from exc
        if not isinstance(response, TwentyResponse) or not isinstance(response.body, dict):
            raise TwentyContractError("malformed_twenty_response")
        if response.status_code != 200:
            raise TwentyTransportError(f"twenty_http_status_{response.status_code}")
        self._audit("twenty.read.completed", {"path": path, "status_code": 200})
        return response.body

    def reject_write(self, operation: str) -> None:
        self._audit("twenty.write.rejected", {"operation": operation, "reason": "read_only_boundary"})
        raise TwentyReadOnlyViolation("twenty_integration_is_read_only")

    def health(self, *, scope: TwentyScope) -> TwentyHealthCheck:
        try:
            self.get("/healthz", scope=scope)
        except (TwentyContractError, TwentyTransportError) as exc:
            return TwentyHealthCheck(False, "UNAVAILABLE", str(exc))
        return TwentyHealthCheck(True, "HEALTH_ENDPOINT_RESPONDED", "live_contract_not_certified")

    def status(self) -> TwentyIntegrationStatus:
        return TwentyIntegrationStatus(configured=self.config.integration_enabled)


class TwentyReadService:
    def __init__(self, client: TwentyClient, *, scope: TwentyScope) -> None:
        scope.validate()
        self.client = client
        self.scope = scope

    def _assert_scope(self, scope: TwentyScope | None) -> None:
        if scope is not None and scope != self.scope:
            raise TwentyScopeViolation("cross_scope_twenty_access_denied")

    @staticmethod
    def _object_name(name: str) -> str:
        normalized = name.strip().lower()
        if normalized not in READABLE_OBJECTS:
            raise TwentyContractError("unknown_or_unsupported_twenty_object")
        return normalized

    def list_records(
        self,
        object_name: str,
        *,
        cursor: str | None = None,
        limit: int = 20,
        scope: TwentyScope | None = None,
    ) -> TwentyPage:
        self._assert_scope(scope)
        name = self._object_name(object_name)
        if not 1 <= limit <= 100:
            raise TwentyContractError("pagination_limit_out_of_bounds")
        query = {"limit": str(limit)}
        if cursor:
            query["startingAfter"] = cursor
        body = self.client.get(f"/rest/{name}", scope=self.scope, query=query)
        records = body.get("data")
        page_info = body.get("pageInfo", {})
        if not isinstance(records, list) or not isinstance(page_info, dict):
            raise TwentyContractError("malformed_twenty_page")
        if any(not isinstance(record, dict) for record in records):
            raise TwentyContractError("malformed_twenty_record")
        return TwentyPage(
            records=tuple(self._map_record(name, record) for record in records),
            has_next_page=bool(page_info.get("hasNextPage", False)),
            next_cursor=str(page_info["endCursor"]) if page_info.get("endCursor") else None,
        )

    def retrieve_record(
        self,
        object_name: str,
        record_id: str,
        *,
        scope: TwentyScope | None = None,
    ) -> dict[str, Any]:
        self._assert_scope(scope)
        name = self._object_name(object_name)
        if not record_id or "/" in record_id or ".." in record_id:
            raise TwentyContractError("invalid_record_id")
        body = self.client.get(f"/rest/{name}/{record_id}", scope=self.scope)
        record = body.get("data", body)
        if not isinstance(record, dict) or not record.get("id"):
            raise TwentyContractError("malformed_twenty_record")
        return self._map_record(name, record)

    def fetch_object_metadata(self) -> dict[str, Any]:
        body = self.client.get("/rest/metadata/objects", scope=self.scope)
        if not isinstance(body.get("data", body), (list, dict)):
            raise TwentyContractError("malformed_twenty_metadata")
        return body

    def fetch_custom_object_schema(self, object_id: str) -> dict[str, Any]:
        if not object_id or "/" in object_id or ".." in object_id:
            raise TwentyContractError("invalid_object_id")
        body = self.client.get(f"/rest/metadata/objects/{object_id}", scope=self.scope)
        if not isinstance(body, dict):
            raise TwentyContractError("malformed_twenty_metadata")
        return body

    def _map_record(self, object_name: str, record: dict[str, Any]) -> dict[str, Any]:
        if not record.get("id"):
            raise TwentyContractError("record_id_required")
        return {
            "provider": "twenty",
            "provider_version": "2.27-contract-fixture",
            "object_type": object_name,
            "org_id": self.scope.org_id,
            "workspace_id": self.scope.workspace_id,
            "read_only": True,
            "source_validation": "FIXTURE_ONLY_NOT_LIVE_VALIDATED",
            "record": dict(record),
        }
