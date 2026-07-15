"""M17.26 — Privacy-safe browser evidence classification and redaction.

Deterministic sources first (selectors, input types, ARIA, autofill, mission tags).
OCR is optional secondary defense only — failure must not expose sensitive screenshots.
Raw screenshot bytes, secrets, and full DOM are never logged.
"""
from __future__ import annotations

import hashlib
import re
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class EvidenceClass(str, Enum):
    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"
    CONFIDENTIAL = "CONFIDENTIAL"
    SENSITIVE_PERSONAL = "SENSITIVE_PERSONAL"
    AUTHENTICATION_SECRET = "AUTHENTICATION_SECRET"
    FINANCIAL_SENSITIVE = "FINANCIAL_SENSITIVE"
    MEDICAL_SENSITIVE = "MEDICAL_SENSITIVE"
    TRADING_SENSITIVE = "TRADING_SENSITIVE"
    PROHIBITED_CAPTURE = "PROHIBITED_CAPTURE"


class RedactionMode(str, Enum):
    ALLOW = "ALLOW"
    MASK_FIELDS = "MASK_FIELDS"
    MASK_REGIONS = "MASK_REGIONS"
    BLUR_SENSITIVE = "BLUR_SENSITIVE"
    SUPPRESS_SCREENSHOT = "SUPPRESS_SCREENSHOT"
    METADATA_ONLY = "METADATA_ONLY"


# Severity order — highest risk wins
_MODE_RANK = {
    RedactionMode.ALLOW: 0,
    RedactionMode.MASK_FIELDS: 1,
    RedactionMode.MASK_REGIONS: 2,
    RedactionMode.BLUR_SENSITIVE: 3,
    RedactionMode.METADATA_ONLY: 4,
    RedactionMode.SUPPRESS_SCREENSHOT: 5,
}

_CLASS_DEFAULT_MODE = {
    EvidenceClass.PUBLIC: RedactionMode.ALLOW,
    EvidenceClass.INTERNAL: RedactionMode.MASK_FIELDS,
    EvidenceClass.CONFIDENTIAL: RedactionMode.MASK_REGIONS,
    EvidenceClass.SENSITIVE_PERSONAL: RedactionMode.BLUR_SENSITIVE,
    EvidenceClass.AUTHENTICATION_SECRET: RedactionMode.SUPPRESS_SCREENSHOT,
    EvidenceClass.FINANCIAL_SENSITIVE: RedactionMode.SUPPRESS_SCREENSHOT,
    EvidenceClass.MEDICAL_SENSITIVE: RedactionMode.SUPPRESS_SCREENSHOT,
    EvidenceClass.TRADING_SENSITIVE: RedactionMode.SUPPRESS_SCREENSHOT,
    EvidenceClass.PROHIBITED_CAPTURE: RedactionMode.SUPPRESS_SCREENSHOT,
}

_RETENTION_DAYS = {
    EvidenceClass.PUBLIC: 90,
    EvidenceClass.INTERNAL: 60,
    EvidenceClass.CONFIDENTIAL: 30,
    EvidenceClass.SENSITIVE_PERSONAL: 14,
    EvidenceClass.AUTHENTICATION_SECRET: 1,
    EvidenceClass.FINANCIAL_SENSITIVE: 7,
    EvidenceClass.MEDICAL_SENSITIVE: 7,
    EvidenceClass.TRADING_SENSITIVE: 7,
    EvidenceClass.PROHIBITED_CAPTURE: 0,
}

# Deterministic sensitive selector / attribute patterns
_SENSITIVE_SELECTOR_RE = re.compile(
    r"(?i)(password|passwd|otp|one[-_]?time|ssn|card[-_]?number|cvv|cvc|iban|"
    r"credential|secret|token|api[-_]?key|pin|recovery|passport|national[-_]?id|"
    r"account[-_]?number|routing|swift|medical|mrn)"
)
_SENSITIVE_INPUT_TYPES = frozenset({
    "password", "tel",  # tel often used for OTP
})
_SENSITIVE_AUTOCOMPLETE = frozenset({
    "current-password", "new-password", "one-time-code", "cc-number", "cc-csc",
    "cc-exp", "cc-exp-month", "cc-exp-year", "cc-name",
})
_SENSITIVE_ARIA = re.compile(
    r"(?i)(password|one[- ]?time|verification code|security code|card number|cvv)"
)
_SENSITIVE_ACTION_CLASSES = frozenset({
    "sensitive_input", "financial",
})
_SENSITIVE_ACTIONS = frozenset({
    "enter_credentials", "enter_pii", "enter_payment_info", "trade", "payment",
    "checkout", "purchase", "withdrawal", "money_transfer",
})


