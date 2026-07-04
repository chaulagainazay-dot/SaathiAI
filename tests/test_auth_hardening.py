"""Regression tests for reverse-proxy auth hardening (public-deployment safety).

Behind Caddy every request to FastAPI arrives from 127.0.0.1, so peer address
alone cannot be trusted. `_is_local` must treat proxied traffic (carrying
X-Forwarded-For) as remote, and `_is_authed` must NOT wave through proxied
callers when no password is configured. See saathi/server.py.
"""
import saathi.server as s


class _Req:
    def __init__(self, host, headers=None):
        self.client = type("C", (), {"host": host})()
        self.headers = headers or {}


def test_genuine_loopback_is_local():
    assert s._is_local(_Req("127.0.0.1")) is True
    assert s._is_local(_Req("::1")) is True


def test_proxied_loopback_is_not_local():
    # Caddy stamps X-Forwarded-For on every proxied hop.
    assert s._is_local(_Req("127.0.0.1", {"x-forwarded-for": "8.8.8.8"})) is False
    assert s._is_local(_Req("127.0.0.1", {"x-forwarded-host": "evil.example"})) is False


def test_external_peer_is_not_local():
    assert s._is_local(_Req("8.8.8.8")) is False


def test_is_authed_without_password_rejects_proxied(monkeypatch):
    # No password configured → only genuine local callers are trusted.
    monkeypatch.setattr(s, "_PASSWORD_HASH", "")
    assert s._is_authed(_Req("127.0.0.1")) is True
    assert s._is_authed(_Req("127.0.0.1", {"x-forwarded-for": "8.8.8.8"})) is False
