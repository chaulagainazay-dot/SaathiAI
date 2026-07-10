"""Tests for ToolIntent schema."""
import json
import time
import uuid
from datetime import datetime, timedelta

import pytest

from saathi.execution.toolintent import (
    ToolIntent, ToolIntentBuilder, ActorType, RiskLevel, ApprovalLevel,
    Priority, BusinessUnit, builder
)


class TestToolIntentSchema:
    """Test ToolIntent schema definition and defaults."""

    def test_default_values(self):
        """Test that defaults are set correctly."""
        intent = builder().actor("user-1").mission("m1").capability("email.send", "gmail", "send").reason("test").build()
        assert intent.schema_version == "1.0"
        assert intent.actor_type == ActorType.USER
        assert intent.risk_level == RiskLevel.MEDIUM
        assert intent.approval_level == ApprovalLevel.L1
        assert intent.priority == Priority.NORMAL
        assert intent.timeout == 30
        assert intent.business_unit == BusinessUnit.MR_YETI

    def test_immutability(self):
        """Test that ToolIntent is immutable (frozen dataclass)."""
        intent = builder().actor("user-1").mission("m1").capability("email.send", "gmail", "send").reason("test").build()
        with pytest.raises(Exception):
            intent.intent_id = "new-id"


class TestValidation:
    """Test ToolIntent validation."""

    def test_valid_intent(self):
        """Test that valid intent passes validation."""
        intent = builder().actor("user-1").mission("m1").capability("email.send", "gmail", "send").reason("test").build()
        assert intent.validate() == []

    def test_required_fields(self):
        """Test that required fields are enforced."""
        intent = ToolIntent()
        errors = intent.validate()
        assert len(errors) > 0
        assert any("actor_id" in e for e in errors)
        assert any("mission_id" in e for e in errors)
        assert any("capability" in e for e in errors)

    def test_invalid_uuid(self):
        """Test that invalid UUIDs are rejected."""
        intent = ToolIntent(
            intent_id="not-a-uuid",
            actor_id="user-1",
            mission_id="m1",
            capability="email.send",
            connector_id="gmail",
            operation="send",
            reason="test"
        )
        errors = intent.validate()
        assert any("intent_id" in e for e in errors)

    def test_invalid_enum_actor_type(self):
        """Test that invalid actor_type is rejected."""
        intent = ToolIntent(
            actor_id="user-1",
            actor_type="invalid",  # type: ignore
            mission_id="m1",
            capability="email.send",
            connector_id="gmail",
            operation="send",
            reason="test"
        )
        errors = intent.validate()
        assert any("actor_type" in e for e in errors)

    def test_invalid_idempotency_key(self):
        """Test that invalid idempotency key is rejected."""
        intent = ToolIntent(
            actor_id="user-1",
            mission_id="m1",
            capability="email.send",
            connector_id="gmail",
            operation="send",
            reason="test",
            idempotency_key="not-hex"
        )
        errors = intent.validate()
        assert any("idempotency_key" in e for e in errors)

    def test_invalid_timeout(self):
        """Test that invalid timeout is rejected."""
        intent = ToolIntent(
            actor_id="user-1",
            mission_id="m1",
            capability="email.send",
            connector_id="gmail",
            operation="send",
            reason="test",
            timeout=5000  # > max 3600
        )
        errors = intent.validate()
        assert any("timeout" in e for e in errors)

    def test_future_created_at(self):
        """Test that future created_at is rejected."""
        future = datetime.now().timestamp() + 3600
        intent = ToolIntent(
            actor_id="user-1",
            mission_id="m1",
            capability="email.send",
            connector_id="gmail",
            operation="send",
            reason="test",
            created_at=future
        )
        errors = intent.validate()
        assert any("created_at" in e for e in errors)

    def test_expires_before_created(self):
        """Test that expires_at < created_at is rejected."""
        now = datetime.now().timestamp()
        intent = ToolIntent(
            actor_id="user-1",
            mission_id="m1",
            capability="email.send",
            connector_id="gmail",
            operation="send",
            reason="test",
            created_at=now,
            expires_at=now - 1
        )
        errors = intent.validate()
        assert any("expires_at" in e for e in errors)

    def test_expires_too_far(self):
        """Test that expires_at > 1 year from created is rejected."""
        now = datetime.now().timestamp()
        intent = ToolIntent(
            actor_id="user-1",
            mission_id="m1",
            capability="email.send",
            connector_id="gmail",
            operation="send",
            reason="test",
            created_at=now,
            expires_at=now + (366 * 24 * 3600)
        )
        errors = intent.validate()
        assert any("expires_at" in e for e in errors)

    def test_invalid_parameters_type(self):
        """Test that non-dict parameters are rejected."""
        intent = ToolIntent(
            actor_id="user-1",
            mission_id="m1",
            capability="email.send",
            connector_id="gmail",
            operation="send",
            reason="test",
            parameters="not-dict"  # type: ignore
        )
        errors = intent.validate()
        assert any("parameters" in e for e in errors)