@dataclass
class ProtectedRegion:
    source: str  # selector | input_type | aria | autofill | mission | user
    selector: str = ""
    reason: str = ""
    bbox: tuple[int, int, int, int] | None = None  # x,y,w,h if known


@dataclass
class EvidencePolicyDecision:
    classification: EvidenceClass
    redaction_mode: RedactionMode
    screenshot_allowed: bool
    dom_text_allowed: bool
    mask_count: int = 0
    suppression_reason: str = ""
    retention_days: int = 30
    ocr_policy: str = "skip"  # skip | optional_secondary | forbidden
    require_manual_review: bool = False
    protected_regions: list[ProtectedRegion] = field(default_factory=list)
    details: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "classification": self.classification.value,
            "redaction_mode": self.redaction_mode.value,
            "screenshot_allowed": self.screenshot_allowed,
            "dom_text_allowed": self.dom_text_allowed,
            "mask_count": self.mask_count,
            "suppression_reason": self.suppression_reason,
            "retention_days": self.retention_days,
            "ocr_policy": self.ocr_policy,
            "require_manual_review": self.require_manual_review,
            "protected_region_count": len(self.protected_regions),
            "details": dict(self.details),
        }


@dataclass
class EvidenceRecord:
    evidence_id: str
    session_id: str
    action_id: str
    mission_run_id: str
    evidence_type: str
    classification: str
    redaction_mode: str
    mask_count: int
    suppression_reason: str
    content_hash: str
    storage_reference: str
    retention_expiry: float
    created_at: float
    ocr_attempted: str = "skipped"  # skipped | succeeded | failed | forbidden
    metadata: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "evidence_id": self.evidence_id,
            "session_id": self.session_id,
            "action_id": self.action_id,
            "mission_run_id": self.mission_run_id,
            "evidence_type": self.evidence_type,
            "classification": self.classification,
            "redaction_mode": self.redaction_mode,
            "mask_count": self.mask_count,
            "suppression_reason": self.suppression_reason,
            "content_hash": self.content_hash,
            "storage_reference": self.storage_reference,
            "retention_expiry": self.retention_expiry,
            "created_at": self.created_at,
            "ocr_attempted": self.ocr_attempted,
            "metadata": dict(self.metadata),
        }


def _max_mode(*modes: RedactionMode) -> RedactionMode:
    return max(modes, key=lambda m: _MODE_RANK[m])


