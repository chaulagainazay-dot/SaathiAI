"""M13 publishing — provider-neutral, approval-gated, receipt-verified.

No platform accounts are configured in this environment, so real publishing is
never attempted: `publish` refuses without (a) an approved final artifact and
(b) an explicit approval, and otherwise performs a DRY RUN that records a
receipt with status='dry_run' and NO fabricated URL/content-id. Idempotency
keys prevent duplicate publishes. A real receipt is never invented.
"""
from __future__ import annotations

from dataclasses import dataclass


class NotApproved(Exception):
    pass


class NoPublishableArtifact(Exception):
    pass


SUPPORTED = {"youtube", "facebook", "instagram", "linkedin", "reddit", "tiktok",
             "website", "file_export"}


@dataclass
class PublishResult:
    ok: bool
    status: str          # dry_run | published | failed | duplicate
    platform: str
    receipt_id: str = ""
    url: str = ""
    detail: str = ""


def _final_artifact(store, project_id: str):
    for a in store.list_artifacts(project_id):
        if a["artifact_type"] in ("final_video", "blog_post", "export_package") \
                and a["status"] in ("ready", "approved"):
            return a
    return None


def publish(store, project_id: str, *, platform: str, owner: str,
            approved: bool, live: bool = False,
            idempotency_key: str = "") -> PublishResult:
    """Publish an approved artifact. Enforces ownership + approval + a verified
    artifact. `live=True` would attempt a real upload — but with no configured
    connector it is refused honestly rather than faked."""
    if platform not in SUPPORTED:
        return PublishResult(False, "failed", platform, detail=f"unsupported platform")
    if not store.owns(project_id, owner):
        raise PermissionError("project ownership check failed")
    if not approved:
        raise NotApproved("publish requires explicit approval of the final artifact")

    art = _final_artifact(store, project_id)
    if not art or not art.get("checksum"):
        raise NoPublishableArtifact("no verified final artifact to publish")

    key = idempotency_key or f"{project_id}:{platform}:{art['checksum']}"
    existing = store.receipt_by_idempotency(key)
    if existing:
        return PublishResult(True, "duplicate", platform,
                             receipt_id=existing["id"], url=existing["url"],
                             detail="idempotency: already published")

    if live:
        # No real connector/credentials in this environment. We do NOT fabricate
        # a receipt — publishing is refused honestly.
        rid = store.add_receipt(project_id, platform=platform, status="failed",
                                idempotency_key=key,
                                detail="live publish unavailable: no configured "
                                       f"{platform} connector/credentials")
        return PublishResult(False, "failed", platform, receipt_id=rid,
                             detail="live publish not configured — nothing was sent")

    # DRY RUN: validates the full path without an external call. Records a
    # receipt marked dry_run with NO fabricated URL or platform content id.
    rid = store.add_receipt(project_id, platform=platform, status="dry_run",
                            idempotency_key=key,
                            detail="dry run: artifact verified, approval present, "
                                   "no external upload performed")
    return PublishResult(True, "dry_run", platform, receipt_id=rid,
                         detail="dry run ok — approval + verified artifact present")
