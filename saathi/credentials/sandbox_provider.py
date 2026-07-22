"""M37 — Governed sandbox provider contract.

Provider-neutral interface for the M36/M37 real-sandbox path. Callers invoke
``identity`` / ``health`` / ``operation`` / ``capabilities`` / ``qualification`` /
``cleanup`` without provider-specific branching.

``GithubMetaSandboxProvider`` is the sole reference implementation, composed from
the existing M33 profile + M33 transport + M36 auth sender / normalization. No
second credential system, no parallel transport, no plaintext secret exposure.
"""
from __future__ import annotations

import abc
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Optional

from saathi.connectors.providers.external.models import ExternalProviderProfile
from saathi.connectors.providers.external.request_envelope import build_request_envelope
from saathi.connectors.providers.external.transport import ExternalTransport, SendContext
from saathi.credentials import m36
from saathi.credentials.m35 import SecretHandle
from saathi.credentials.m36 import (
    classify_observed_scopes,
    identity_operation_profile,
    make_authenticated_sender,
    meta_operation_profile,
    normalize_identity_response,
    normalize_meta_response,
    qualify_sandbox_identity,
)


@dataclass(frozen=True)
class ProviderCapabilities:
    provider_id: str
    operations: tuple[str, ...]
    methods: tuple[str, ...]
    side_effect_class: str
    data_classifications: tuple[str, ...]
    supports_identity: bool
    supports_scope_headers: bool
    auth_required_for_identity: bool
    auth_required_for_operation: bool
    max_call_budget: int
    write_capable: bool = False
    financial: bool = False
    trading: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SafeProviderResult:
    ok: bool
    provider_id: str
    operation: str
    classification: str
    detail: dict[str, Any] = field(default_factory=dict)
    failure_code: str = ""
    http_status: int = 0
    contains_secret_values: bool = False
    contains_raw_identity: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "provider_id": self.provider_id,
            "operation": self.operation,
            "classification": self.classification,
            "detail": self.detail,
            "failure_code": self.failure_code,
            "http_status": self.http_status,
            "contains_secret_values": False,
            "contains_raw_identity": False,
            "privacy_safe": True,
        }


class SandboxProvider(abc.ABC):
    """Governed sandbox provider contract. Implementations must never return
    plaintext secrets or raw personal identity fields."""

    provider_id: str

    @abc.abstractmethod
    def capabilities(self) -> ProviderCapabilities:
        ...

    @abc.abstractmethod
    def qualification(self, **kwargs: Any) -> dict[str, Any]:
        ...

    @abc.abstractmethod
    def health(self, *, transport: Optional[ExternalTransport] = None) -> SafeProviderResult:
        ...

    @abc.abstractmethod
    def identity(
        self,
        *,
        transport: ExternalTransport,
        handle: SecretHandle,
        session_id: str,
        expected_subject_fingerprint: str = "",
    ) -> SafeProviderResult:
        ...

    @abc.abstractmethod
    def operation(
        self,
        *,
        transport: ExternalTransport,
        handle: Optional[SecretHandle] = None,
        session_id: str = "",
        operation: str = "",
    ) -> SafeProviderResult:
        ...

    @abc.abstractmethod
    def cleanup(self, *, session_id: str = "", reason: str = "") -> SafeProviderResult:
        ...


# ── registry (single reference provider; no ungoverned expansion) ─────────────
_REGISTRY: dict[str, type] = {}


def register_sandbox_provider(cls: type) -> type:
    pid = getattr(cls, "provider_id", "") or ""
    if not pid:
        raise ValueError("provider_id_required")
    _REGISTRY[pid] = cls
    return cls


def resolve_sandbox_provider(provider_id: str, **kwargs: Any) -> SandboxProvider:
    pid = (provider_id or "").strip().lower()
    if pid not in _REGISTRY:
        raise m36.M36Error("unknown_sandbox_provider", pid)
    return _REGISTRY[pid](**kwargs)  # type: ignore[call-arg]


def list_sandbox_providers() -> list[str]:
    return sorted(_REGISTRY)