def classify_evidence(
    *,
    action_type: str = "",
    action_class: str = "",
    selector: str = "",
    field_name: str = "",
    input_type: str = "",
    aria_label: str = "",
    autocomplete: str = "",
    page_elements: list[dict] | None = None,
    mission_sensitivity: str = "general",
    trading_classified: bool = False,
    handoff_state: str = "",
    domain: str = "",
    user_protected_regions: list[dict] | None = None,
) -> EvidencePolicyDecision:
    regions: list[ProtectedRegion] = []
    classification = EvidenceClass.INTERNAL
    mode = RedactionMode.MASK_FIELDS

    # Mission-level
    ms = (mission_sensitivity or "general").lower()
    if ms in ("auth", "authentication", "login"):
        classification = EvidenceClass.AUTHENTICATION_SECRET
        mode = RedactionMode.SUPPRESS_SCREENSHOT
    elif ms in ("financial", "payment", "banking"):
        classification = EvidenceClass.FINANCIAL_SENSITIVE
        mode = RedactionMode.SUPPRESS_SCREENSHOT
    elif ms in ("medical", "health"):
        classification = EvidenceClass.MEDICAL_SENSITIVE
        mode = RedactionMode.SUPPRESS_SCREENSHOT
    elif ms in ("trading", "brokerage"):
        classification = EvidenceClass.TRADING_SENSITIVE
        mode = RedactionMode.SUPPRESS_SCREENSHOT
    elif ms in ("pii", "personal"):
        classification = EvidenceClass.SENSITIVE_PERSONAL
        mode = RedactionMode.BLUR_SENSITIVE
    elif ms in ("public",):
        classification = EvidenceClass.PUBLIC
        mode = RedactionMode.ALLOW

    if trading_classified or action_type in ("trade", "withdrawal", "modify_stop_loss"):
        classification = EvidenceClass.TRADING_SENSITIVE
        mode = _max_mode(mode, RedactionMode.SUPPRESS_SCREENSHOT)

    if action_class in _SENSITIVE_ACTION_CLASSES or action_type in _SENSITIVE_ACTIONS:
        if action_type in ("trade", "payment", "checkout", "purchase", "withdrawal"):
            classification = EvidenceClass.FINANCIAL_SENSITIVE if not trading_classified else EvidenceClass.TRADING_SENSITIVE
            mode = _max_mode(mode, RedactionMode.SUPPRESS_SCREENSHOT)
        else:
            classification = EvidenceClass.AUTHENTICATION_SECRET if "credential" in action_type or "password" in selector.lower() else EvidenceClass.SENSITIVE_PERSONAL
            mode = _max_mode(mode, RedactionMode.SUPPRESS_SCREENSHOT if "password" in selector.lower() or "otp" in selector.lower() else RedactionMode.BLUR_SENSITIVE)

    # Deterministic field detection
    blob = f"{selector} {field_name} {aria_label} {autocomplete}"
    if _SENSITIVE_SELECTOR_RE.search(blob) or _SENSITIVE_ARIA.search(aria_label or ""):
        regions.append(ProtectedRegion(
            source="selector", selector=selector or field_name,
            reason="sensitive_field_pattern",
        ))
        if re.search(r"(?i)password|passwd", blob):
            classification = EvidenceClass.AUTHENTICATION_SECRET
            mode = _max_mode(mode, RedactionMode.SUPPRESS_SCREENSHOT)
        elif re.search(r"(?i)otp|one[-_]?time|verification", blob):
            classification = EvidenceClass.AUTHENTICATION_SECRET
            mode = _max_mode(mode, RedactionMode.SUPPRESS_SCREENSHOT)
        elif re.search(r"(?i)card|cvv|cvc|iban", blob):
            classification = EvidenceClass.FINANCIAL_SENSITIVE
            mode = _max_mode(mode, RedactionMode.SUPPRESS_SCREENSHOT)
        elif re.search(r"(?i)api[-_]?key|token|secret", blob):
            classification = EvidenceClass.AUTHENTICATION_SECRET
            mode = _max_mode(mode, RedactionMode.SUPPRESS_SCREENSHOT)
        else:
            classification = max(
                classification, EvidenceClass.SENSITIVE_PERSONAL,
                key=lambda c: list(EvidenceClass).index(c),
            )
            mode = _max_mode(mode, RedactionMode.MASK_FIELDS)

    if input_type.lower() in _SENSITIVE_INPUT_TYPES:
        regions.append(ProtectedRegion(source="input_type", selector=selector, reason=input_type))
        mode = _max_mode(mode, RedactionMode.MASK_FIELDS if input_type != "password" else RedactionMode.SUPPRESS_SCREENSHOT)
        if input_type == "password":
            classification = EvidenceClass.AUTHENTICATION_SECRET

    if autocomplete.lower() in _SENSITIVE_AUTOCOMPLETE:
        regions.append(ProtectedRegion(source="autofill", selector=selector, reason=autocomplete))
        mode = _max_mode(mode, RedactionMode.MASK_FIELDS)

    for el in page_elements or []:
        el_sel = str(el.get("selector") or el.get("id") or "")
        el_type = str(el.get("type") or el.get("input_type") or "")
        el_name = str(el.get("name") or el.get("label") or el.get("aria") or "")
        el_auto = str(el.get("autocomplete") or "")
        if (
            _SENSITIVE_SELECTOR_RE.search(f"{el_sel} {el_name}")
            or el_type.lower() in _SENSITIVE_INPUT_TYPES
            or el_auto.lower() in _SENSITIVE_AUTOCOMPLETE
        ):
            regions.append(ProtectedRegion(
                source="dom", selector=el_sel or el_name,
                reason="page_element_sensitive",
                bbox=tuple(el["bbox"]) if el.get("bbox") and len(el["bbox"]) == 4 else None,
            ))
            mode = _max_mode(mode, RedactionMode.MASK_REGIONS)

    for ur in user_protected_regions or []:
        regions.append(ProtectedRegion(
            source="user",
            selector=str(ur.get("selector") or ""),
            reason=str(ur.get("reason") or "user_protected"),
            bbox=tuple(ur["bbox"]) if ur.get("bbox") else None,
        ))
        mode = _max_mode(mode, RedactionMode.MASK_REGIONS)

    # High-risk pages default to suppression if deterministic masking insufficient
    if classification in (
        EvidenceClass.AUTHENTICATION_SECRET,
        EvidenceClass.FINANCIAL_SENSITIVE,
        EvidenceClass.MEDICAL_SENSITIVE,
        EvidenceClass.TRADING_SENSITIVE,
        EvidenceClass.PROHIBITED_CAPTURE,
    ):
        mode = _max_mode(mode, RedactionMode.SUPPRESS_SCREENSHOT)

    screenshot_allowed = mode not in (
        RedactionMode.SUPPRESS_SCREENSHOT, RedactionMode.METADATA_ONLY,
    ) or mode == RedactionMode.ALLOW
    if mode in (RedactionMode.SUPPRESS_SCREENSHOT, RedactionMode.METADATA_ONLY):
        screenshot_allowed = False

    # MASK_* still allow screenshot after masking
    if mode in (RedactionMode.MASK_FIELDS, RedactionMode.MASK_REGIONS, RedactionMode.BLUR_SENSITIVE):
        screenshot_allowed = True

    dom_text_allowed = classification in (
        EvidenceClass.PUBLIC, EvidenceClass.INTERNAL, EvidenceClass.CONFIDENTIAL,
    )

    suppression = ""
    if not screenshot_allowed:
        suppression = f"classification={classification.value};mode={mode.value}"

    ocr = "forbidden" if classification in (
        EvidenceClass.AUTHENTICATION_SECRET, EvidenceClass.PROHIBITED_CAPTURE,
    ) else ("optional_secondary" if mode != RedactionMode.ALLOW else "skip")

    return EvidencePolicyDecision(
        classification=classification,
        redaction_mode=mode,
        screenshot_allowed=screenshot_allowed,
        dom_text_allowed=dom_text_allowed,
        mask_count=len(regions),
        suppression_reason=suppression,
        retention_days=_RETENTION_DAYS.get(classification, 30),
        ocr_policy=ocr,
        require_manual_review=classification in (
            EvidenceClass.FINANCIAL_SENSITIVE, EvidenceClass.MEDICAL_SENSITIVE,
            EvidenceClass.TRADING_SENSITIVE,
        ),
        protected_regions=regions,
        details={"domain": domain, "handoff_state": handoff_state},
    )


