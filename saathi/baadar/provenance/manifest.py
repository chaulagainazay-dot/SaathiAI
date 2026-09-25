"""Baadar asset provenance manifest."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class SourceType(str, Enum):
    ORIGINAL = "original"
    GENERATED = "generated"
    LICENSED = "licensed"
    PUBLIC_DOMAIN = "public_domain"
    USER_PROVIDED = "user_provided"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class AssetManifest:
    asset_id: str
    asset_type: str
    created_at: str
    source_type: SourceType
    source_location: str
    generation_provider: str
    model_name: str
    model_version: str
    prompt_reference: str
    input_asset_references: tuple[str, ...]
    licence: str
    commercial_use_status: str
    attribution_required: bool
    attribution_text: str
    music_rights: str
    font_rights: str
    voice_rights: str
    character_rights: str
    similarity_review_status: str
    human_review_status: str
    approved_by: str
    approved_at: str
    publication_destinations: tuple[str, ...]
    content_hash: str
    permission_confirmed: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["source_type"] = self.source_type.value
        data["input_asset_references"] = list(self.input_asset_references)
        data["publication_destinations"] = list(self.publication_destinations)
        return data
