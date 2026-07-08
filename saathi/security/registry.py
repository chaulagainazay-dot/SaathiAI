"""Token Registry — named, permissioned API tokens for services and integrations.

Replaces the single global SAATHI_TOKEN with a registry where each consumer
(Studio, Mission Bot, CLI, etc.) gets its own token with scoped permissions.

Token format: `tk_<32-char random>` → stored as SHA256 hash.
"""
from __future__ import annotations

import hashlib
import secrets
import time
from typing import Callable

from saathi.security.store import SecurityStore, get_store


class TokenRegistry:
    """Registry of API tokens with permission checking.

    Permissions are endpoint path patterns with optional method prefix:
        "*"                          → all endpoints
        "/api/v1/studio/*"           → all studio endpoints
        "GET /api/v1/missions"       → specific endpoint + method
        "POST /api/v1/content/*"     → POST only on content endpoints
    """

    def __init__(self, store: SecurityStore | None = None,
                 now: Callable[[], float] = time.time):
        self.store = store or get_store()
        self._now = now

    # ── lifecycle ────────────────────────────────────────────────────────────
    def create(self, user_id: str, name: str, purpose: str = "",
               permissions: list[str] | None = None,
               expires_in_days: int | None = None) -> tuple[str, str]:
        """Create a new API token. Returns (token_id, raw_token).

        The raw token is shown ONCE to the caller. After that only the hash
        is stored.
        """
        raw = "tk_" + secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw.encode()).hexdigest()
        expires_at = None
        if expires_in_days:
            expires_at = self._now() + expires_in_days * 86400
        tid = self.store.api_token_create(
            user_id, name, token_hash, purpose=purpose,
            permissions=permissions, expires_at=expires_at,
        )
        return tid, raw

    def verify(self, raw_token: str) -> dict | None:
        """Validate a raw token and update last_used. Returns record or None."""
        if not raw_token or not raw_token.startswith("tk_"):
            return None
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        rec = self.store.api_token_by_hash(token_hash)
        if rec:
            self.store.api_token_touch(rec["id"])
        return rec

    def revoke(self, token_id: str) -> bool:
        return self.store.api_token_revoke(token_id)

    def list(self, user_id: str) -> list[dict]:
        return self.store.api_token_list(user_id)

    # ── permission checking ──────────────────────────────────────────────────
    def check_permission(self, token_record: dict, path: str, method: str = "GET") -> bool:
        """Does this token have permission for the given endpoint + method?"""
        perms = token_record.get("permissions", [])
        if isinstance(perms, str):
            import json
            try:
                perms = json.loads(perms)
            except Exception:
                perms = []
        if "*" in perms:
            return True
        for p in perms:
            if self._match_perm(p, path, method):
                return True
        return False

    @staticmethod
    def _match_perm(perm: str, path: str, method: str) -> bool:
        """Match a permission pattern against path + method."""
        # Parse optional method prefix
        perm_method = ""
        perm_path = perm
        if " " in perm:
            parts = perm.split(" ", 1)
            perm_method = parts[0].upper()
            perm_path = parts[1]
        # Method must match if specified
        if perm_method and perm_method != method.upper():
            return False
        # Wildcard suffix
        if perm_path.endswith("*"):
            prefix = perm_path[:-1]
            return path.startswith(prefix)
        return path == perm_path

    # ── legacy migration ─────────────────────────────────────────────────────
    def migrate_legacy_token(self, user_id: str, raw_token: str, name: str = "legacy-admin") -> str:
        """Migrate a raw SAATHI_TOKEN into the registry. Idempotent."""
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        existing = self.store.api_token_by_hash(token_hash)
        if existing:
            return existing["id"]
        return self.store.api_token_create(
            user_id, name, token_hash,
            purpose="Migrated from SAATHI_TOKEN env var",
            permissions=["*"],
        )


# ── process-wide singleton ───────────────────────────────────────────────────
_default_registry: TokenRegistry | None = None


def get_registry() -> TokenRegistry:
    global _default_registry
    if _default_registry is None:
        _default_registry = TokenRegistry()
    return _default_registry
