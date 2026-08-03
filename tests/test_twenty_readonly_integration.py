from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path

import pytest

from saathi.integrations.twenty import (
    FixtureTransport,
    TwentyClient,
    TwentyConfig,
    TwentyConfigurationError,
    TwentyContractError,
    TwentyReadOnlyViolation,
    TwentyReadService,
    TwentyResponse,
    TwentyScope,
    TwentyTransportError,
    TwentyWebhookVerifier,
    twenty_connector_manifest,
)
from saathi.integrations.twenty.errors import TwentyScopeViolation
from saathi.connectors.registry.validation import validate_manifest


SCOPE = TwentyScope("org_demo", "workspace_demo")
OTHER_SCOPE = TwentyScope("org_other", "workspace_other")


def fixture_body(name: str) -> dict:
    path = Path(__file__).parent / "fixtures" / "twenty" / name
    return json.loads(path.read_text())


def fixture_client(*, response: TwentyResponse | None = None, audit=None):
    response = response or TwentyResponse(200, fixture_body("companies.json"))
    transport = FixtureTransport({("org_demo", "workspace_demo", "GET", "/rest/companies"): response})
    return TwentyClient(TwentyConfig(), transport, audit_sink=audit), transport


def test_configuration_defaults_are_localhost_read_only_and_disabled():
    cfg = TwentyConfig()
    cfg.validate()
    assert cfg.base_url == "http://127.0.0.1:3020"
    assert cfg.read_only is True
    assert cfg.integration_enabled is False


@pytest.mark.parametrize("url", ["not-a-url", "ftp://localhost", "https://crm.example.com", "http://user:pass@localhost:3020"])
def test_invalid_or_nonlocal_url_fails_closed(url):
    with pytest.raises(TwentyConfigurationError):
        TwentyConfig(base_url=url).validate()


def test_missing_credential_reference_is_explicit_when_connectivity_requested():
    with pytest.raises(TwentyConfigurationError, match="credential_reference_required"):
        TwentyConfig().validate(require_credentials=True)


def test_raw_credential_is_rejected_in_favor_of_reference():
    with pytest.raises(TwentyConfigurationError, match="raw_credential_forbidden"):
        TwentyConfig(credential_reference="Bearer super-secret").validate()


def test_deterministic_company_pagination_and_schema_mapping():
    client, transport = fixture_client()
    page = TwentyReadService(client, scope=SCOPE).list_records("companies", limit=2)
    assert [record["record"]["name"] for record in page.records] == ["Demo Hospital", "Demo Food Supplier"]
    assert page.has_next_page is True
    assert page.next_cursor == "demo-cursor-2"
    assert page.records[0]["org_id"] == "org_demo"
    assert page.records[0]["read_only"] is True
    assert transport.calls == 1


def test_unknown_object_and_bad_pagination_rejected():
    client, _ = fixture_client()
    service = TwentyReadService(client, scope=SCOPE)
    with pytest.raises(TwentyContractError, match="unknown_or_unsupported"):
        service.list_records("payments")
    with pytest.raises(TwentyContractError, match="pagination_limit"):
        service.list_records("companies", limit=1000)


def test_cross_organization_and_workspace_access_rejected_before_transport():
    client, transport = fixture_client()
    service = TwentyReadService(client, scope=SCOPE)
    with pytest.raises(TwentyScopeViolation):
        service.list_records("companies", scope=OTHER_SCOPE)
    assert transport.calls == 0


def test_malformed_response_and_connection_failure_are_normalized():
    client, _ = fixture_client(response=TwentyResponse(200, {"data": "bad", "pageInfo": {}}))
    with pytest.raises(TwentyContractError, match="malformed_twenty_page"):
        TwentyReadService(client, scope=SCOPE).list_records("companies")
    missing = FixtureTransport({})
    client = TwentyClient(TwentyConfig(), missing)
    with pytest.raises(TwentyTransportError, match="fixture_missing"):
        client.get("/rest/companies", scope=SCOPE)


def test_timeout_is_normalized_without_leaking_payload():
    class TimeoutTransport:
        def send(self, request, *, timeout_seconds):
            raise TimeoutError("raw transport details")

    with pytest.raises(TwentyTransportError, match="twenty_timeout"):
        TwentyClient(TwentyConfig(), TimeoutTransport()).get("/healthz", scope=SCOPE)


def test_write_rejection_and_audit_emission():
    audit = []
    client, _ = fixture_client(audit=lambda event, detail: audit.append((event, detail)))
    with pytest.raises(TwentyReadOnlyViolation):
        client.reject_write("create_note")
    assert audit == [("twenty.write.rejected", {"operation": "create_note", "reason": "read_only_boundary"})]


