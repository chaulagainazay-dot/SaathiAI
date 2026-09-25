"""Phase 23-25 — narrow NEPSE endpoint stability monitor (read-only).

Not a broad monitoring system: only availability, response classification, expected
endpoint presence, capture success, and schema compatibility for the exact fields V3
uses. On schema/token change → degraded (never guess field replacements). Exposes no
tokens or cookies.
"""
from __future__ import annotations

import time
from enum import Enum


class EndpointHealth(str, Enum):
    AVAILABLE = "AVAILABLE"
    DEGRADED = "DEGRADED"
    SCHEMA_CHANGED = "SCHEMA_CHANGED"
    TOKEN_FLOW_CHANGED = "TOKEN_FLOW_CHANGED"
    UNAVAILABLE = "UNAVAILABLE"


# Fields V3 depends on (Phase 24).
NOTICE_FIELDS = ("noticeHeading", "modifiedDate", "noticeFilePath")
DISCLOSURE_FIELDS = ("newsHeadline", "addedDate", "applicationDocumentDetailsList")
SECURITY_FIELDS = ("symbol", "securityName")


def _has_fields(item: dict, fields) -> list[str]:
    return [f for f in fields if f not in (item or {})]


def validate_schema(cap) -> tuple[bool, dict]:
    """Return (ok, per-endpoint missing-field report)."""
    report = {"notices": "OK", "disclosures": "OK", "security": "OK"}
    ok = True
    notices = getattr(cap, "notices", []) or []
    if notices:
        miss = _has_fields(notices[0], NOTICE_FIELDS)
        if miss:
            report["notices"] = f"MISSING:{','.join(miss)}"; ok = False
    disc = getattr(cap, "disclosures", {}) or {}
    news = disc.get("companyNews", []) if isinstance(disc, dict) else (disc or [])
    if news:
        miss = _has_fields(news[0], DISCLOSURE_FIELDS)
        if miss:
            report["disclosures"] = f"MISSING:{','.join(miss)}"; ok = False
    secs = getattr(cap, "securities", []) or []
    if secs:
        miss = _has_fields(secs[0], SECURITY_FIELDS)
        if miss:
            report["security"] = f"MISSING:{','.join(miss)}"; ok = False
    return ok, report


def health_from_capture(cap) -> dict:
    """Read-only health projection. No tokens, no cookies."""
    status = getattr(cap, "status", "degraded")
    ep = getattr(cap, "endpoint_status", {}) or {}
    if status == "degraded":
        err = getattr(cap, "error_category", "")
        hs = EndpointHealth.UNAVAILABLE if "PLAYWRIGHT_UNAVAILABLE" in err else EndpointHealth.DEGRADED
        return _health_dict(hs, cap, {"notices": "?", "disclosures": "?", "security": "?"})
    if any(v in (401, 403) for v in ep.values()):
        return _health_dict(EndpointHealth.TOKEN_FLOW_CHANGED, cap,
                            {"notices": "AUTH", "disclosures": "AUTH", "security": "AUTH"})
    ok, report = validate_schema(cap)
    hs = EndpointHealth.AVAILABLE if ok else EndpointHealth.SCHEMA_CHANGED
    return _health_dict(hs, cap, report)


def _health_dict(hs: EndpointHealth, cap, report: dict) -> dict:
    return {
        "endpoint": "NEPSE Browser Endpoint",
        "status": hs.value,
        "notices": report.get("notices"),
        "disclosures": report.get("disclosures"),
        "security_index": report.get("security"),
        "schema": "VALID" if hs == EndpointHealth.AVAILABLE else hs.value,
        "notice_count": len(getattr(cap, "notices", []) or []),
        "security_count": len(getattr(cap, "securities", []) or []),
        "last_success": time.time() if hs == EndpointHealth.AVAILABLE else None,
        "read_only": True,
    }