@register_sandbox_provider
class GithubMetaSandboxProvider(SandboxProvider):
    """Reference implementation for api.github.com (identity + meta)."""

    provider_id = "github_meta"

    def __init__(self) -> None:
        self._cleanup_log: list[dict[str, Any]] = []

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider_id=self.provider_id,
            operations=(m36.OPERATION_IDENTITY, m36.OPERATION_META),
            methods=("GET",),
            side_effect_class="READ_ONLY",
            data_classifications=("PUBLIC", "INTERNAL"),
            supports_identity=True,
            supports_scope_headers=True,
            auth_required_for_identity=True,
            auth_required_for_operation=False,
            max_call_budget=m36.M36_MAX_CALL_BUDGET,
            write_capable=False,
            financial=False,
            trading=False,
        )

    def qualification(self, **kwargs: Any) -> dict[str, Any]:
        kwargs.setdefault("provider_id", self.provider_id)
        return qualify_sandbox_identity(**kwargs)

    def health(self, *, transport: Optional[ExternalTransport] = None) -> SafeProviderResult:
        """Offline-safe structural health of the provider binding (no network)."""
        caps = self.capabilities()
        meta = meta_operation_profile()
        ident = identity_operation_profile()
        ok = (
            meta.provider_id == self.provider_id
            and ident.provider_id == self.provider_id
            and not caps.write_capable
            and not caps.financial
            and not caps.trading
        )
        return SafeProviderResult(
            ok=ok,
            provider_id=self.provider_id,
            operation="health",
            classification="STRUCTURAL_HEALTHY" if ok else "STRUCTURAL_UNHEALTHY",
            detail={
                "hostname_allowlist": list(meta.hostname_allowlist),
                "identity_path": ident.canonical_path,
                "operation_path": meta.canonical_path,
                "transport_injected": transport is not None,
            },
        )

    def identity(
        self,
        *,
        transport: ExternalTransport,
        handle: SecretHandle,
        session_id: str,
        expected_subject_fingerprint: str = "",
    ) -> SafeProviderResult:
        profile = identity_operation_profile()
        # Auth only via M36 sender wrapper — never on envelope
        auth_transport = ExternalTransport(
            resolver=transport.resolver,
            tls_prober=transport.tls_prober,
            sender=make_authenticated_sender(transport.sender, handle, session_id=session_id),  # type: ignore[arg-type]
            clock=transport.clock,
        )
        envelope = build_request_envelope(profile, request_id=f"{session_id}-id")
        if "authorization" in {k.lower() for k in envelope.safe_headers}:
            return SafeProviderResult(
                ok=False, provider_id=self.provider_id, operation=m36.OPERATION_IDENTITY,
                classification="ENVELOPE_AUTH_LEAK", failure_code="auth_on_envelope",
            )
        tr = auth_transport.send(profile, envelope)
        if tr.status_code in (401, 403):
            tr.body_bytes = b""
            return SafeProviderResult(
                ok=False, provider_id=self.provider_id, operation=m36.OPERATION_IDENTITY,
                classification="AUTHENTICATION_FAILURE",
                failure_code=f"http_{tr.status_code}",
                http_status=tr.status_code,
            )
        if tr.status_code == 429:
            tr.body_bytes = b""
            return SafeProviderResult(
                ok=False, provider_id=self.provider_id, operation=m36.OPERATION_IDENTITY,
                classification="RATE_LIMITED", failure_code="http_429", http_status=429,
            )
        if tr.status_code >= 500:
            tr.body_bytes = b""
            return SafeProviderResult(
                ok=False, provider_id=self.provider_id, operation=m36.OPERATION_IDENTITY,
                classification="PROVIDER_ERROR", failure_code=f"http_{tr.status_code}",
                http_status=tr.status_code,
            )
        if not tr.ok:
            code = tr.failure_code or "transport_failed"
            tr.body_bytes = b""
            return SafeProviderResult(
                ok=False, provider_id=self.provider_id, operation=m36.OPERATION_IDENTITY,
                classification="TRANSPORT_FAILURE", failure_code=code, http_status=tr.status_code,
            )
        norm = normalize_identity_response(
            status_code=tr.status_code,
            headers=tr.headers,
            body_bytes=tr.body_bytes,
            expected_subject_fingerprint=expected_subject_fingerprint,
            provider_id=self.provider_id,
            transport_ok=tr.ok,
            tls=tr.tls,
            latency_ms=tr.latency_ms,
        )
        tr.body_bytes = b""
        observed = norm.get("observed_scopes")
        scope = classify_observed_scopes(
            ("identity:read", "metadata:read"),
            tuple(observed) if observed is not None else None,
        )
        ok = bool(norm.get("schema_valid")) and (
            not expected_subject_fingerprint or bool(norm.get("account_match"))
        )
        return SafeProviderResult(
            ok=ok,
            provider_id=self.provider_id,
            operation=m36.OPERATION_IDENTITY,
            classification="IDENTITY_OK" if ok else "IDENTITY_FAILED",
            detail={"identity": norm, "scope": scope},
            http_status=tr.status_code,
        )

    def operation(
        self,
        *,
        transport: ExternalTransport,
        handle: Optional[SecretHandle] = None,
        session_id: str = "",
        operation: str = "",
    ) -> SafeProviderResult:
        op = operation or m36.OPERATION_META
        if op != m36.OPERATION_META:
            return SafeProviderResult(
                ok=False, provider_id=self.provider_id, operation=op,
                classification="UNSUPPORTED_OPERATION", failure_code="unknown_operation",
            )
        profile = meta_operation_profile()
        send_transport = transport
        if handle is not None and session_id:
            send_transport = ExternalTransport(
                resolver=transport.resolver,
                tls_prober=transport.tls_prober,
                sender=make_authenticated_sender(transport.sender, handle, session_id=session_id),  # type: ignore[arg-type]
                clock=transport.clock,
            )
        envelope = build_request_envelope(profile, request_id=f"{session_id or 'op'}-meta")
        tr = send_transport.send(profile, envelope)
        if tr.status_code == 429:
            tr.body_bytes = b""
            return SafeProviderResult(
                ok=False, provider_id=self.provider_id, operation=op,
                classification="RATE_LIMITED", failure_code="http_429", http_status=429,
            )
        if tr.status_code >= 500:
            tr.body_bytes = b""
            return SafeProviderResult(
                ok=False, provider_id=self.provider_id, operation=op,
                classification="PROVIDER_ERROR", failure_code=f"http_{tr.status_code}",
                http_status=tr.status_code,
            )
        if not tr.ok:
            code = tr.failure_code or "transport_failed"
            tr.body_bytes = b""
            return SafeProviderResult(
                ok=False, provider_id=self.provider_id, operation=op,
                classification="TRANSPORT_FAILURE", failure_code=code, http_status=tr.status_code,
            )
        norm = normalize_meta_response(
            status_code=tr.status_code,
            body_bytes=tr.body_bytes,
            content_type=tr.content_type,
            latency_ms=tr.latency_ms,
            transport_ok=tr.ok,
            tls=tr.tls,
        )
        tr.body_bytes = b""
        ok = bool(norm.get("schema_valid")) and tr.ok
        return SafeProviderResult(
            ok=ok,
            provider_id=self.provider_id,
            operation=op,
            classification="OPERATION_OK" if ok else "OPERATION_FAILED",
            detail={"result": norm},
            http_status=tr.status_code,
        )

    def cleanup(self, *, session_id: str = "", reason: str = "") -> SafeProviderResult:
        entry = {
            "session_id": session_id[:64],
            "reason": (reason or "cleanup")[:200],
            "provider_id": self.provider_id,
            "contains_secret_values": False,
        }
        self._cleanup_log.append(entry)
        return SafeProviderResult(
            ok=True,
            provider_id=self.provider_id,
            operation="cleanup",
            classification="CLEANUP_RECORDED",
            detail=entry,
        )


def profile_for_provider_operation(provider_id: str, operation: str) -> ExternalProviderProfile:
    """Resolve operation profiles without upward provider branching in callers."""
    if provider_id != "github_meta":
        raise m36.M36Error("unknown_sandbox_provider", provider_id)
    return m36.profile_for_operation(operation)