def apply_deterministic_masks(
    image_bytes: bytes | None,
    regions: list[ProtectedRegion],
    *,
    mode: RedactionMode,
    fail_closed_on_error: bool = True,
) -> tuple[bytes | None, str, str]:
    """Apply masks before persistence.

    Returns (possibly_redacted_bytes, content_hash, outcome).
    Never returns original sensitive bytes when mode requires suppression.
    """
    if mode in (RedactionMode.SUPPRESS_SCREENSHOT, RedactionMode.METADATA_ONLY):
        return None, "", "suppressed"
    if image_bytes is None:
        return None, "", "no_image"
    try:
        # Deterministic masking without image library: replace payload with
        # a redacted marker that includes region count + hash of original size.
        # Real pixel masking would use region bboxes when a decoder is available.
        marker = (
            f"REDACTED_SCREENSHOT mode={mode.value} masks={len(regions)} "
            f"orig_len={len(image_bytes)}"
        ).encode()
        # If we have no regions and mode is ALLOW, keep a non-secret synthetic stub
        if mode == RedactionMode.ALLOW and not regions:
            # Still do not store raw bytes of potentially large captures in tests;
            # store a bounded public stub hash input.
            stub = b"PUBLIC_SCREENSHOT_STUB:" + hashlib.sha256(image_bytes).digest()[:8]
            h = hashlib.sha256(stub).hexdigest()
            return stub, h, "allowed_stub"
        # Always mask — never persist pre-mask raw bytes
        redacted = marker + b":" + hashlib.sha256(image_bytes).digest()[:16]
        h = hashlib.sha256(redacted).hexdigest()
        return redacted, h, "masked"
    except Exception:
        if fail_closed_on_error:
            return None, "", "redaction_failed"
        raise


