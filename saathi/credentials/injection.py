"""M31 — Narrow runtime secret-injection boundary.

The *only* sanctioned way a connector obtains secret values is inside a
``SecretInjectionContext``: it issues a bounded, single-use lease, retrieves the
allowed fields for one request, hands them to the caller for the duration of a
``with`` block, and then scrubs them — whether the block succeeds or raises.

Secrets never leave the block, are never returned upward, never enter events or
evidence, and are overwritten on exit so a stale reference cannot resurface them.
"""
from __future__ import annotations

from typing import Any, Optional

from saathi.credentials.broker import BrokerError, CredentialBroker


class InjectionError(Exception):
    def __init__(self, code: str, detail: str = ""):
        super().__init__(detail or code)
        self.code = code


def _scrub(d: dict[str, str]) -> None:
    """Best-effort in-place erase of secret values."""
    for k in list(d.keys()):
        try:
            d[k] = "\x00" * len(d[k]) if isinstance(d[k], str) else ""
        except Exception:
            d[k] = ""
        d[k] = ""
        d.pop(k, None)


class SecretInjectionContext:
    """Context manager yielding a request-scoped secrets dict, scrubbed on exit."""

    def __init__(
        self,
        broker: CredentialBroker,
        *,
        credential_ref_id: str,
        request_id: str,
        connector_id: str,
        operation: str,
        actor: str,
        owner_scope: str = "",
        allowed_fields: Optional[tuple[str, ...]] = None,
        payload: Optional[dict] = None,
        resource_target: str = "",
        ttl_seconds: float = 30.0,
    ):
        self.broker = broker
        self._args = dict(
            credential_ref_id=credential_ref_id,
            request_id=request_id,
            connector_id=connector_id,
            operation=operation,
            payload=payload,
            resource_target=resource_target,
        )
        self._lease_args = dict(
            credential_ref_id=credential_ref_id,
            request_id=request_id,
            connector_id=connector_id,
            operation=operation,
            actor=actor,
            owner_scope=owner_scope,
            allowed_fields=allowed_fields,
            payload=payload,
            resource_target=resource_target,
            ttl_seconds=ttl_seconds,
        )
        self._secrets: dict[str, str] = {}
        self.lease_id: str = ""
        self._entered = False

    def __enter__(self) -> dict[str, str]:
        try:
            lease = self.broker.issue_lease(**self._lease_args)
            self.lease_id = lease["lease_id"]
            self._secrets = self.broker.inject_secrets(lease_id=self.lease_id, **self._args)
        except BrokerError as e:
            self._secrets = {}
            raise InjectionError(e.code) from e
        self._entered = True
        return self._secrets

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        _scrub(self._secrets)
        self._secrets = {}
        # Belt-and-suspenders: revoke the (already single-use-consumed) lease.
        try:
            if self.lease_id:
                self.broker.leases.revoke(self.lease_id)
        except Exception:
            pass
        return False  # never suppress exceptions


def inject_and_apply(
    broker: CredentialBroker,
    apply_fn: Any,
    **kwargs: Any,
) -> Any:
    """Run ``apply_fn(secrets)`` inside an injection context and scrub after.

    ``apply_fn`` must consume the secrets synchronously and return only
    non-secret results. Its return value is passed through untouched.
    """
    with SecretInjectionContext(broker, **kwargs) as secrets:
        return apply_fn(secrets)
