"""Travel CRM business event source → Evidence (likely first paying client)."""
from __future__ import annotations
from saathi.evidence.schema import Evidence
_T = "travel"


def handle(event_type: str, payload: dict, *, subject: str = "") -> list[Evidence]:
    p = payload or {}
    subject = subject or p.get("lead_id") or p.get("booking_id") or ""
    if event_type in ("lead.created", "website.lead", "facebook.lead", "instagram.lead"):
        src = p.get("channel") or event_type.split(".")[0]
        return [Evidence(department=_T, project=p.get("project", "surmount_travels"), episode=subject,
                         director="campaign", status="lead", metrics={"channel": src, "value": p.get("value")})]
    if event_type in ("quotation.sent", "quotation.accepted"):
        return [Evidence(department=_T, project=p.get("project", "surmount_travels"), episode=subject,
                         director="sales", status=event_type.split(".")[1],
                         metrics={"amount": p.get("amount"), "channel": p.get("channel", "")})]
    if event_type in ("booking.completed", "booking.confirmed"):
        return [Evidence(department=_T, project=p.get("project", "surmount_travels"), episode=subject,
                         director="sales", status="booked",
                         metrics={"revenue": p.get("revenue"), "channel": p.get("channel", "")})]
    if event_type == "client.feedback":
        return [Evidence(department=_T, project=p.get("project", "surmount_travels"), episode=subject,
                         director="sales", status="feedback", feedback={"rating": p.get("rating")})]
    return []
