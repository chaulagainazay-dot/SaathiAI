"""M15 credential-reference system — metadata ONLY, never raw secrets.

A credential record stores a *reference* to a secret in a backend (env var, OS
keychain, or a future cloud secret manager) — never the secret value. Resolving
a reference returns the value in-process only, never persisted, never returned
by any API, never logged.
"""
from __future__ import annotations

import os
import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional


class SecretBackend(str, Enum):
    ENV = "env"                # environment variable reference
    KEYCHAIN = "keychain"      # OS keychain (macOS `security`)
    ENCRYPTED_STORE = "encrypted_store"  # existing secrets/ store
    CLOUD = "cloud"            # future cloud secret manager (contract-ready)


class CredStatus(str, Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"
    ROTATION_REQUIRED = "rotation_required"
    UNVERIFIED = "unverified"


@dataclass
class CredentialRef:
    ref_id: str
    connector_id: str
    scope: str                 # user:<id> or org:<id>
    provider_account_id: str = ""
    label: str = ""
    backend: str = SecretBackend.ENV.value
    backend_key: str = ""      # e.g. env var NAME — NOT the value
    granted_scopes: list = field(default_factory=list)
    created_at: float = 0.0
    updated_at: float = 0.0
    last_verified: Optional[float] = None
    expiry: Optional[float] = None
    status: str = CredStatus.UNVERIFIED.value
    rotation_required: bool = False

    def to_dict(self) -> dict:
        """SAFE serialization — contains only metadata + the backend KEY name,
        never a secret value."""
        d = asdict(self)
        return d


class SecretUnavailable(Exception):
    pass


def resolve_secret(ref: CredentialRef) -> str:
    """Resolve a reference to its secret value IN-PROCESS ONLY.

    The value is never returned by an API, logged, stored, or put in memory/
    checkpoints/prompts. Callers must use it transiently and discard it.
    """
    if ref.status in (CredStatus.REVOKED.value, CredStatus.EXPIRED.value):
        raise SecretUnavailable(f"credential {ref.ref_id} is {ref.status}")
    if ref.backend == SecretBackend.ENV.value:
        val = os.getenv(ref.backend_key, "")
        if not val:
            raise SecretUnavailable(f"env {ref.backend_key} not set")
        return val
    if ref.backend == SecretBackend.KEYCHAIN.value:
        import subprocess
        try:
            r = subprocess.run(["security", "find-generic-password", "-s",
                               ref.backend_key, "-w"], capture_output=True,
                               text=True, timeout=5)
            if r.returncode == 0 and r.stdout.strip():
                return r.stdout.strip()
        except Exception:
            pass
        raise SecretUnavailable(f"keychain {ref.backend_key} unavailable")
    # ENCRYPTED_STORE / CLOUD: contract-ready, not configured in this env
    raise SecretUnavailable(f"backend {ref.backend} not configured")


def has_secret(ref: CredentialRef) -> bool:
    """Presence check WITHOUT resolving/returning the value."""
    if ref.backend == SecretBackend.ENV.value:
        return bool(os.getenv(ref.backend_key))
    return False


def new_ref(*, connector_id: str, scope: str, backend: str = "env",
            backend_key: str = "", label: str = "",
            provider_account_id: str = "") -> CredentialRef:
    now = time.time()
    return CredentialRef(
        ref_id="cred_" + uuid.uuid4().hex[:14], connector_id=connector_id,
        scope=scope, provider_account_id=provider_account_id, label=label,
        backend=backend, backend_key=backend_key, created_at=now, updated_at=now,
        status=CredStatus.ACTIVE.value if (backend != "env" or os.getenv(backend_key))
        else CredStatus.UNVERIFIED.value)
