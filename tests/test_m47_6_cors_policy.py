"""M47.6 CORS policy unit tests — no wildcard, fail-closed production."""
from __future__ import annotations

import pytest

from saathi.cors_policy import (
    CORS_ALLOW_HEADERS,
    CORS_ALLOW_METHODS,
    origin_allowed,
    parse_cors_origins,
    resolve_cors_origins,
    resolve_environment,
)


class TestParse:
    def test_empty(self):
        assert parse_cors_origins("") == []
        assert parse_cors_origins(None) == []

    def test_list(self):
        assert parse_cors_origins("http://a.com, http://b.com") == [
            "http://a.com",
            "http://b.com",
        ]

    def test_rejects_wildcard(self):
        assert parse_cors_origins("*,http://a.com") == ["http://a.com"]
        assert parse_cors_origins("*") == []


class TestResolve:
    def test_explicit_env_value_wins(self):
        got = resolve_cors_origins("http://ui.example", environment="production")
        assert got == ["http://ui.example"]

    def test_production_fail_closed_when_unset(self):
        assert resolve_cors_origins("", environment="production") == []
        assert resolve_cors_origins("", environment="staging") == []
        assert resolve_cors_origins("", environment="canary") == []

    def test_development_defaults_include_cert_ports(self):
        got = resolve_cors_origins("", environment="development")
        assert "http://localhost:3000" in got
        assert "http://127.0.0.1:3110" in got
        assert "http://127.0.0.1:3000" in got
        assert "*" not in got

    def test_wildcard_stripped_even_if_set(self):
        assert resolve_cors_origins("*,http://ok.local") == ["http://ok.local"]


class TestOriginAllowed:
    def test_allowed(self):
        assert origin_allowed("http://localhost:3000", ["http://localhost:3000"]) is True

    def test_denied(self):
        assert origin_allowed("http://evil.example", ["http://localhost:3000"]) is False

    def test_missing_origin(self):
        assert origin_allowed(None, ["http://localhost:3000"]) is False
        assert origin_allowed("", ["http://localhost:3000"]) is False


class TestBounds:
    def test_methods_bounded(self):
        assert "*" not in CORS_ALLOW_METHODS
        assert "GET" in CORS_ALLOW_METHODS
        assert "OPTIONS" in CORS_ALLOW_METHODS

    def test_headers_include_session(self):
        assert "*" not in CORS_ALLOW_HEADERS
        assert any("session" in h.lower() for h in CORS_ALLOW_HEADERS)
        assert "Content-Type" in CORS_ALLOW_HEADERS


class TestEnvironment:
    def test_default_development(self, monkeypatch):
        monkeypatch.delenv("SAATHI_ENV", raising=False)
        monkeypatch.delenv("SAATHI_ENVIRONMENT", raising=False)
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        assert resolve_environment() == "development"
