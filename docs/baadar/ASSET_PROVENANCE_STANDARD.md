# Baadar Asset Provenance Standard

Status: fail-closed contract integrated at `saathi.baadar`.

Each asset manifest records:

`asset_id`, `asset_type`, `created_at`, `source_type`, `source_location`,
`generation_provider`, `model_name`, `model_version`, `prompt_reference`,
`input_asset_references`, `licence`, `commercial_use_status`,
`attribution_required`, `attribution_text`, `music_rights`, `font_rights`,
`voice_rights`, `character_rights`, `similarity_review_status`,
`human_review_status`, `approved_by`, `approved_at`,
`publication_destinations`, and `content_hash`.

Allowed source types are `original`, `generated`, `licensed`,
`public_domain`, `user_provided`, and `unknown`. Source `unknown` always
blocks. A user-provided source must carry explicit permission confirmation.

The manifest is a governance record, not a legal opinion. C2PA can complement
this record with signed content credentials, but C2PA provenance does not
itself establish copyright ownership or commercial-use permission. The
integration therefore adapts the [C2PA specification](https://spec.c2pa.org/)
as a provenance concept and retains explicit rights fields and human review.
