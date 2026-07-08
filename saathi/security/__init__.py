"""SaathiOS Security Platform — Authentication v1.2 package exports."""
from __future__ import annotations

from saathi.security.store import SecurityStore, get_store
from saathi.security.registry import TokenRegistry, get_registry
from saathi.security.risk import RiskEngine
from saathi.security.timeline import SecurityTimeline, get_timeline, EVENT_KINDS
from saathi.security.health import PasswordHealth
from saathi.security.identity import (
    IdentityProvider, IdentityProviderRouter, OAuthToken, UserInfo,
    GoogleIdentityProvider, AppleIdentityProvider, GitHubIdentityProvider,
    default_router,
)
from saathi.security.diagnostics import (
    passkey_diagnostic, passkey_diagnostic_from_exception, oauth_diagnostic,
)

__all__ = [
    # Store
    "SecurityStore", "get_store",
    # Token Registry
    "TokenRegistry", "get_registry",
    # Risk
    "RiskEngine",
    # Timeline
    "SecurityTimeline", "get_timeline", "EVENT_KINDS",
    # Health
    "PasswordHealth",
    # Identity
    "IdentityProvider", "IdentityProviderRouter", "OAuthToken", "UserInfo",
    "GoogleIdentityProvider", "AppleIdentityProvider", "GitHubIdentityProvider",
    "default_router",
    # Diagnostics
    "passkey_diagnostic", "passkey_diagnostic_from_exception", "oauth_diagnostic",
]
