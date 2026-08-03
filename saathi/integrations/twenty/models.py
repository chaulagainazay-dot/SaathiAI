"""Typed contracts for the offline-certified Twenty read boundary."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

from .errors import TwentyConfigurationError, TwentyContractError


LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


@dataclass(frozen=True)
class TwentyScope:
    org_id: str
    workspace_id: str

    def validate(self) -> None:
        if not self.org_id.strip() or not self.workspace_id.strip():
            raise TwentyConfigurationError("organization_and_workspace_scope_required")


@dataclass(frozen=True)
class TwentyConfig:
    base_url: str = "http://127.0.0.1:3020"
    credential_reference: str = ""
    timeout_seconds: float = 5.0
    localhost_only: bool = True
    read_only: bool = True
    integration_enabled: bool = False

    def validate(self, *, require_credentials: bool = False) -> None:
        parsed = urlsplit(self.base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise TwentyConfigurationError("invalid_twenty_base_url")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise TwentyConfigurationError("credentials_or_query_forbidden_in_base_url")
        if self.localhost_only and parsed.hostname not in LOCAL_HOSTS:
            raise TwentyConfigurationError("twenty_sandbox_must_be_localhost_only")
        if not (0.05 <= float(self.timeout_seconds) <= 30.0):
            raise TwentyConfigurationError("timeout_out_of_bounds")
        if not self.read_only:
            raise TwentyConfigurationError("twenty_write_authority_not_available")
        if require_credentials and not self.credential_reference.strip():
            raise TwentyConfigurationError("credential_reference_required")
        if self.credential_reference and any(
            marker in self.credential_reference.lower()
            for marker in ("bearer ", "eyj", "sk-", "password=", "token=")
        ):
            raise TwentyConfigurationError("raw_credential_forbidden_use_reference")


@dataclass(frozen=True)
class TwentyRequest:
    method: str
    path: str
    scope: TwentyScope
    query: dict[str, str] = field(default_factory=dict)

    def validate(self) -> None:
        self.scope.validate()
        if self.method != "GET":
            raise TwentyContractError("read_only_transport_allows_get_only")
        if not self.path.startswith("/") or ".." in self.path or "://" in self.path:
            raise TwentyContractError("invalid_relative_api_path")


@dataclass(frozen=True)
class TwentyResponse:
    status_code: int
    body: dict[str, Any]


@dataclass(frozen=True)
class TwentyPage:
    records: tuple[dict[str, Any], ...]
    has_next_page: bool
    next_cursor: str | None
    source: str = "TWENTY_FIXTURE_UNVALIDATED_LIVE"


@dataclass(frozen=True)
class TwentyHealthCheck:
    available: bool
    state: str
    detail: str


@dataclass(frozen=True)
class TwentyIntegrationStatus:
    configured: bool
    transport_validated_live: bool = False
    read_only: bool = True
    write_authority: bool = False
    webhook_execution_authority: bool = False
    evidence_state: str = "FIXTURE_CONTRACTS_ONLY"
