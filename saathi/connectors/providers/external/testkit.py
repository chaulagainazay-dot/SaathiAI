"""M33 — Deterministic test/offline kit: injectable resolvers, TLS probers, senders.

Used by offline verification and by the deterministic test suite so NO standard
test ever performs a real DNS, TLS, or network operation. Not part of the
verification fingerprint surface and never used on the live path.
"""
from __future__ import annotations

from typing import Any, Callable, Optional

from saathi.connectors.providers.external.tls_policy import TlsResult
from saathi.connectors.providers.external.transport import ExternalTransport, SendContext


def public_resolver(ips: tuple[str, ...] = ("140.82.112.3",)) -> Callable[[str], list[str]]:
    def _r(host: str) -> list[str]:
        return list(ips)
    return _r


def private_resolver(ips: tuple[str, ...] = ("10.0.0.5",)) -> Callable[[str], list[str]]:
    def _r(host: str) -> list[str]:
        return list(ips)
    return _r


def mixed_resolver(ips: tuple[str, ...] = ("140.82.112.3", "10.0.0.5")) -> Callable[[str], list[str]]:
    def _r(host: str) -> list[str]:
        return list(ips)
    return _r


def failing_resolver() -> Callable[[str], list[str]]:
    def _r(host: str) -> list[str]:
        raise OSError("nxdomain")
    return _r


def empty_resolver() -> Callable[[str], list[str]]:
    def _r(host: str) -> list[str]:
        return []
    return _r


def timeout_resolver() -> Callable[[str], list[str]]:
    def _r(host: str) -> list[str]:
        raise TimeoutError("dns_timeout")
    return _r


def rebinding_resolver() -> Callable[[str], list[str]]:
    """Returns a public and a private address in one resolution → must fail closed."""
    def _r(host: str) -> list[str]:
        return ["140.82.112.3", "127.0.0.1"]
    return _r


def good_tls_prober(protocol: str = "TLSv1.3") -> Callable[[str], TlsResult]:
    def _p(host: str) -> TlsResult:
        return TlsResult(verified=True, hostname_match=True, expired=False, protocol=protocol)
    return _p


def tls_prober(**kw: Any) -> Callable[[str], TlsResult]:
    def _p(host: str) -> TlsResult:
        return TlsResult(**kw)
    return _p


def fixture_sender(
    *,
    status: int = 200,
    body_bytes: bytes = b"{}",
    headers: Optional[dict[str, str]] = None,
    content_type: str = "application/json",
    location: str = "",
    decompressed_size: Optional[int] = None,
) -> Callable[[SendContext], dict[str, Any]]:
    def _s(ctx: SendContext) -> dict[str, Any]:
        h = dict(headers or {})
        h.setdefault("content-type", content_type)
        return {
            "status_code": status,
            "headers": h,
            "body_bytes": body_bytes,
            "content_type": content_type,
            "location": location,
            "decompressed_size": len(body_bytes) if decompressed_size is None else int(decompressed_size),
        }
    return _s


def raising_sender(exc: BaseException) -> Callable[[SendContext], dict[str, Any]]:
    def _s(ctx: SendContext) -> dict[str, Any]:
        raise exc
    return _s


def make_transport(
    *,
    resolver: Optional[Callable[[str], list[str]]] = None,
    tls_prober_fn: Optional[Callable[[str], TlsResult]] = None,
    sender: Optional[Callable[[SendContext], dict[str, Any]]] = None,
    clock: Optional[Callable[[], float]] = None,
) -> ExternalTransport:
    return ExternalTransport(
        resolver=resolver or public_resolver(),
        tls_prober=tls_prober_fn or good_tls_prober(),
        sender=sender,
        clock=clock,
    )
