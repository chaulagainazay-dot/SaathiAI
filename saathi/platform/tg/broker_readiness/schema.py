"""M224–M231 additive SQLite schema for read-only broker readiness.

SIMULATION ONLY. No real secrets. No external account identifiers unless synthetic.
"""
from __future__ import annotations

from saathi.platform.tg.broker_readiness.models import ENGINE_VERSION, SCHEMA_VERSION

READINESS_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS br_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS br_providers (
    provider_id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    is_emulator INTEGER NOT NULL DEFAULT 1,
    connection_state TEXT NOT NULL DEFAULT 'SIMULATED_NOT_CONNECTED',
    capabilities_json TEXT NOT NULL DEFAULT '[]',
    detail_json TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS br_adapter_ops (
    id TEXT PRIMARY KEY,
    operation TEXT NOT NULL,
    authority_class TEXT NOT NULL,
    available_in_m224 INTEGER NOT NULL DEFAULT 0,
    detail_json TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS br_credential_refs (
    id TEXT PRIMARY KEY,
    provider_id TEXT NOT NULL,
    credential_type TEXT NOT NULL DEFAULT 'SIMULATED_METADATA',
    lifecycle_state TEXT NOT NULL DEFAULT 'proposed',
    declared_scopes_json TEXT NOT NULL DEFAULT '[]',
    environment TEXT NOT NULL DEFAULT 'SIMULATION',
    fingerprint TEXT NOT NULL DEFAULT '',
    owner_approval_json TEXT NOT NULL DEFAULT '{}',
    security_approval_json TEXT NOT NULL DEFAULT '{}',
    activated_at REAL,
    expires_at REAL,
    rotation_deadline REAL,
    revoked_at REAL,
    secret_material_present INTEGER NOT NULL DEFAULT 0,
    credential_usable_for_real_connection INTEGER NOT NULL DEFAULT 0,
    audit_refs_json TEXT NOT NULL DEFAULT '[]',
    detail_json TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_br_cred_provider ON br_credential_refs(provider_id);
CREATE INDEX IF NOT EXISTS idx_br_cred_lifecycle ON br_credential_refs(lifecycle_state);

CREATE TABLE IF NOT EXISTS br_lifecycle_events (
    id TEXT PRIMARY KEY,
    credential_id TEXT NOT NULL,
    from_state TEXT NOT NULL,
    to_state TEXT NOT NULL,
    actor TEXT NOT NULL DEFAULT 'system',
    reason TEXT NOT NULL DEFAULT '',
    detail_json TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL,
    FOREIGN KEY (credential_id) REFERENCES br_credential_refs(id)
);
CREATE INDEX IF NOT EXISTS idx_br_life_cred ON br_lifecycle_events(credential_id, created_at);

CREATE TABLE IF NOT EXISTS br_scope_reviews (
    id TEXT PRIMARY KEY,
    credential_id TEXT NOT NULL DEFAULT '',
    requested_json TEXT NOT NULL DEFAULT '[]',
    declared_json TEXT NOT NULL DEFAULT '[]',
    provider_json TEXT NOT NULL DEFAULT '[]',
    approved_json TEXT NOT NULL DEFAULT '[]',
    effective_json TEXT NOT NULL DEFAULT '[]',
    outcome TEXT NOT NULL,
    diff_json TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS br_sessions (
    id TEXT PRIMARY KEY,
    provider_id TEXT NOT NULL,
    credential_id TEXT NOT NULL DEFAULT '',
    state TEXT NOT NULL DEFAULT 'NOT_CONFIGURED',
    rate_limit_json TEXT NOT NULL DEFAULT '{}',
    clock_skew_sec REAL NOT NULL DEFAULT 0,
    heartbeat_at REAL,
    snapshot_fingerprint TEXT NOT NULL DEFAULT '',
    auto_reconnect_allowed INTEGER NOT NULL DEFAULT 0,
    security_failure INTEGER NOT NULL DEFAULT 0,
    detail_json TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS br_session_events (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    event TEXT NOT NULL,
    from_state TEXT NOT NULL DEFAULT '',
    to_state TEXT NOT NULL DEFAULT '',
    detail_json TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL,
    FOREIGN KEY (session_id) REFERENCES br_sessions(id)
);

CREATE TABLE IF NOT EXISTS br_account_snapshots (
    id TEXT PRIMARY KEY,
    provider_id TEXT NOT NULL,
    account_ref TEXT NOT NULL,
    account_type TEXT NOT NULL DEFAULT 'SIMULATED',
    status TEXT NOT NULL DEFAULT 'ACTIVE_SIM',
    base_currency TEXT NOT NULL DEFAULT 'USD',
    permissions_json TEXT NOT NULL DEFAULT '[]',
    balances_json TEXT NOT NULL DEFAULT '[]',
    positions_json TEXT NOT NULL DEFAULT '[]',
    open_order_count INTEGER NOT NULL DEFAULT 0,
    historical_order_count INTEGER NOT NULL DEFAULT 0,
    trade_count INTEGER NOT NULL DEFAULT 0,
    fees_json TEXT NOT NULL DEFAULT '[]',
    liabilities_json TEXT NOT NULL DEFAULT '[]',
    margin_json TEXT NOT NULL DEFAULT '{}',
    history_json TEXT NOT NULL DEFAULT '{}',
    snapshot_ts REAL NOT NULL,
    provider_ts REAL NOT NULL,
    ingestion_ts REAL NOT NULL,
    source_fingerprint TEXT NOT NULL DEFAULT '',
    detail_json TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_br_snap_provider ON br_account_snapshots(provider_id, created_at);

CREATE TABLE IF NOT EXISTS br_reconciliations (
    id TEXT PRIMARY KEY,
    provider_snapshot_id TEXT NOT NULL DEFAULT '',
    local_snapshot_id TEXT NOT NULL DEFAULT '',
    paper_portfolio_ref TEXT NOT NULL DEFAULT '',
    classifications_json TEXT NOT NULL DEFAULT '[]',
    discrepancies_json TEXT NOT NULL DEFAULT '[]',
    recommendations_json TEXT NOT NULL DEFAULT '[]',
    mutated_provider INTEGER NOT NULL DEFAULT 0,
    mutated_portfolio INTEGER NOT NULL DEFAULT 0,
    overall TEXT NOT NULL DEFAULT 'MATCHED',
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS br_policy_evals (
    id TEXT PRIMARY KEY,
    operation TEXT NOT NULL,
    decision TEXT NOT NULL,
    input_json TEXT NOT NULL DEFAULT '{}',
    detail_json TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS br_drills (
    id TEXT PRIMARY KEY,
    scenario TEXT NOT NULL,
    input_json TEXT NOT NULL DEFAULT '{}',
    result_json TEXT NOT NULL DEFAULT '{}',
    fail_closed INTEGER NOT NULL DEFAULT 1,
    recovery_procedure TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS br_security_checks (
    id TEXT PRIMARY KEY,
    threat TEXT NOT NULL,
    result TEXT NOT NULL,
    detail_json TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS br_audit_events (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    actor TEXT NOT NULL DEFAULT 'system',
    subject TEXT NOT NULL DEFAULT '',
    detail_json TEXT NOT NULL DEFAULT '{}',
    evidence_hash TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_br_audit_ts ON br_audit_events(created_at DESC);

CREATE TABLE IF NOT EXISTS br_transport_blocks (
    id TEXT PRIMARY KEY,
    attempted_url TEXT NOT NULL DEFAULT '',
    domain TEXT NOT NULL DEFAULT '',
    result TEXT NOT NULL DEFAULT 'REAL_PROVIDER_TRANSPORT_FORBIDDEN',
    detail_json TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL
);
"""

__all__ = ["READINESS_SCHEMA_SQL", "SCHEMA_VERSION", "ENGINE_VERSION"]
