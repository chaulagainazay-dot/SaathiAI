"""Canonical IELTSAlert contracts and lifecycle rules.

These records contain bounded text and artifact references only. They never contain
raw audio/image data, payment credentials, or provider secrets.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class IELTSValidationError(ValueError):
    pass


class ExamType(str, Enum):
    ACADEMIC = "academic"
    GENERAL_TRAINING = "general_training"


class Skill(str, Enum):
    READING = "reading"
    LISTENING = "listening"
    WRITING = "writing"
    SPEAKING = "speaking"


class AlertStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    MATCHED = "matched"
    NOTIFIED = "notified"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


ALERT_TRANSITIONS = {
    AlertStatus.DRAFT: {AlertStatus.ACTIVE, AlertStatus.CANCELLED},
    AlertStatus.ACTIVE: {AlertStatus.PAUSED, AlertStatus.MATCHED, AlertStatus.EXPIRED, AlertStatus.CANCELLED},
    AlertStatus.PAUSED: {AlertStatus.ACTIVE, AlertStatus.EXPIRED, AlertStatus.CANCELLED},
    AlertStatus.MATCHED: {AlertStatus.NOTIFIED, AlertStatus.ACTIVE, AlertStatus.EXPIRED, AlertStatus.CANCELLED},
    AlertStatus.NOTIFIED: {AlertStatus.ACTIVE, AlertStatus.EXPIRED, AlertStatus.CANCELLED},
    AlertStatus.EXPIRED: set(),
    AlertStatus.CANCELLED: set(),
}


class PaymentStatus(str, Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


PAYMENT_TRANSITIONS = {
    PaymentStatus.DRAFT: {PaymentStatus.SUBMITTED, PaymentStatus.CANCELLED},
    PaymentStatus.SUBMITTED: {PaymentStatus.UNDER_REVIEW, PaymentStatus.CANCELLED, PaymentStatus.EXPIRED},
    PaymentStatus.UNDER_REVIEW: {PaymentStatus.APPROVED, PaymentStatus.REJECTED, PaymentStatus.EXPIRED},
    PaymentStatus.APPROVED: set(),
    PaymentStatus.REJECTED: set(),
    PaymentStatus.CANCELLED: set(),
    PaymentStatus.EXPIRED: set(),
}


def bounded(value: Any, name: str, *, maximum: int, required: bool = False) -> str:
    text = str(value or "").strip()
    if required and not text:
        raise IELTSValidationError(f"{name} is required")
    if len(text) > maximum:
        raise IELTSValidationError(f"{name} exceeds {maximum} characters")
    lowered = text.lower()
    forbidden = ("password", "cvv", "private key", "wallet secret", "authorization: bearer")
    if any(marker in lowered for marker in forbidden):
        raise IELTSValidationError(f"{name} contains prohibited credential material")
    return text


def target_band(value: Any) -> float:
    try:
        band = float(value)
    except (TypeError, ValueError) as exc:
        raise IELTSValidationError("target_band must be numeric") from exc
    if band < 4.0 or band > 9.0 or band * 2 != int(band * 2):
        raise IELTSValidationError("target_band must be 4.0–9.0 in 0.5 steps")
    return band


@dataclass(frozen=True)
class IELTSRecord:
    record_id: str
    record_type: str
    org_id: str
    workspace_id: str
    owner_id: str
    status: str
    body: dict[str, Any] = field(default_factory=dict)
    project_id: str = ""
    mission_id: str = ""
    idempotency_key: str = ""
    version: int = 1
    created_at: float = 0.0
    updated_at: float = 0.0
    archived_at: float = 0.0

    def to_public(self) -> dict[str, Any]:
        return asdict(self)


def validate_profile(body: dict[str, Any]) -> dict[str, Any]:
    return {
        "display_name": bounded(body.get("display_name"), "display_name", maximum=100, required=True),
        "timezone": bounded(body.get("timezone", "Asia/Kathmandu"), "timezone", maximum=64),
        "preferred_language": bounded(body.get("preferred_language", "en"), "preferred_language", maximum=16),
    }


def validate_goal(body: dict[str, Any]) -> dict[str, Any]:
    try:
        exam_type = ExamType(str(body.get("exam_type", ""))).value
    except ValueError as exc:
        raise IELTSValidationError("exam_type must be academic or general_training") from exc
    planned = bounded(body.get("planned_test_date"), "planned_test_date", maximum=10, required=True)
    return {
        "exam_type": exam_type,
        "target_band": target_band(body.get("target_band")),
        "planned_test_date": planned,
        "daily_minutes": max(10, min(int(body.get("daily_minutes", 30)), 240)),
    }


def validate_practice(body: dict[str, Any]) -> dict[str, Any]:
    try:
        skill = Skill(str(body.get("skill", ""))).value
    except ValueError as exc:
        raise IELTSValidationError("skill must be reading, listening, writing, or speaking") from exc
    result = {
        "skill": skill,
        "task_type": bounded(body.get("task_type"), "task_type", maximum=40, required=True),
        "prompt": bounded(body.get("prompt"), "prompt", maximum=4000, required=True),
        "response": bounded(body.get("response"), "response", maximum=12000, required=True),
        "duration_seconds": max(0, min(int(body.get("duration_seconds", 0)), 14400)),
        "artifact_ref": bounded(body.get("artifact_ref"), "artifact_ref", maximum=500),
        "transcript_ref": bounded(body.get("transcript_ref"), "transcript_ref", maximum=500),
    }
    if skill == Skill.SPEAKING.value and not (result["artifact_ref"] or result["response"]):
        raise IELTSValidationError("speaking practice requires response text or artifact_ref")
    return result


def validate_alert(body: dict[str, Any]) -> dict[str, Any]:
    try:
        exam_type = ExamType(str(body.get("exam_type", ""))).value
    except ValueError as exc:
        raise IELTSValidationError("exam_type must be academic or general_training") from exc
    locations = body.get("preferred_locations") or []
    if not isinstance(locations, list) or not locations or len(locations) > 10:
        raise IELTSValidationError("preferred_locations requires 1–10 entries")
    return {
        "exam_type": exam_type,
        "test_format": bounded(body.get("test_format", "computer"), "test_format", maximum=20),
        "preferred_locations": [bounded(x, "location", maximum=100, required=True) for x in locations],
        "date_from": bounded(body.get("date_from"), "date_from", maximum=10, required=True),
        "date_to": bounded(body.get("date_to"), "date_to", maximum=10, required=True),
        "expires_on": bounded(body.get("expires_on"), "expires_on", maximum=10, required=True),
        "notification_channel": bounded(body.get("notification_channel", "in_app"), "notification_channel", maximum=20),
        "source": "local_fixture",
        "live_availability": False,
    }


def validate_payment(body: dict[str, Any]) -> dict[str, Any]:
    amount = str(body.get("amount", "")).strip()
    try:
        numeric = float(amount)
    except ValueError as exc:
        raise IELTSValidationError("amount must be numeric") from exc
    if numeric <= 0 or numeric > 1000000:
        raise IELTSValidationError("amount is outside the supported manual range")
    return {
        "product": bounded(body.get("product"), "product", maximum=100, required=True),
        "amount": f"{numeric:.2f}",
        "currency": bounded(body.get("currency", "NPR"), "currency", maximum=3, required=True).upper(),
        "payment_method_label": bounded(body.get("payment_method_label"), "payment_method_label", maximum=80, required=True),
        "transaction_reference": bounded(body.get("transaction_reference"), "transaction_reference", maximum=120, required=True),
        "evidence_ref": bounded(body.get("evidence_ref"), "evidence_ref", maximum=500, required=True),
        "submission_note": bounded(body.get("submission_note"), "submission_note", maximum=1000),
        "disclaimer": "Manual verification only; no payment settlement is performed.",
    }