class TestIdempotencyKey:
    """Test idempotency key computation."""

    def test_compute_key(self):
        """Test computing idempotency key from params."""
        params = {"to": "user@example.com", "message": "hello"}
        key = ToolIntent.compute_idempotency_key(params)
        assert len(key) == 64
        assert all(c in "0123456789abcdef" for c in key)

    def test_deterministic_key(self):
        """Test that key computation is deterministic."""
        params = {"to": "user@example.com", "message": "hello"}
        key1 = ToolIntent.compute_idempotency_key(params)
        key2 = ToolIntent.compute_idempotency_key(params)
        assert key1 == key2

    def test_order_independent(self):
        """Test that param order doesn't affect key."""
        params_a = {"to": "user@example.com", "message": "hello"}
        params_b = {"message": "hello", "to": "user@example.com"}
        key_a = ToolIntent.compute_idempotency_key(params_a)
        key_b = ToolIntent.compute_idempotency_key(params_b)
        assert key_a == key_b

    def test_auto_compute_on_build(self):
        """Test that builder auto-computes idempotency key."""
        intent = builder().actor("user-1").mission("m1").capability("email.send", "gmail", "send").reason("test").parameters({"to": "x@y.com"}).build()
        assert len(intent.idempotency_key) == 64

    def test_different_params_different_key(self):
        """Test that different params produce different keys."""
        key1 = ToolIntent.compute_idempotency_key({"to": "a@b.com"})
        key2 = ToolIntent.compute_idempotency_key({"to": "c@d.com"})
        assert key1 != key2


class TestSerialization:
    """Test serialization and deserialization."""

    def test_to_dict(self):
        """Test converting to dict."""
        intent = builder().actor("user-1").mission("m1").capability("email.send", "gmail", "send").reason("test").build()
        d = intent.to_dict()
        assert d["actor_id"] == "user-1"
        assert d["mission_id"] == "m1"
        assert d["capability"] == "email.send"
        assert d["connector_id"] == "gmail"
        # Enums should be converted to strings
        assert d["actor_type"] == "user"
        assert d["risk_level"] == "medium"

    def test_to_json(self):
        """Test converting to JSON."""
        intent = builder().actor("user-1").mission("m1").capability("email.send", "gmail", "send").reason("test").build()
        json_str = intent.to_json()
        data = json.loads(json_str)
        assert data["actor_id"] == "user-1"

    def test_from_dict(self):
        """Test constructing from dict."""
        d = {
            "schema_version": "1.0",
            "intent_id": str(uuid.uuid4()),
            "correlation_id": str(uuid.uuid4()),
            "actor_id": "user-1",
            "actor_type": "user",
            "mission_id": "m1",
            "business_unit": "mr-yeti",
            "capability": "email.send",
            "connector_id": "gmail",
            "operation": "send",
            "reason": "test",
            "risk_level": "medium",
            "approval_level": "L1",
            "idempotency_key": "a" * 64,
            "created_at": datetime.now().timestamp(),
            "expires_at": (datetime.now() + timedelta(hours=24)).timestamp(),
        }
        intent = ToolIntent.from_dict(d)
        assert intent.actor_id == "user-1"
        assert intent.actor_type == ActorType.USER

    def test_from_json(self):
        """Test constructing from JSON."""
        intent1 = builder().actor("user-1").mission("m1").capability("email.send", "gmail", "send").reason("test").build()
        json_str = intent1.to_json()
        intent2 = ToolIntent.from_json(json_str)
        assert intent2.actor_id == intent1.actor_id
        assert intent2.intent_id == intent1.intent_id

    def test_round_trip(self):
        """Test JSON serialization round-trip preserves all data."""
        original = builder().actor("user-1", ActorType.AGENT).mission("m1").business_unit(BusinessUnit.PIELTS).capability("social.post", "instagram", "post").reason("daily content").parameters({"caption": "hello"}).risk(RiskLevel.HIGH, ApprovalLevel.L4).build()
        json_str = original.to_json()
        restored = ToolIntent.from_json(json_str)
        assert restored.to_dict() == original.to_dict()


