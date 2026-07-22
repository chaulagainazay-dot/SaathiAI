"""ExecutionGateway exception hierarchy."""

from enum import Enum
from dataclasses import dataclass
from typing import Optional


class ErrorSeverity(Enum):
    """Error severity classification."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class ExecutionError:
    """Base execution error."""
    code: str
    message: str
    severity: ErrorSeverity
    retriable: bool = False
    context: Optional[dict] = None


class ExecutionGatewayException(Exception):
    """Base ExecutionGateway exception."""
    pass


class ValidationException(ExecutionGatewayException):
    """Schema or syntax validation failed."""
    pass


class AuthorizationException(ExecutionGatewayException):
    """Authorization check failed."""
    pass


class ApprovalException(ExecutionGatewayException):
    """Approval check failed or pending."""
    pass


class CredentialException(ExecutionGatewayException):
    """Credential error (missing, expired, invalid)."""
    pass


class ConnectorException(ExecutionGatewayException):
    """Connector invocation failed."""
    pass


class ResultException(ExecutionGatewayException):
    """Result validation or sanitization failed."""
    pass


class StateException(ExecutionGatewayException):
    """Invalid state transition."""
    pass
