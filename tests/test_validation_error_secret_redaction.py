"""A 422 must never echo the credential that was submitted.

Observed live: POSTing to /api/v1/platform/auth/login without the required
`email` field returned a validation error whose `input` carried the submitted
password verbatim, which then landed in terminal scrollback. FastAPI's default
RequestValidationError handler reflects the offending input, so this is a
property of EVERY route that takes a body — not of one endpoint.

These tests pin the boundary, so a new endpoint cannot reintroduce the leak by
forgetting about it.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from saathi.server import app
from saathi.tool_runtime.secrets import REDACTED

SENTINELS = {
    "password": "SENTINEL-PASSWORD-b3a91f",
    "token": "SENTINEL-TOKEN-b3a91f",
    "api_key": "SENTINEL-APIKEY-b3a91f",
    "client_secret": "SENTINEL-CLIENTSECRET-b3a91f",
    "authorization": "SENTINEL-AUTHZ-b3a91f",
    "refresh_token": "SENTINEL-REFRESH-b3a91f",
}

client = TestClient(app, raise_server_exceptions=False)


def _post_missing_required_field(payload: dict):
    """A body that is valid JSON but fails model validation, so a 422 is raised."""
    return client.post("/api/v1/platform/auth/login", json=payload)


def test_a_validation_error_does_not_echo_a_submitted_password():
    res = _post_missing_required_field({"password": SENTINELS["password"]})
    assert res.status_code == 422, res.status_code
    assert SENTINELS["password"] not in res.text


def test_no_secret_field_name_leaks_its_value():
    """Not a special case for `password` — the whole credential vocabulary."""
    res = _post_missing_required_field(dict(SENTINELS))
    assert res.status_code == 422
    for field, sentinel in SENTINELS.items():
        assert sentinel not in res.text, f"{field} was echoed back to the caller"


def test_a_secret_nested_inside_an_object_is_still_redacted():
    res = _post_missing_required_field(
        {"profile": {"credentials": {"password": SENTINELS["password"]}}}
    )
    assert res.status_code == 422
    assert SENTINELS["password"] not in res.text


def test_a_secret_inside_a_list_is_still_redacted():
    res = _post_missing_required_field({"items": [{"api_key": SENTINELS["api_key"]}]})
    assert res.status_code == 422
    assert SENTINELS["api_key"] not in res.text


def test_the_field_name_survives_so_the_error_stays_actionable():
    """Redaction must not turn a useful 422 into an unusable one.

    Naming the field "password" discloses nothing; the VALUE is the secret. A
    caller still has to be able to see which field was wrong.
    """
    res = _post_missing_required_field({"password": SENTINELS["password"]})
    body = res.json()
    assert "detail" in body
    locs = [".".join(str(x) for x in (e.get("loc") or ())) for e in body["detail"]]
    assert any("email" in loc for loc in locs), locs
    assert body["detail"], "the error list must not be emptied to achieve redaction"


def test_a_non_secret_value_is_still_shown():
    """Blanket-dropping `input` would be safe but would blind ordinary debugging."""
    res = client.post("/api/v1/platform/auth/login", json={"email": 12345})
    assert res.status_code == 422
    # The offending non-secret value stays visible somewhere in the response.
    assert "12345" in res.text


def test_the_redaction_marker_is_the_repo_wide_one():
    res = _post_missing_required_field({"password": SENTINELS["password"]})
    assert REDACTED in res.text


def test_a_malformed_body_still_returns_422_and_not_a_crash():
    """The handler must never raise.

    A malformed body reaches the handler as raw BYTES, which json cannot encode.
    The first version of this handler threw on that input, and an exception
    inside an exception handler does not become a 422 — it escapes as an
    unhandled 500. That turned a redaction fix into an availability bug on every
    endpoint that takes a body.
    """
    res = client.post(
        "/api/v1/platform/auth/login",
        content=b"not json",
        headers={"content-type": "application/json"},
    )
    assert res.status_code == 422, res.status_code
    assert res.json()["detail"], "the error body must still be useful"


def test_a_body_that_is_not_an_object_is_handled():
    for payload in ("a string", 42, [1, 2, 3], None, True):
        res = client.post("/api/v1/platform/auth/login", json=payload)
        assert res.status_code == 422, f"{payload!r} produced {res.status_code}"


def test_a_secret_inside_a_malformed_nested_shape_is_still_redacted():
    res = client.post(
        "/api/v1/platform/auth/login",
        json={"password": {"nested": [{"token": SENTINELS["token"]}]}},
    )
    assert res.status_code == 422
    assert SENTINELS["token"] not in res.text
