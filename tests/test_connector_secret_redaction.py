"""Connector surfaces must not disclose credential VALUES.

Observed live: GET /api/v1/connections returned connections.json verbatim, so an
authenticated caller received the Facebook page access token — 202 characters of
live publishing credential — in a 200 response body. The 422 redaction boundary
covers validation errors only; a success response needed its own guard.

Presence must survive redaction: the UI has to show whether a platform is
configured, and that is a different fact from the credential itself.
"""
from __future__ import annotations

import json

from fastapi.testclient import TestClient

from saathi import connections
from saathi.server import app
from saathi.tool_runtime.secrets import REDACTED, is_secret_key

client = TestClient(app, raise_server_exceptions=False)

# The endpoint is auth-gated, so the redaction itself is exercised by calling the
# route function directly. That keeps these tests free of any credential.
from saathi.server import get_connections

SENTINEL = "SENTINEL-PAGE-TOKEN-2f9c1a-do-not-disclose"

SECRET_FIELDS = [
    "page_access_token", "access_token", "refresh_token", "bot_token",
    "client_secret", "api_key", "token", "password", "authorization",
]


def test_the_secret_detector_covers_every_connector_credential_name():
    """The redaction is only as good as the vocabulary behind it."""
    for field in SECRET_FIELDS:
        assert is_secret_key(field), f"{field} is not recognised as a secret"


def test_connections_never_returns_a_credential_value(monkeypatch):
    fake = {
        "facebook": {
            "connected": True, "method": "graph", "handle": "mryeti",
            "page_id": "1234567890", "page_access_token": SENTINEL,
        },
        "telegram": {"connected": True, "bot_token": SENTINEL},
        "youtube": {"connected": True, "refresh_token": SENTINEL},
    }
    monkeypatch.setattr(connections, "get_all", lambda: fake)
    body = json.dumps(get_connections())
    assert SENTINEL not in body, "a credential value reached the response body"


def test_presence_is_still_reported(monkeypatch):
    """Redaction must not blind the UI to whether a platform is configured."""
    fake = {
        "facebook": {"connected": True, "page_access_token": SENTINEL, "page_id": "42"},
        "linkedin": {"connected": True, "page_access_token": ""},
    }
    monkeypatch.setattr(connections, "get_all", lambda: fake)
    body = get_connections()["connections"]
    assert body["facebook"]["has_page_access_token"] is True
    assert body["facebook"]["page_access_token"] == REDACTED
    # An empty credential is absent, not present-but-hidden.
    assert body["linkedin"]["has_page_access_token"] is False


def test_non_secret_settings_survive_untouched(monkeypatch):
    """Handles, ids and webhooks are configuration, not credentials."""
    fake = {"facebook": {"connected": True, "method": "graph", "handle": "mryeti",
                         "page_id": "1234567890", "webhook": "https://example.com/hook"}}
    monkeypatch.setattr(connections, "get_all", lambda: fake)
    fb = get_connections()["connections"]["facebook"]
    assert fb["handle"] == "mryeti"
    assert fb["page_id"] == "1234567890"
    assert fb["webhook"] == "https://example.com/hook"
    assert fb["connected"] is True


def test_a_malformed_entry_does_not_break_the_endpoint(monkeypatch):
    monkeypatch.setattr(connections, "get_all", lambda: {"facebook": "not-a-dict", "x": None})
    out = get_connections()
    assert "connections" in out


def test_connector_accounts_never_return_secrets():
    """The encrypted account store already promises this; hold it to the promise."""
    from saathi.connectors.accounts import default_store

    listed = default_store().list()
    body = json.dumps(listed)
    assert "secret_enc" not in body
    for account in listed:
        assert "secret" not in account, "the raw secret must never be listed"
        assert "has_secret" in account, "presence must still be reported"


def test_the_connections_endpoint_stays_auth_gated():
    """Redaction is defence in depth, not a licence to open the endpoint."""
    assert client.get("/api/v1/connections").status_code == 401
