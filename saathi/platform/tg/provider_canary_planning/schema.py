"""Additive SQLite schema for M240–M247 provider canary planning.

No raw credentials. No provider secrets. No authenticated account data.
"""
from __future__ import annotations

from saathi.platform.tg.provider_canary_planning.models import ENGINE_VERSION, SCHEMA_VERSION

PCP_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS pcp_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS pcp_sources (
    id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    retrieval_date TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'official_api_docs',
    relevant_claim TEXT NOT NULL DEFAULT '',
    confidence TEXT NOT NULL DEFAULT 'medium',
    unresolved_ambiguity TEXT NOT NULL DEFAULT '',
    detail_json TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pcp_src_provider ON pcp_sources(provider);

CREATE TABLE IF NOT EXISTS pcp_candidates (
    id TEXT PRIMARY KEY,
    provider TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    classification TEXT NOT NULL,
    preferred INTEGER NOT NULL DEFAULT 0,
    fallback INTEGER NOT NULL DEFAULT 0,
    scores_json TEXT NOT NULL DEFAULT '{}',
    disqualifying_issues_json TEXT NOT NULL DEFAULT '[]',
    unresolved_questions_json TEXT NOT NULL DEFAULT '[]',
    rationale TEXT NOT NULL DEFAULT '',
    evidence_json TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS pcp_rankings (
    id TEXT PRIMARY KEY,
    preferred_provider TEXT NOT NULL,
    fallback_provider TEXT NOT NULL,
    ranking_json TEXT NOT NULL DEFAULT '[]',
    matrix_json TEXT NOT NULL DEFAULT '{}',
    evidence_hash TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS pcp_capabilities (
    id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    endpoint_family TEXT NOT NULL,
    method TEXT NOT NULL DEFAULT 'GET',
    auth_category TEXT NOT NULL,
    required_scope TEXT NOT NULL DEFAULT '',
    pagination TEXT NOT NULL DEFAULT '',
    rate_limit TEXT NOT NULL DEFAULT '',
    timestamp_behaviour TEXT NOT NULL DEFAULT '',
    schema_notes TEXT NOT NULL DEFAULT '',
    retention_limits TEXT NOT NULL DEFAULT '',
    error_behaviour TEXT NOT NULL DEFAULT '',
    canary_relevance TEXT NOT NULL DEFAULT '',
    allowed_or_forbidden TEXT NOT NULL DEFAULT 'FORBIDDEN',
    source_evidence TEXT NOT NULL DEFAULT '',
    detail_json TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pcp_cap_provider ON pcp_capabilities(provider);

CREATE TABLE IF NOT EXISTS pcp_scopes (
    id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    scope_name TEXT NOT NULL,
    kind TEXT NOT NULL,
    rationale TEXT NOT NULL DEFAULT '',
    source_evidence TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS pcp_eligibility (
    id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    result TEXT NOT NULL,
    items_json TEXT NOT NULL DEFAULT '[]',
    legal_review_items_json TEXT NOT NULL DEFAULT '[]',
    unresolved_json TEXT NOT NULL DEFAULT '[]',
    evidence_hash TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS pcp_canary_plans (
    id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    state TEXT NOT NULL,
    architecture_json TEXT NOT NULL DEFAULT '{}',
    network_allowlist_json TEXT NOT NULL DEFAULT '[]',
    endpoint_allowlist_json TEXT NOT NULL DEFAULT '[]',
    budgets_json TEXT NOT NULL DEFAULT '{}',
    evidence_hash TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS pcp_credential_runbooks (
    id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    status TEXT NOT NULL,
    ceremony_json TEXT NOT NULL DEFAULT '{}',
    rotation_json TEXT NOT NULL DEFAULT '{}',
    revocation_json TEXT NOT NULL DEFAULT '{}',
    compromise_json TEXT NOT NULL DEFAULT '{}',
    destruction_json TEXT NOT NULL DEFAULT '{}',
    acknowledgement_template TEXT NOT NULL DEFAULT '',
    evidence_hash TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS pcp_gates (
    id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    pre_activation_json TEXT NOT NULL DEFAULT '[]',
    success_json TEXT NOT NULL DEFAULT '[]',
    abort_json TEXT NOT NULL DEFAULT '[]',
    thresholds_json TEXT NOT NULL DEFAULT '{}',
    evidence_hash TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS pcp_owner_packages (
    id TEXT PRIMARY KEY,
    preferred_provider TEXT NOT NULL,
    fallback_provider TEXT NOT NULL,
    package_json TEXT NOT NULL DEFAULT '{}',
    owner_decision TEXT NOT NULL DEFAULT '',
    owner_signoff_generated_by_automation INTEGER NOT NULL DEFAULT 0,
    decision_options_json TEXT NOT NULL DEFAULT '[]',
    evidence_hash TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS pcp_review_status (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'PLANNING_PACKAGE_READY',
    notes TEXT NOT NULL DEFAULT '',
    actor TEXT NOT NULL DEFAULT 'system',
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS pcp_certifications (
    id TEXT PRIMARY KEY,
    verdict TEXT NOT NULL,
    result_json TEXT NOT NULL DEFAULT '{}',
    evidence_hash TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS pcp_transport_blocks (
    id TEXT PRIMARY KEY,
    attempted_url TEXT NOT NULL,
    domain TEXT NOT NULL DEFAULT '',
    result TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'provider',
    detail_json TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS pcp_audit_events (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    actor TEXT NOT NULL DEFAULT 'system',
    subject TEXT NOT NULL DEFAULT '',
    detail_json TEXT NOT NULL DEFAULT '{}',
    evidence_hash TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pcp_audit_kind ON pcp_audit_events(kind);
CREATE INDEX IF NOT EXISTS idx_pcp_audit_created ON pcp_audit_events(created_at);
"""

__all__ = ["PCP_SCHEMA_SQL", "SCHEMA_VERSION", "ENGINE_VERSION"]