def redact_dom_snapshot(dom: dict | str | None) -> dict:
    """Bounded DOM evidence — strip secrets and full source."""
    if dom is None:
        return {"nodes": [], "redacted": True}
    if isinstance(dom, str):
        return {
            "text_excerpt": _redact_text_values(dom)[:500],
            "redacted": True,
            "full_source_stored": False,
        }
    out_nodes = []
    for node in (dom.get("nodes") or dom.get("elements") or [])[:100]:
        if not isinstance(node, dict):
            continue
        ntype = str(node.get("type") or node.get("input_type") or "").lower()
        name = str(node.get("name") or node.get("label") or "")
        sel = str(node.get("selector") or "")
        sensitive = bool(
            ntype == "password"
            or _SENSITIVE_SELECTOR_RE.search(f"{sel} {name}")
        )
        out_nodes.append({
            "selector": sel[:120],
            "type": ntype,
            "name": name[:80],
            "value": "***REDACTED***" if sensitive else _redact_text_values(str(node.get("value") or ""))[:80],
            "sensitive": sensitive,
        })
    return {
        "nodes": out_nodes,
        "redacted": True,
        "full_source_stored": False,
        "scripts_stripped": True,
        "tokens_stripped": True,
    }


def _redact_text_values(text: str) -> str:
    if not text:
        return ""
    text = re.sub(
        r"(?i)(password|token|secret|api[_-]?key|authorization)\s*[:=]\s*\S+",
        r"\1=***REDACTED***",
        text,
    )
    text = re.sub(r"\b\d{13,19}\b", "[CARD_REDACTED]", text)
    text = re.sub(r"\b\d{3}-\d{2}-\d{4}\b", "[SSN_REDACTED]", text)
    return text


# Production defaults for non-screenshot evidence
TRACE_DEFAULT_ENABLED = False
VIDEO_DEFAULT_ENABLED = False
STORAGE_STATE_LOG_ENABLED = False
COOKIE_LOG_ENABLED = False


def trace_policy(*, enabled: bool = False, has_retention: bool = False, has_redaction: bool = False) -> dict:
    if not enabled:
        return {"enabled": False, "reason": "disabled_by_default"}
    if not (has_retention and has_redaction):
        return {
            "enabled": False,
            "reason": "traces_require_retention_and_redaction_policy",
            "blocked": True,
        }
    return {
        "enabled": True,
        "redact_headers": True,
        "redact_cookies": True,
        "redact_form_values": True,
        "redact_storage_state": True,
    }


def video_policy(
    *,
    enabled: bool = False,
    classification: EvidenceClass = EvidenceClass.INTERNAL,
    approved: bool = False,
) -> dict:
    if not enabled:
        return {"enabled": False, "reason": "disabled_by_default"}
    if classification in (
        EvidenceClass.AUTHENTICATION_SECRET,
        EvidenceClass.FINANCIAL_SENSITIVE,
        EvidenceClass.MEDICAL_SENSITIVE,
        EvidenceClass.TRADING_SENSITIVE,
        EvidenceClass.PROHIBITED_CAPTURE,
    ) and not approved:
        return {
            "enabled": False,
            "reason": "suppressed_for_sensitive_classification",
            "blocked": True,
        }
    return {"enabled": True, "strict_retention": True, "screenshot_redaction_does_not_cover_video": True}