class TestSecretRedaction:
    """Test safe logging with secret redaction."""

    def test_redact_api_key(self):
        """Test that API keys in parameters are redacted."""
        intent = builder().actor("user-1").mission("m1").capability("api.call", "external", "call").reason("test").parameters({"api_key": "secret123", "url": "http://example.com"}).build()
        safe = intent.to_dict(redact=True)
        assert safe["parameters"]["api_key"] == "***REDACTED***"
        assert safe["parameters"]["url"] == "http://example.com"

    def test_redact_oauth_token(self):
        """Test that OAuth tokens are redacted."""
        intent = builder().actor("user-1").mission("m1").capability("social.post", "facebook", "post").reason("test").parameters({"oauth_token": "fb_token_xyz", "message": "hello"}).build()
        safe = intent.to_dict(redact=True)
        assert safe["parameters"]["oauth_token"] == "***REDACTED***"
        assert safe["parameters"]["message"] == "hello"

    def test_safe_repr(self):
        """Test safe_repr returns redacted JSON."""
        intent = builder().actor("user-1").mission("m1").capability("api.call", "external", "call").reason("test").parameters({"secret": "password123"}).build()
        safe = intent.safe_repr()
        assert "***REDACTED***" in safe
        assert "password123" not in safe

    def test_redact_metadata(self):
        """Test that secrets in metadata are also redacted."""
        intent = builder().actor("user-1").mission("m1").capability("email.send", "gmail", "send").reason("test").metadata({"auth_token": "secret"}).build()
        safe = intent.to_dict(redact=True)
        assert safe["metadata"]["auth_token"] == "***REDACTED***"


class TestBuilder:
    """Test ToolIntent builder fluent interface."""

    def test_builder_chain(self):
        """Test that builder allows method chaining."""
        intent = (builder()
                  .actor("user-1", ActorType.USER)
                  .mission("mr-yeti")
                  .business_unit(BusinessUnit.MR_YETI)
                  .capability("video.upload", "youtube", "upload_video")
                  .parameters({"title": "Episode 5"})
                  .reason("Daily release")
                  .risk(RiskLevel.HIGH, ApprovalLevel.L4)
                  .timeout(600)
                  .build())
        assert intent.actor_id == "user-1"
        assert intent.mission_id == "mr-yeti"
        assert intent.timeout == 600

    def test_builder_validation_on_build(self):
        """Test that builder validates on build()."""
        b = builder()
        # Missing required fields
        with pytest.raises(ValueError) as exc_info:
            b.build()
        assert "Invalid ToolIntent" in str(exc_info.value)

    def test_builder_auto_idempotency_key(self):
        """Test that builder auto-computes idempotency_key."""
        intent = (builder()
                  .actor("user-1").mission("m1")
                  .capability("email.send", "gmail", "send")
                  .reason("test")
                  .parameters({"to": "x@y.com"})
                  .build())
        assert len(intent.idempotency_key) == 64
        # Key should match computed value
        expected = ToolIntent.compute_idempotency_key({"to": "x@y.com"})
        assert intent.idempotency_key == expected


