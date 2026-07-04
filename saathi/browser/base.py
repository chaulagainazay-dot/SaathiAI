"""Tier contract — every backend (HTTP, Playwright, Camofox) implements this.

The service knows only these methods + a `capabilities()` descriptor and a
`name`/`tier`. It never imports a concrete backend; new tiers are added by
registering an instance (AP-02 provider abstraction). Backends that can't do a
capability raise NotImplementedError and the service escalates.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from .types import Capabilities, Page, Snapshot, Tier


class BrowserTier(ABC):
    name: str
    tier: Tier

    @abstractmethod
    def capabilities(self) -> Capabilities: ...

    @abstractmethod
    def available(self) -> bool:
        """True if this backend is usable in the current environment
        (dependency installed / binary present). Cheap, no network."""

    @abstractmethod
    def open(self, url: str, *, timeout: int = 30, session=None) -> Page:
        """Fetch `url`. `session` (optional SessionState) supplies cookies /
        storage-state and is updated in place with anything the fetch sets."""

    # Optional capabilities — default to NotImplemented so the service escalates.
    def screenshot(self, url: str, *, timeout: int = 30, full_page: bool = True) -> bytes:
        raise NotImplementedError(f"{self.name} cannot screenshot")

    def pdf(self, url: str, *, timeout: int = 30) -> bytes:
        raise NotImplementedError(f"{self.name} cannot render PDF")

    def query(self, url: str, selector: str, *, timeout: int = 30) -> list[str]:
        """Return text content of nodes matching a CSS selector."""
        raise NotImplementedError(f"{self.name} has no DOM query")

    def snapshot(self, url: str, *, timeout: int = 30) -> Snapshot:
        """Default fingerprint = digest of the opened page text."""
        import hashlib
        page = self.open(url, timeout=timeout)
        text = page.text or page.html
        digest = hashlib.sha256(text.encode("utf-8", "ignore")).hexdigest()
        return Snapshot(url=url, digest=digest, length=len(text))
