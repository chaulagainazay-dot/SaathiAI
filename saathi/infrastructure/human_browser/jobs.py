"""Signed jobs — the security boundary of the Human Browser Driver.

The VM never controls your personal browser and never holds your cookies. It
signs a *job* ("publish this video to profile ajay/youtube") and drops it on a
queue. The Mac Agent, running on your trusted machine where Chrome is already
logged in, verifies the signature and executes it. Your sessions stay off the
server.

Protections: HMAC-SHA256 over a canonical serialization (tamper), `expires_at`
(stale jobs rejected), and a one-time `nonce` (replay rejected).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass, field, asdict


class JobError(Exception): ...
class BadSignature(JobError): ...
class JobExpired(JobError): ...
class JobReplayed(JobError): ...


# fields covered by the signature (order-independent via sorted canonicalization)
_SIGNED = ("id", "capability", "payload", "profile", "issued_at", "expires_at", "nonce")


@dataclass
class HumanJob:
    capability: str                 # "open" | "login" | "upload" | "publish_video" | …
    payload: dict = field(default_factory=dict)
    profile: str = ""               # e.g. "ajay/youtube"
    ttl_seconds: int = 300
    id: str = field(default_factory=lambda: secrets.token_hex(8))
    nonce: str = field(default_factory=lambda: secrets.token_hex(16))
    issued_at: float = field(default_factory=time.time)
    expires_at: float = 0.0

    def __post_init__(self):
        if not self.expires_at:
            self.expires_at = self.issued_at + self.ttl_seconds

    def canonical(self) -> bytes:
        d = {k: getattr(self, k) for k in _SIGNED}
        return json.dumps(d, sort_keys=True, separators=(",", ":")).encode()

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "HumanJob":
        return cls(**{k: d[k] for k in ("capability", "payload", "profile", "ttl_seconds",
                                        "id", "nonce", "issued_at", "expires_at") if k in d})


def sign(job: HumanJob, secret: str) -> str:
    if not secret:
        raise JobError("no signing secret configured")
    return hmac.new(secret.encode(), job.canonical(), hashlib.sha256).hexdigest()


class NonceStore:
    """Remembers spent nonces to reject replays. In-memory; a durable store can
    replace it. Prunes entries past their expiry so it doesn't grow forever."""
    def __init__(self):
        self._seen: dict[str, float] = {}

    def check_and_add(self, nonce: str, expires_at: float, *, now: float) -> None:
        self._seen = {n: e for n, e in self._seen.items() if e > now}   # prune
        if nonce in self._seen:
            raise JobReplayed(f"nonce already used: {nonce}")
        self._seen[nonce] = expires_at


def verify(job: HumanJob, signature: str, secret: str, *,
           nonces: NonceStore | None = None, now: float | None = None) -> None:
    """Raise if the job is forged, stale, or replayed. Constant-time HMAC compare."""
    now = time.time() if now is None else now
    expected = sign(job, secret)
    if not hmac.compare_digest(expected, signature or ""):
        raise BadSignature("job signature mismatch")
    if now > job.expires_at:
        raise JobExpired(f"job expired at {job.expires_at}")
    if nonces is not None:
        nonces.check_and_add(job.nonce, job.expires_at, now=now)
