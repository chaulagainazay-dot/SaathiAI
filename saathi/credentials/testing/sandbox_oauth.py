"""M31 — In-process fake OAuth provider (no network)."""
from __future__ import annotations

import hashlib
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


class FakeProviderError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass
class FakeOAuthProvider:
    """Deterministic sandbox OAuth provider."""

    clock: Optional[Callable[[], float]] = None
    code_ttl_sec: float = 120.0
    fail_mode: str = ""  # timeout | unavailable | malformed | ""
    rotate_refresh: bool = True
    _codes: dict[str, dict[str, Any]] = field(default_factory=dict)
    _tokens: dict[str, dict[str, Any]] = field(default_factory=dict)
    _lock: threading.RLock = field(default_factory=threading.RLock)

    def __post_init__(self) -> None:
        if self.clock is None:
            self.clock = time.time

    def authorize(
        self,
        *,
        state: str,
        code_challenge: str,
        redirect_uri: str,
        provider_id: str,
        scopes: list[str],
        allow: bool = True,
        account_subject: str = "sandbox-user-1",
    ) -> dict[str, Any]:
        if self.fail_mode == "unavailable":
            raise FakeProviderError("provider_unavailable")
        if not allow:
            return {"error": "access_denied", "state": state}
        code = "ac_" + hashlib.sha256(f"{state}:{time.time()}".encode()).hexdigest()[:20]
        with self._lock:
            self._codes[code] = {
                "state": state,
                "code_challenge": code_challenge,
                "redirect_uri": redirect_uri,
                "provider_id": provider_id,
                "scopes": list(scopes),
                "created_at": float(self.clock()),
                "used": False,
                "subject": account_subject,
            }
        return {
            "code": code,
            "state": state,
            "redirect_uri": redirect_uri,
        }

    def exchange_code(
        self,
        *,
        code: str,
        code_verifier: str,
        redirect_uri: str,
        provider_id: str,
    ) -> dict[str, Any]:
        if self.fail_mode == "timeout":
            raise FakeProviderError("token_exchange_timeout")
        if self.fail_mode == "unavailable":
            raise FakeProviderError("provider_unavailable")
        if self.fail_mode == "malformed":
            return {"not_a_token": True}
        with self._lock:
            rec = self._codes.get(code)
            if rec is None:
                raise FakeProviderError("invalid_code")
            if rec["used"]:
                raise FakeProviderError("code_reuse")
            if float(self.clock()) - rec["created_at"] > self.code_ttl_sec:
                raise FakeProviderError("code_expired")
            if rec["redirect_uri"] != redirect_uri:
                raise FakeProviderError("redirect_mismatch")
            if rec["provider_id"] != provider_id:
                raise FakeProviderError("provider_mismatch")
            # PKCE S256
            import base64
            challenge = base64.urlsafe_b64encode(
                hashlib.sha256(code_verifier.encode()).digest()
            ).decode().rstrip("=")
            if challenge != rec["code_challenge"]:
                raise FakeProviderError("pkce_mismatch")
            rec["used"] = True
            access = "atk_" + uuid.uuid4().hex
            refresh = "rtk_" + uuid.uuid4().hex
            tid = "tok_" + uuid.uuid4().hex[:12]
            self._tokens[tid] = {
                "access_token": access,
                "refresh_token": refresh,
                "scopes": list(rec["scopes"]),
                "provider_id": provider_id,
                "subject": rec["subject"],
                "expires_at": float(self.clock()) + 3600,
            }
            return {
                "access_token": access,
                "refresh_token": refresh,
                "scopes": list(rec["scopes"]),
                "expires_in": 3600,
                "token_id": tid,
                "subject_hash": hashlib.sha256(rec["subject"].encode()).hexdigest()[:32],
            }

    def refresh(self, *, session_id: str = "", refresh_token: str = "") -> dict[str, Any]:
        if self.fail_mode == "timeout":
            raise FakeProviderError("refresh_timeout")
        if self.fail_mode == "unavailable":
            raise FakeProviderError("provider_unavailable")
        access = "atk_" + uuid.uuid4().hex
        new_refresh = ("rtk_" + uuid.uuid4().hex) if self.rotate_refresh else refresh_token
        return {
            "access_token": access,
            "refresh_token": new_refresh,
            "scopes": [],  # empty means keep previous
            "expires_in": 3600,
        }

    def revoke(self, token: str) -> dict[str, Any]:
        return {"revoked": True}

    def narrow_scopes(self, code: str, scopes: list[str]) -> None:
        with self._lock:
            if code in self._codes:
                self._codes[code]["scopes"] = list(scopes)
