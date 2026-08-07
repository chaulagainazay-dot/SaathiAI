"""Additive SQLite schema for M232–M239 integration assurance.

No raw credentials. No provider secrets. No external account data.
"""
from __future__ import annotations

from saathi.platform.tg.integration_assurance.models import ENGINE_VERSION, SCHEMA_VERSION

IA_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS ia_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS ia_reproduction_runs (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    source_repo TEXT NOT NULL DEFAULT '',
    branch TEXT NOT NULL DEFAULT '',
    sha TEXT NOT NULL DEFAULT '',
    clone_path_fingerprint TEXT NOT NULL DEFAULT '',
    os_name TEXT NOT NULL DEFAULT '',
    architecture TEXT NOT NULL DEFAULT '',
    python_version TEXT NOT NULL DEFAULT '',
    node_version TEXT NOT NULL DEFAULT '',
    result_json TEXT NOT NULL DEFAULT '{}',
    verdict TEXT NOT NULL DEFAULT '',
    external_network_attempts INTEGER NOT NULL DEFAULT 0,
    hidden_state_findings_json TEXT NOT NULL DEFAULT '[]',
    limitations_json TEXT NOT NULL DEFAULT '[]',
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS ia_source_audit (
    id TEXT PRIMARY KEY,
    path TEXT NOT NULL,
    classification TEXT NOT NULL,
    committed INTEGER NOT NULL DEFAULT 0,
    required INTEGER NOT NULL DEFAULT 0,
    detail_json TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ia_src_path ON ia_source_audit(path);

CREATE TABLE IF NOT EXISTS ia_env_contracts (
    id TEXT PRIMARY KEY,
    contract_json TEXT NOT NULL DEFAULT '{}',
    fingerprint TEXT NOT NULL DEFAULT '',
    preflight_json TEXT NOT NULL DEFAULT '{}',
    preflight_pass INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS ia_dependencies (
    id TEXT PRIMARY KEY,
    package_name TEXT NOT NULL,
    version TEXT NOT NULL DEFAULT '',
    source_registry TEXT NOT NULL DEFAULT '',
    direct INTEGER NOT NULL DEFAULT 1,
    runtime INTEGER NOT NULL DEFAULT 1,
    ecosystem TEXT NOT NULL DEFAULT 'python',
    lockfile_present INTEGER NOT NULL DEFAULT 0,
    integrity_hash TEXT NOT NULL DEFAULT '',
    licence TEXT NOT NULL DEFAULT '',
    purpose TEXT NOT NULL DEFAULT '',
    owning_subsystem TEXT NOT NULL DEFAULT '',
    unpinned INTEGER NOT NULL DEFAULT 0,
    deprecated INTEGER NOT NULL DEFAULT 0,
    risk_rank INTEGER NOT NULL DEFAULT 0,
    detail_json TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ia_dep_name ON ia_dependencies(package_name);

CREATE TABLE IF NOT EXISTS ia_lockfile_checks (
    id TEXT PRIMARY KEY,
    path TEXT NOT NULL,
    present INTEGER NOT NULL DEFAULT 0,
    fingerprint TEXT NOT NULL DEFAULT '',
    consistent INTEGER NOT NULL DEFAULT 1,
    floating_refs_json TEXT NOT NULL DEFAULT '[]',
    detail_json TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS ia_sbom (
    id TEXT PRIMARY KEY,
    format TEXT NOT NULL DEFAULT 'CycloneDX',
    content_json TEXT NOT NULL DEFAULT '{}',
    fingerprint TEXT NOT NULL DEFAULT '',
    component_count INTEGER NOT NULL DEFAULT 0,
    tool_version TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS ia_provenance (
    id TEXT PRIMARY KEY,
    artifact TEXT NOT NULL,
    branch TEXT NOT NULL DEFAULT '',
    sha TEXT NOT NULL DEFAULT '',
    source_tree_fingerprint TEXT NOT NULL DEFAULT '',
    lock_fingerprint TEXT NOT NULL DEFAULT '',
    env_fingerprint TEXT NOT NULL DEFAULT '',
    command TEXT NOT NULL DEFAULT '',
    exit_code INTEGER NOT NULL DEFAULT 0,
    content_hash TEXT NOT NULL DEFAULT '',
    signed INTEGER NOT NULL DEFAULT 0,
    detail_json TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ia_prov_artifact ON ia_provenance(artifact);

CREATE TABLE IF NOT EXISTS ia_threats (
    id TEXT PRIMARY KEY,
    threat TEXT NOT NULL,
    attack_path TEXT NOT NULL DEFAULT '',
    affected_asset TEXT NOT NULL DEFAULT '',
    preventative TEXT NOT NULL DEFAULT '',
    detective TEXT NOT NULL DEFAULT '',
    recovery TEXT NOT NULL DEFAULT '',
    residual_risk TEXT NOT NULL DEFAULT '',
    evidence TEXT NOT NULL DEFAULT '',
    detail_json TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS ia_assurance_gates (
    id TEXT PRIMARY KEY,
    gate TEXT NOT NULL,
    passed INTEGER NOT NULL DEFAULT 0,
    detail_json TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS ia_authorization_plans (
    id TEXT PRIMARY KEY,
    provider TEXT NOT NULL DEFAULT '',
    environment TEXT NOT NULL DEFAULT 'PLANNING',
    aggregate_state TEXT NOT NULL DEFAULT 'PLANNING_ONLY',
    real_connectivity_authorized INTEGER NOT NULL DEFAULT 0,
    detail_json TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS ia_approvals (
    id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL DEFAULT '',
    domain TEXT NOT NULL,
    approver_identity TEXT NOT NULL DEFAULT '',
    role TEXT NOT NULL DEFAULT '',
    scope TEXT NOT NULL DEFAULT '',
    provider TEXT NOT NULL DEFAULT '',
    environment TEXT NOT NULL DEFAULT 'PLANNING',
    issued_at REAL,
    expires_at REAL,
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    acknowledgements_json TEXT NOT NULL DEFAULT '[]',
    revoked INTEGER NOT NULL DEFAULT 0,
    revoked_at REAL,
    superseded INTEGER NOT NULL DEFAULT 0,
    automated INTEGER NOT NULL DEFAULT 0,
    audit_json TEXT NOT NULL DEFAULT '[]',
    detail_json TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ia_appr_plan ON ia_approvals(plan_id);
CREATE INDEX IF NOT EXISTS idx_ia_appr_domain ON ia_approvals(domain);

CREATE TABLE IF NOT EXISTS ia_audit_events (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    actor TEXT NOT NULL DEFAULT 'system',
    subject TEXT NOT NULL DEFAULT '',
    detail_json TEXT NOT NULL DEFAULT '{}',
    evidence_hash TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ia_audit_ts ON ia_audit_events(created_at DESC);

CREATE TABLE IF NOT EXISTS ia_transport_blocks (
    id TEXT PRIMARY KEY,
    attempted_url TEXT NOT NULL DEFAULT '',
    domain TEXT NOT NULL DEFAULT '',
    result TEXT NOT NULL DEFAULT 'REAL_PROVIDER_TRANSPORT_FORBIDDEN',
    category TEXT NOT NULL DEFAULT 'provider',
    detail_json TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS ia_security_checks (
    id TEXT PRIMARY KEY,
    check_name TEXT NOT NULL,
    result TEXT NOT NULL,
    detail_json TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS ia_certification (
    id TEXT PRIMARY KEY,
    verdict TEXT NOT NULL,
    result_json TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL
);
"""

__all__ = ["IA_SCHEMA_SQL", "SCHEMA_VERSION", "ENGINE_VERSION"]
