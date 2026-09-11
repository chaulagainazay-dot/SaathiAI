"""Connectivity governance errors — fail closed."""
from __future__ import annotations


class ConnectivityGovernanceError(Exception):
    """Base governance error."""

    def __init__(self, code: str, message: str, **extra):
        super().__init__(message)
        self.code = code
        self.message = message
        self.extra = extra

    def to_dict(self) -> dict:
        return {"ok": False, "refused": True, "code": self.code, "message": self.message, **self.extra}


class AuthorityDenied(ConnectivityGovernanceError):
    pass


class ApprovalRejected(ConnectivityGovernanceError):
    pass


class CredentialPolicyViolation(ConnectivityGovernanceError):
    pass


class ProviderGovernanceError(ConnectivityGovernanceError):
    pass


class EmergencyShutdownActive(ConnectivityGovernanceError):
    pass


class SecretFieldDetected(ConnectivityGovernanceError):
    pass