class EvidenceRedactionPipeline:
    """Capture sequence: classify → mask → persist references only."""

    def __init__(self, storage_dir: str | None = None):
        self.storage_dir = storage_dir
        self._records: dict[str, EvidenceRecord] = {}
        self.ocr_available = False  # do not require OCR for completion

    def capture(
        self,
        *,
        session_id: str,
        action_id: str,
        mission_run_id: str = "",
        evidence_type: str = "screenshot",
        image_bytes: bytes | None = None,
        dom: dict | str | None = None,
        action_type: str = "",
        action_class: str = "",
        selector: str = "",
        field_name: str = "",
        input_type: str = "",
        page_elements: list[dict] | None = None,
        mission_sensitivity: str = "general",
        trading_classified: bool = False,
        force_redaction_failure: bool = False,
    ) -> EvidenceRecord:
        policy = classify_evidence(
            action_type=action_type,
            action_class=action_class,
            selector=selector,
            field_name=field_name,
            input_type=input_type,
            page_elements=page_elements,
            mission_sensitivity=mission_sensitivity,
            trading_classified=trading_classified,
        )

        eid = f"bev-{uuid.uuid4().hex[:14]}"
        now = time.time()
        ocr_status = "skipped"
        content_hash = ""
        storage_ref = ""
        suppression = policy.suppression_reason
        mask_count = policy.mask_count
        mode = policy.redaction_mode

        if evidence_type == "screenshot":
            if force_redaction_failure and policy.classification != EvidenceClass.PUBLIC:
                # Fail closed for sensitive evidence
                return EvidenceRecord(
                    evidence_id=eid,
                    session_id=session_id,
                    action_id=action_id,
                    mission_run_id=mission_run_id,
                    evidence_type=evidence_type,
                    classification=policy.classification.value,
                    redaction_mode=RedactionMode.SUPPRESS_SCREENSHOT.value,
                    mask_count=mask_count,
                    suppression_reason="redaction_failed",
                    content_hash="",
                    storage_reference="",
                    retention_expiry=now,
                    created_at=now,
                    ocr_attempted="skipped",
                    metadata={"status": "failed_closed", "raw_persisted": False},
                )
            # Never persist raw before masking
            raw = image_bytes
            redacted, content_hash, outcome = apply_deterministic_masks(
                raw, policy.protected_regions, mode=mode, fail_closed_on_error=True,
            )
            if outcome == "redaction_failed":
                suppression = "redaction_failed"
                mode = RedactionMode.SUPPRESS_SCREENSHOT
                redacted = None
            if outcome == "suppressed" or redacted is None:
                storage_ref = ""
                suppression = suppression or "suppressed"
            else:
                storage_ref = f"evidence://redacted/{eid}"
                # optional OCR only after mask and never on secrets
                if policy.ocr_policy == "optional_secondary" and self.ocr_available:
                    ocr_status = "succeeded"
                elif policy.ocr_policy == "forbidden":
                    ocr_status = "forbidden"
                else:
                    ocr_status = "skipped"
            # Drop raw reference
            raw = None
        elif evidence_type == "dom":
            safe = redact_dom_snapshot(dom)
            content_hash = hashlib.sha256(
                str(safe).encode()
            ).hexdigest()
            storage_ref = f"evidence://dom/{eid}" if policy.dom_text_allowed else ""
            if not policy.dom_text_allowed:
                suppression = "dom_suppressed_for_classification"
                mode = RedactionMode.METADATA_ONLY
        elif evidence_type in ("trace", "video"):
            storage_ref = ""
            suppression = f"{evidence_type}_disabled_by_default"
            mode = RedactionMode.METADATA_ONLY
            content_hash = ""
        elif evidence_type in ("cookies", "storage_state"):
            storage_ref = ""
            suppression = "secrets_not_logged"
            mode = RedactionMode.METADATA_ONLY
        else:
            storage_ref = f"evidence://meta/{eid}"
            content_hash = hashlib.sha256(f"{session_id}:{action_id}:{evidence_type}".encode()).hexdigest()

        rec = EvidenceRecord(
            evidence_id=eid,
            session_id=session_id,
            action_id=action_id,
            mission_run_id=mission_run_id,
            evidence_type=evidence_type,
            classification=policy.classification.value,
            redaction_mode=mode.value if isinstance(mode, RedactionMode) else str(mode),
            mask_count=mask_count,
            suppression_reason=suppression,
            content_hash=content_hash,
            storage_reference=storage_ref,
            retention_expiry=now + policy.retention_days * 86400,
            created_at=now,
            ocr_attempted=ocr_status,
            metadata={
                "screenshot_allowed": policy.screenshot_allowed,
                "raw_persisted": False,
                "policy": policy.as_dict(),
            },
        )
        self._records[eid] = rec
        return rec

    def get(self, evidence_id: str) -> EvidenceRecord | None:
        return self._records.get(evidence_id)

    def alert_payload(self, rec: EvidenceRecord, *, kind: str = "redaction") -> dict:
        """Privacy-safe alert — no screenshot, no secrets."""
        return {
            "kind": kind,
            "evidence_id": rec.evidence_id,
            "session_id": rec.session_id,
            "action_id": rec.action_id,
            "mission_run_id": rec.mission_run_id,
            "classification": rec.classification,
            "redaction_mode": rec.redaction_mode,
            "suppression_reason": rec.suppression_reason,
            "content_hash": rec.content_hash,
            # explicitly absent
            "screenshot_bytes": None,
            "secret_values": None,
        }


_PIPELINE: EvidenceRedactionPipeline | None = None


def default_evidence_pipeline() -> EvidenceRedactionPipeline:
    global _PIPELINE
    if _PIPELINE is None:
        _PIPELINE = EvidenceRedactionPipeline()
    return _PIPELINE


def reset_evidence_pipeline() -> None:
    global _PIPELINE
    _PIPELINE = None
