"""M15 webhook platform — signature verification + timestamp + replay defense.

Inbound provider events are UNTRUSTED. A webhook is accepted only if:
  1. the HMAC signature over the raw body verifies against the shared secret
  2. the timestamp is within a freshness window (anti-replay by age)
  3. the dedup key has not been seen (anti-replay by identity)
Accepted events are normalized and stored; they NEVER trigger side effects
directly — they enqueue work that still flows through the ExecutionEngine.
"""
from __future__ import annotations

import hashlib
import hmac
import time
from typing import Optional

from saathi.connectors.platform import store as S


class WebhookError(Exception):
    pass


def verify_signature(*, secret: str, raw_body: bytes, signature: str,
                     algo: str = "sha256") -> bool:
    """Constant-time HMAC verification. secret is resolved in-process only."""
    if not secret or not signature:
        return False
    mac = hmac.new(secret.encode(), raw_body, getattr(hashlib, algo))
    expected = mac.hexdigest()
    # accept "sha256=..." prefixed form too
    got = signature.split("=", 1)[1] if "=" in signature else signature
    return hmac.compare_digest(expected, got)


def receive(*, connector_id: str, raw_body: bytes, signature: str,
            event_ts: float, dedup_key: str, secret: str,
            freshness_sec: int = 300, normalized: Optional[dict] = None,
            store: Optional[S.ConnectorStore] = None) -> dict:
    """Validate + persist an inbound webhook. Returns an outcome dict.

    outcome.accepted is False for bad-signature / stale / replay — with a
    reason — and the event is not stored (replay returns accepted=False,
    reason='replay')."""
    st = store or S.default_store()
    if not verify_signature(secret=secret, raw_body=raw_body, signature=signature):
        st.event("webhook.bad_signature", {"connector": connector_id})
        return {"accepted": False, "reason": "bad_signature"}
    age = abs(time.time() - event_ts)
    if age > freshness_sec:
        st.event("webhook.stale", {"connector": connector_id, "age": age})
        return {"accepted": False, "reason": "stale", "age": age}
    rec_id = st.record_webhook(connector_id=connector_id, dedup_key=dedup_key,
                              event_ts=event_ts, normalized=normalized or {})
    if rec_id is None:  # unique dedup index rejected it → replay
        st.event("webhook.replay", {"connector": connector_id, "dedup_key": dedup_key})
        return {"accepted": False, "reason": "replay"}
    return {"accepted": True, "event_id": rec_id}
