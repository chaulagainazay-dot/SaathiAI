"""M31 — Deterministic test doubles (no network, no real providers)."""
from __future__ import annotations

from saathi.credentials.testing.sandbox_oauth import FakeOAuthProvider, FakeProviderError

__all__ = ["FakeOAuthProvider", "FakeProviderError"]
