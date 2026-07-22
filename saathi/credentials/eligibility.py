"""M31 — Connector credential / account-link eligibility.

Answers a question distinct from M30 behavioral certification and M25 platform
production certification: *does this connector have a ready, governed credential
and a linked account for this owner?* It composes with — never replaces — M30
``resolve_eligibility``.

Fail-closed everywhere: unknown link, unbound credential, expired/quarantined/
revoked credential, prohibited provider/scope, or cross-owner access all deny.
Caller metadata can never forge eligibility.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class CredentialEligibilityDecision:
    allowed: bool
    connector_id: str
    account_link_id: str = ""
    readiness: str = ""
    reason: str = "ok"
    layer: str = "m31_credential"

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "connector_id": self.connector_id,
            "account_link_id": self.account_link_id,
            "readiness": self.readiness,
            "reason": self.reason,
            "layer": self.layer,
        }


_OVERRIDE_KEYS = frozenset({
    "force_credential", "bypass_credential", "credential_ready",
    "skip_account_link", "account_link_override", "force_linked",
    "inject_secret", "raw_secret", "secret_override",
})


def caller_cannot_override_credential(metadata: Optional[dict[str, Any]]) -> bool:
    """True if caller metadata attempts to forge credential eligibility."""
    if not metadata:
        return False
    for k in metadata:
        if str(k).lower() in _OVERRIDE_KEYS:
            return True
    return False


def resolve_credential_eligibility(
    connector_id: str,
    account_link_id: str,
    *,
    registry: Any,
    broker: Any = None,
    owner_scope: str = "",
    caller_metadata: Optional[dict[str, Any]] = None,
) -> CredentialEligibilityDecision:
    """Decide whether a connector may execute against a linked account now."""
    if caller_cannot_override_credential(caller_metadata):
        return CredentialEligibilityDecision(
            False, connector_id, account_link_id,
            reason="caller_override_rejected",
        )
    if registry is None:
        return CredentialEligibilityDecision(
            False, connector_id, account_link_id, reason="no_account_link_registry",
        )
    r = registry.readiness(account_link_id, connector_id=connector_id, owner_scope=owner_scope)
    return CredentialEligibilityDecision(
        allowed=bool(r.get("ready")),
        connector_id=connector_id,
        account_link_id=account_link_id,
        readiness=str(r.get("readiness", "")),
        reason=str(r.get("reason", "")),
    )


@dataclass
class CombinedEligibilityDecision:
    allowed: bool
    connector_id: str
    reason: str = "ok"
    certification: Optional[dict[str, Any]] = None
    credential: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "connector_id": self.connector_id,
            "reason": self.reason,
            "certification": self.certification,
            "credential": self.credential,
        }


def combined_connector_eligibility(
    connector_id: str,
    *,
    account_link_id: str = "",
    registry: Any = None,
    broker: Any = None,
    owner_scope: str = "",
    caller_metadata: Optional[dict[str, Any]] = None,
    cert_store: Any = None,
    cert_registry: Any = None,
    require_certification: bool = True,
    require_credential: bool = True,
) -> CombinedEligibilityDecision:
    """AND M30 behavioral certification with M31 credential/account-link readiness.

    Either gate can be disabled for connectors that need only one (e.g. an
    AuthMode.NONE built-in needs certification but no credential). Both default on.
    Fail-closed: any error or denial in either layer denies overall.
    """
    cert_view: Optional[dict[str, Any]] = None
    if require_certification:
        try:
            from saathi.connectors.conformance.eligibility import resolve_eligibility
            # M31 is a read-only consumer of M30 certification: refresh_stale=False
            # so composing eligibility never mutates the M30 certification store.
            elig = resolve_eligibility(
                connector_id, store=cert_store, registry=cert_registry, refresh_stale=False,
            )
            cert_view = {
                "allowed": bool(elig.allowed), "state": elig.state,
                "reason": elig.reason, "fresh": bool(getattr(elig, "fresh", False)),
            }
            if not elig.allowed:
                return CombinedEligibilityDecision(
                    False, connector_id,
                    reason=f"certification:{elig.reason}", certification=cert_view,
                )
        except Exception as e:  # fail-closed
            return CombinedEligibilityDecision(
                False, connector_id,
                reason=f"certification_error:{type(e).__name__}",
                certification={"allowed": False},
            )

    cred_view: Optional[dict[str, Any]] = None
    if require_credential:
        cred = resolve_credential_eligibility(
            connector_id, account_link_id,
            registry=registry, broker=broker, owner_scope=owner_scope,
            caller_metadata=caller_metadata,
        )
        cred_view = cred.to_dict()
        if not cred.allowed:
            return CombinedEligibilityDecision(
                False, connector_id,
                reason=f"credential:{cred.reason}",
                certification=cert_view, credential=cred_view,
            )

    return CombinedEligibilityDecision(
        True, connector_id, reason="ok",
        certification=cert_view, credential=cred_view,
    )