def test_manifest_composes_with_canonical_registry_and_never_grants_authority():
    manifest = twenty_connector_manifest()
    validation = validate_manifest(manifest, strict=True)
    assert validation.ok, validation.errors
    assert manifest.connector_id == "twenty_crm_readonly"
    assert manifest.trading is False
    assert manifest.rollout_compatible == ("OFF", "SHADOW")
    assert set(manifest.capability_classes) == {"READ"}
    assert "create" in manifest.denied_operations
    assert manifest.secret_references == ("TWENTY_API_CREDENTIAL_REFERENCE",)


def signed_webhook(*, event="company.updated", event_id="evt_demo", scope=SCOPE, secret="fixture-secret", timestamp="1000000000000"):
    raw = json.dumps({"event": event, "data": {"id": "demo-company-hospital", "name": "Demo Hospital"}}, separators=(",", ":")).encode()
    signature = hmac.new(secret.encode(), timestamp.encode() + b":" + raw, hashlib.sha256).hexdigest()
    verifier = TwentyWebhookVerifier(
        secret_resolver=lambda ref: secret if ref == "ref://twenty/webhook" else None,
        allowed_events={"company.updated", "person.created"},
        clock=lambda: 1_000_000_000,
    )
    result = verifier.verify(
        scope=scope,
        credential_reference="ref://twenty/webhook",
        raw_body=raw,
        signature=signature,
        timestamp=timestamp,
        event_id=event_id,
    )
    return verifier, result, raw, signature


def test_valid_webhook_becomes_observation_with_no_execution():
    _, result, _, _ = signed_webhook()
    assert result.accepted is True
    assert result.execution_requested is False
    assert result.observation["direct_execution"] is False
    assert result.observation["mission_state"] == "PROPOSAL_ONLY"
    assert result.observation["org_id"] == SCOPE.org_id


def test_webhook_signature_failure_stale_timestamp_and_unsupported_event():
    verifier, _, raw, _ = signed_webhook()
    bad = verifier.verify(scope=SCOPE, credential_reference="ref://twenty/webhook", raw_body=raw, signature="bad", timestamp="1000000000000", event_id="evt_bad")
    assert (bad.accepted, bad.reason) == (False, "invalid_signature")
    stale = verifier.verify(scope=SCOPE, credential_reference="ref://twenty/webhook", raw_body=raw, signature="bad", timestamp="1", event_id="evt_stale")
    assert stale.reason == "stale_timestamp"
    _, unsupported, _, _ = signed_webhook(event="opportunity.deleted")
    assert unsupported.reason == "unsupported_event_type"


def test_webhook_replay_and_scope_keys_are_isolated():
    verifier, first, raw, signature = signed_webhook()
    assert first.accepted
    replay = verifier.verify(scope=SCOPE, credential_reference="ref://twenty/webhook", raw_body=raw, signature=signature, timestamp="1000000000000", event_id="evt_demo")
    assert replay.reason == "duplicate_or_replayed_event"
    other = verifier.verify(scope=OTHER_SCOPE, credential_reference="ref://twenty/webhook", raw_body=raw, signature=signature, timestamp="1000000000000", event_id="evt_demo")
    assert other.accepted is True
    assert other.observation["org_id"] == "org_other"


def test_webhook_secret_redaction_and_audit():
    audit = []
    raw = b'{"event":"company.updated","data":{"id":"demo"}}'
    verifier = TwentyWebhookVerifier(
        secret_resolver=lambda ref: "fixture-secret",
        allowed_events={"company.updated"},
        audit_sink=lambda event, detail: audit.append((event, detail)),
        clock=lambda: 1000,
    )
    result = verifier.verify(scope=SCOPE, credential_reference="ref://twenty/webhook", raw_body=raw, signature="invalid", timestamp="1000", event_id="evt")
    assert result.accepted is False
    assert all("secret" not in json.dumps(detail).lower() for _, detail in audit)


def test_payload_size_and_malformed_json_fail_closed():
    verifier = TwentyWebhookVerifier(secret_resolver=lambda ref: "x", allowed_events={"company.updated"}, clock=lambda: 1000, max_payload_bytes=4)
    too_big = verifier.verify(scope=SCOPE, credential_reference="ref", raw_body=b"12345", signature="x", timestamp="1000", event_id="evt")
    assert too_big.reason == "payload_too_large"
