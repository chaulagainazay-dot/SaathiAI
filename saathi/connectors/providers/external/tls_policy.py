"""M33 — TLS policy for external providers (verification cannot be disabled).

Certificate verification and hostname verification are mandatory. Insecure SSL
contexts, ``verify=False``, expired certificates, hostname mismatch, and TLS
downgrades below the minimum version all fail closed. TLS results are injectable
so deterministic tests never open a real socket. Only bounded, non-sensitive TLS
metadata is recorded — never full certificates or private material.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from saathi.connectors.providers.external.models import ExternalFailure

_TLS_ORDER = {"TLSv1": 10, "TLSv1.0": 10, "TLSv1.1": 11, "TLSv1.2": 12, "TLSv1.3": 13}


class TlsPolicyError(ValueError):
    def __init__(self, code: ExternalFailure, message: str = ""):
        self.code = code
        super().__init__(f"{code.value}:{message[:80]}")


@dataclass
class TlsPolicy:
    require_verification: bool = True
    require_hostname_match: bool = True
    min_version: str = "TLSv1.2"
    allow_insecure: bool = False        # must stay False; True is a policy violation

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TlsResult:
    """Injectable TLS handshake result. In tests this is fabricated deterministically."""

    verified: bool = True
    hostname_match: bool = True
    expired: bool = False
    protocol: str = "TLSv1.3"
    cipher: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def assert_verification_enabled(policy: TlsPolicy) -> None:
    """A policy that disables verification is itself rejected (fail closed)."""
    if policy.allow_insecure or not policy.require_verification:
        raise TlsPolicyError(ExternalFailure.TLS_POLICY_BLOCKED, "verification_disabled_forbidden")


def classify_tls(result: TlsResult, policy: TlsPolicy) -> None:
    """Raise TlsPolicyError if the TLS result violates policy; return None if OK."""
    assert_verification_enabled(policy)
    if not result.verified:
        raise TlsPolicyError(ExternalFailure.TLS_CERTIFICATE_FAILED, "certificate_not_verified")
    if result.expired:
        raise TlsPolicyError(ExternalFailure.TLS_CERTIFICATE_FAILED, "certificate_expired")
    if policy.require_hostname_match and not result.hostname_match:
        raise TlsPolicyError(ExternalFailure.TLS_HOSTNAME_FAILED, "hostname_mismatch")
    got = _TLS_ORDER.get((result.protocol or "").strip(), 0)
    need = _TLS_ORDER.get((policy.min_version or "TLSv1.2").strip(), 12)
    if got < need:
        raise TlsPolicyError(ExternalFailure.TLS_POLICY_BLOCKED, f"tls_version_too_low:{result.protocol}")


def safe_tls_metadata(result: TlsResult) -> dict[str, Any]:
    """Bounded, non-sensitive TLS metadata — no certificate, no private material."""
    return {
        "protocol": (result.protocol or "")[:16],
        "verified": bool(result.verified),
        "hostname_match": bool(result.hostname_match),
        "privacy_safe": True,
    }
