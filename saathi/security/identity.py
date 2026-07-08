"""Identity Provider abstraction — adapter pattern for OAuth / SSO.

Modelled after Model Router and Connector Registry:
- Callers ask by provider name
- The router picks the right adapter
- Adding a provider = one adapter file + one registration call

No providers are fully implemented yet (no credentials configured).
The skeleton is ready for Google, Apple, GitHub, Microsoft, Telegram.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable


@dataclass
class OAuthToken:
    access_token: str
    refresh_token: str | None = None
    expires_at: float | None = None
    token_type: str = "Bearer"
    scope: str = ""


@dataclass
class UserInfo:
    provider_user_id: str
    email: str | None = None
    name: str | None = None
    avatar_url: str | None = None
    raw: dict | None = None


class IdentityProvider(ABC):
    """Abstract base for OAuth / SSO identity providers.

    Subclass this and implement the 4 abstract methods. Register the instance
    with IdentityProviderRouter. No changes needed in server.py.
    """

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def authorize_url(self, redirect_uri: str, state: str) -> str:
        """Return the OAuth authorization URL for this provider."""
        ...

    @abstractmethod
    async def exchange_code(self, code: str, redirect_uri: str) -> OAuthToken:
        """Exchange an authorization code for an access token."""
        ...

    @abstractmethod
    async def get_user_info(self, token: OAuthToken) -> UserInfo:
        """Fetch user profile from the provider's API."""
        ...

    def diagnostic(self, error: Exception) -> str:
        """Convert a provider error to a human-readable message.
        Override per provider for better messages."""
        return f"{self.name} authentication failed: {error}"

    def is_configured(self) -> bool:
        """Override to check if required env vars / credentials are present."""
        return True


# ── skeleton adapters (not yet functional — no credentials) ──────────────────

class GoogleIdentityProvider(IdentityProvider):
    """Google OAuth 2.0 adapter skeleton."""

    @property
    def name(self) -> str:
        return "google"

    def authorize_url(self, redirect_uri: str, state: str) -> str:
        # TODO: implement when GOOGLE_CLIENT_ID is configured
        return ""

    async def exchange_code(self, code: str, redirect_uri: str) -> OAuthToken:
        raise NotImplementedError("Google OAuth credentials not configured")

    async def get_user_info(self, token: OAuthToken) -> UserInfo:
        raise NotImplementedError("Google OAuth credentials not configured")

    def is_configured(self) -> bool:
        import os
        return bool(os.getenv("GOOGLE_CLIENT_ID"))


class AppleIdentityProvider(IdentityProvider):
    """Apple Sign In adapter skeleton."""

    @property
    def name(self) -> str:
        return "apple"

    def authorize_url(self, redirect_uri: str, state: str) -> str:
        return ""

    async def exchange_code(self, code: str, redirect_uri: str) -> OAuthToken:
        raise NotImplementedError("Apple Sign In credentials not configured")

    async def get_user_info(self, token: OAuthToken) -> UserInfo:
        raise NotImplementedError("Apple Sign In credentials not configured")

    def is_configured(self) -> bool:
        import os
        return bool(os.getenv("APPLE_CLIENT_ID"))


class GitHubIdentityProvider(IdentityProvider):
    """GitHub OAuth adapter skeleton."""

    @property
    def name(self) -> str:
        return "github"

    def authorize_url(self, redirect_uri: str, state: str) -> str:
        return ""

    async def exchange_code(self, code: str, redirect_uri: str) -> OAuthToken:
        raise NotImplementedError("GitHub OAuth credentials not configured")

    async def get_user_info(self, token: OAuthToken) -> UserInfo:
        raise NotImplementedError("GitHub OAuth credentials not configured")

    def is_configured(self) -> bool:
        import os
        return bool(os.getenv("GITHUB_CLIENT_ID"))


# ── router ───────────────────────────────────────────────────────────────────

class IdentityProviderRouter:
    """Registry and router for identity providers.

    Usage:
        router = IdentityProviderRouter()
        router.register(GoogleIdentityProvider())
        router.register(AppleIdentityProvider())

        provider = router.get("google")
        url = provider.authorize_url(redirect_uri, state)
    """

    def __init__(self):
        self._providers: dict[str, IdentityProvider] = {}

    def register(self, provider: IdentityProvider) -> None:
        self._providers[provider.name] = provider

    def get(self, name: str) -> IdentityProvider | None:
        return self._providers.get(name)

    def list(self) -> list[IdentityProvider]:
        return list(self._providers.values())

    def available(self) -> list[str]:
        """Providers that have credentials configured."""
        return [p.name for p in self._providers.values() if p.is_configured()]

    def all_names(self) -> list[str]:
        return list(self._providers.keys())


# ── process-wide default router ──────────────────────────────────────────────
_default_router: IdentityProviderRouter | None = None


def default_router() -> IdentityProviderRouter:
    global _default_router
    if _default_router is None:
        _default_router = IdentityProviderRouter()
        # Register all skeleton adapters
        _default_router.register(GoogleIdentityProvider())
        _default_router.register(AppleIdentityProvider())
        _default_router.register(GitHubIdentityProvider())
    return _default_router
