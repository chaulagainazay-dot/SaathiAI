"""Fail-closed Baadar pre-publication gate.

Approval and audit are injected existing SaathiOS authorities. This package
does not persist approvals, execute publication, or create an audit registry.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Callable, Iterable

from saathi.baadar.provenance import AssetManifest, SourceType

ApprovalChecker = Callable[[str, str], bool]
AuditWriter = Callable[[str, dict[str, Any]], None]


@dataclass(frozen=True)
class GateDecision:
    allowed: bool
    status: str
    reasons: tuple[str, ...]
    duplicate_asset_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class PublicationGate:
    def __init__(self, *, approval_checker: ApprovalChecker, audit_writer: AuditWriter) -> None:
        if approval_checker is None or audit_writer is None:
            raise ValueError("existing approval and audit authorities are required")
        self._approval_checker = approval_checker
        self._audit_writer = audit_writer

    @staticmethod
    def _reasons(asset: AssetManifest) -> list[str]:
        reasons: list[str] = []
        if asset.source_type is SourceType.UNKNOWN:
            reasons.append("source_unknown")
        if not asset.licence.strip():
            reasons.append("licence_missing")
        if asset.commercial_use_status.lower() not in {"allowed", "not_applicable"}:
            reasons.append("commercial_rights_unclear")
        if asset.attribution_required and not asset.attribution_text.strip():
            reasons.append("attribution_missing")
        if asset.music_rights.lower() not in {"cleared", "not_applicable"}:
            reasons.append("music_rights_unresolved")
        if asset.font_rights.lower() not in {"cleared", "not_applicable"}:
            reasons.append("font_rights_unresolved")
        if asset.voice_rights.lower() not in {"cleared", "not_applicable"}:
            reasons.append("voice_rights_unresolved")
        if asset.character_rights.lower() not in {"cleared", "not_applicable"}:
            reasons.append("character_rights_unresolved")
        if asset.source_type is SourceType.USER_PROVIDED and not asset.permission_confirmed:
            reasons.append("user_permission_unconfirmed")
        if asset.similarity_review_status.lower() not in {"passed", "not_applicable", "approved"}:
            reasons.append("similarity_review_incomplete")
        if asset.human_review_status.lower() != "approved":
            reasons.append("human_review_missing")
        if asset.human_review_status.lower() == "approved" and (
            not asset.approved_by.strip() or not asset.approved_at.strip()
        ):
            reasons.append("human_review_evidence_missing")
        if not asset.content_hash.strip():
            reasons.append("content_hash_missing")
        return reasons

    def evaluate(
        self,
        assets: Iterable[AssetManifest],
        *,
        approval_id: str,
        destination: str,
        simulate: bool = True,
    ) -> GateDecision:
        rows = list(assets)
        hashes: dict[str, list[str]] = {}
        reasons: list[str] = []
        for asset in rows:
            reasons.extend(f"{asset.asset_id}:{reason}" for reason in self._reasons(asset))
            hashes.setdefault(asset.content_hash, []).append(asset.asset_id)
            if destination not in asset.publication_destinations:
                reasons.append(f"{asset.asset_id}:destination_not_declared")
        duplicates = tuple(
            asset_id
            for content_hash, asset_ids in hashes.items()
            if content_hash and len(asset_ids) > 1
            for asset_id in asset_ids
        )
        if duplicates:
            reasons.append("duplicate_asset_hash")
        if not rows:
            reasons.append("asset_manifest_empty")
        if not approval_id or not self._approval_checker(approval_id, f"baadar.publish:{destination}"):
            reasons.append("existing_approval_missing_or_invalid")
        if not simulate:
            reasons.append("real_publication_not_authorized")
        decision = GateDecision(
            allowed=not reasons,
            status="APPROVED_SIMULATION" if not reasons else "BLOCKED",
            reasons=tuple(sorted(set(reasons))),
            duplicate_asset_ids=duplicates,
        )
        self._audit_writer(
            "baadar.publication_gate_evaluated",
            {
                "approval_id": approval_id,
                "destination": destination,
                "asset_ids": [asset.asset_id for asset in rows],
                "status": decision.status,
                "reasons": list(decision.reasons),
                "simulation": simulate,
            },
        )
        return decision
