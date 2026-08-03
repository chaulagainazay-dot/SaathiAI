"""Versioned, read-only Twenty CRM boundary.

This package deliberately contains no HTTP implementation. A transport must be
injected by the governed connector runtime; tests use deterministic fixtures.
"""

from .client import FixtureTransport, TwentyClient, TwentyReadService
from .errors import (
    TwentyConfigurationError,
    TwentyContractError,
    TwentyReadOnlyViolation,
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
from .manifest import TWENTY_READ_OPERATIONS, twenty_connector_manifest
from .webhook import TwentyWebhookVerifier, WebhookOutcome

__all__ = [
    "FixtureTransport",
    "TwentyClient",
    "TwentyConfig",
    "TwentyConfigurationError",
    "TwentyContractError",
    "TwentyHealthCheck",
    "TwentyIntegrationStatus",
    "TwentyPage",
    "TwentyReadOnlyViolation",
    "TwentyReadService",
    "TwentyRequest",
    "TwentyResponse",
    "TwentyScope",
    "TwentyTransportError",
    "TwentyWebhookVerifier",
    "TWENTY_READ_OPERATIONS",
    "WebhookOutcome",
    "twenty_connector_manifest",
]