class TestExamples:
    """Test real-world examples."""

    def test_low_risk_read(self):
        """Test L1 read-only intent."""
        intent = (builder()
                  .actor("user-1")
                  .mission("mr-yeti")
                  .business_unit(BusinessUnit.MR_YETI)
                  .capability("social.analytics", "youtube", "get_channel_stats")
                  .parameters({"channel": "@mryeti"})
                  .reason("Daily metrics check")
                  .risk(RiskLevel.LOW, ApprovalLevel.L1)
                  .build())
        assert intent.validate() == []
        assert intent.risk_level == RiskLevel.LOW
        assert intent.approval_level == ApprovalLevel.L1

    def test_high_risk_publish(self):
        """Test L4 external publish intent."""
        intent = (builder()
                  .actor("director-creative", ActorType.AGENT)
                  .mission("mr-yeti")
                  .business_unit(BusinessUnit.MR_YETI)
                  .capability("video.upload", "youtube", "upload_video")
                  .parameters({
                      "title": "Episode 5: Past Continuous",
                      "description": "Teaching past continuous...",
                      "playlist": "mr-yeti-playlist"
                  })
                  .reason("Content release per editorial schedule")
                  .risk(RiskLevel.HIGH, ApprovalLevel.L4)
                  .timeout(600)
                  .build())
        assert intent.validate() == []
        assert intent.risk_level == RiskLevel.HIGH
        assert intent.approval_level == ApprovalLevel.L4

    def test_critical_payment(self):
        """Test L4 critical payment intent."""
        intent = (builder()
                  .actor("trading-agent", ActorType.AGENT)
                  .mission("surmount-trades")
                  .business_unit(BusinessUnit.SURMOUNT)
                  .capability("payments.charge", "stripe", "create_payment")
                  .parameters({
                      "amount": 5000000,
                      "currency": "usd",
                      "customer": "acme-corp"
                  })
                  .reason("Invoice #INV-2026-001 payment")
                  .risk(RiskLevel.CRITICAL, ApprovalLevel.L4)
                  .timeout(120)
                  .build())
        assert intent.validate() == []
        assert intent.risk_level == RiskLevel.CRITICAL


class TestBusinessUnits:
    """Test business_unit field coverage."""

    def test_all_business_units(self):
        """Test that all business units can be used."""
        for unit in BusinessUnit:
            intent = (builder()
                      .actor("user-1")
                      .mission("test")
                      .business_unit(unit)
                      .capability("email.send", "gmail", "send")
                      .reason("test")
                      .build())
            assert intent.business_unit == unit
            assert intent.validate() == []

    def test_business_unit_immutable(self):
        """Test that business_unit is immutable."""
        intent = (builder()
                  .actor("user-1").mission("m1")
                  .business_unit(BusinessUnit.MR_YETI)
                  .capability("email.send", "gmail", "send")
                  .reason("test")
                  .build())
        with pytest.raises(Exception):
            intent.business_unit = BusinessUnit.PIELTS


class TestExpiry:
    """Test expiry logic."""

    def test_not_expired(self):
        """Test is_expired for future expiry."""
        future = datetime.now().timestamp() + 3600
        intent = ToolIntent(
            actor_id="user-1",
            mission_id="m1",
            capability="email.send",
            connector_id="gmail",
            operation="send",
            reason="test",
            expires_at=future
        )
        assert not intent.is_expired()

    def test_expired(self):
        """Test is_expired for past expiry."""
        past = datetime.now().timestamp() - 3600
        intent = ToolIntent(
            actor_id="user-1",
            mission_id="m1",
            capability="email.send",
            connector_id="gmail",
            operation="send",
            reason="test",
            expires_at=past
        )
        assert intent.is_expired()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
