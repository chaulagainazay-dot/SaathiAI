"""AI Studio business event source → Evidence (delegates to the studio adapter)."""
from __future__ import annotations
from saathi.evidence.schema import Evidence


def handle(event_type: str, payload: dict, *, subject: str = "") -> list[Evidence]:
    from saathi.evidence.adapters import from_studio_production
    p = dict(payload or {})
    p.setdefault("episode", subject)
    if event_type == "episode.produced":
        return from_studio_production(p)
    # analytics events (youtube.analytics, CTR.updated, retention.updated, subscriber.gained)
    if event_type.endswith(".analytics") or "." in event_type:
        return [Evidence(department="ai_studio", project=p.get("project", "mr_yeti"), episode=subject,
                         director="analytics", status=event_type,
                         metrics={k: v for k, v in p.items() if k not in ("episode",)})]
    return []
