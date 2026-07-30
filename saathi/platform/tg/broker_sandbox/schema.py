"""M216–M223 additive SQLite schema for broker sandbox architecture.

PAPER ONLY. No live connection artifacts. Credential tables store metadata only.
"""
from __future__ import annotations

from saathi.platform.tg.broker_sandbox.models import ENGINE_VERSION, SCHEMA_VERSION

SANDBOX_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS bs_brokers (
    broker_id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    provider TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    is_emulator INTEGER NOT NULL DEFAULT 0,
    connection_status TEXT NOT NULL DEFAULT 'NOT_CONNECTED',
    lifecycle TEXT NOT NULL DEFAULT 'CATALOGED',
    org_id TEXT NOT NULL DEFAULT 'local',
    workspace_id TEXT NOT NULL DEFAULT 'local',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS bs_capabilities (
    broker_id TEXT PRIMARY KEY,
    supported_assets_json TEXT NOT NULL DEFAULT '[]',
    paper_support INTEGER NOT NULL DEFAULT 1,
    market_orders INTEGER NOT NULL DEFAULT 0,
    limit_orders INTEGER NOT NULL DEFAULT 0,
    stop_orders INTEGER NOT NULL DEFAULT 0,
    margin INTEGER NOT NULL DEFAULT 0,
    options INTEGER NOT NULL DEFAULT 0,
    futures INTEGER NOT NULL DEFAULT 0,
    crypto INTEGER NOT NULL DEFAULT 0,
    equities INTEGER NOT NULL DEFAULT 0,
    rate_limits_json TEXT NOT NULL DEFAULT '{}',
    authentication_method TEXT NOT NULL DEFAULT 'NONE',
    streaming_support INTEGER NOT NULL DEFAULT 0,
    order_events INTEGER NOT NULL DEFAULT 0,
    time_zones_json TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'NOT_CONNECTED',
    detail_json TEXT NOT NULL DEFAULT '{}',
    updated_at REAL NOT NULL,
    FOREIGN KEY (broker_id) REFERENCES bs_brokers(broker_id)
);

CREATE TABLE IF NOT EXISTS bs_credential_refs (
    id TEXT PRIMARY KEY,
    broker_id TEXT NOT NULL,
    provider_metadata_json TEXT NOT NULL DEFAULT '{}',
    permission_scopes_json TEXT NOT NULL DEFAULT '[]',
    rotation_metadata_json TEXT NOT NULL DEFAULT '{}',
    expires_at REAL,
    revoked_at REAL,
    status TEXT NOT NULL DEFAULT 'PLACEHOLDER',
    secret_material_present INTEGER NOT NULL DEFAULT 0,
    usable INTEGER NOT NULL DEFAULT 0,
    approval_chain_json TEXT NOT NULL DEFAULT '[]',
    audit_trail_json TEXT NOT NULL DEFAULT '[]',
    label TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    FOREIGN KEY (broker_id) REFERENCES bs_brokers(broker_id)
);
CREATE INDEX IF NOT EXISTS idx_bs_cred_broker ON bs_credential_refs(broker_id);

CREATE TABLE IF NOT EXISTS bs_trust_pipelines (
    id TEXT PRIMARY KEY,
    broker_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'DRAFT',
    stages_json TEXT NOT NULL DEFAULT '{}',
    paper_graduation_ref TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    created_by TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    completed_at REAL,
    FOREIGN KEY (broker_id) REFERENCES bs_brokers(broker_id)
);

CREATE TABLE IF NOT EXISTS bs_trust_decisions (
    id TEXT PRIMARY KEY,
    pipeline_id TEXT NOT NULL,
    stage TEXT NOT NULL,
    decision TEXT NOT NULL,
    actor TEXT NOT NULL,
    actor_role TEXT NOT NULL DEFAULT '',
    reason TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL,
    FOREIGN KEY (pipeline_id) REFERENCES bs_trust_pipelines(id)
);
CREATE INDEX IF NOT EXISTS idx_bs_trust_dec ON bs_trust_decisions(pipeline_id, stage);

CREATE TABLE IF NOT EXISTS bs_emulator_sessions (
    id TEXT PRIMARY KEY,
    broker_id TEXT NOT NULL DEFAULT 'sandbox.emulator',
    seed INTEGER NOT NULL DEFAULT 42,
    connected INTEGER NOT NULL DEFAULT 1,
    market_open INTEGER NOT NULL DEFAULT 1,
    latency_ms INTEGER NOT NULL DEFAULT 0,
    rate_limit_per_sec INTEGER NOT NULL DEFAULT 100,
    requests_window_json TEXT NOT NULL DEFAULT '[]',
    failure_mode TEXT NOT NULL DEFAULT '',
    clock_skew_sec REAL NOT NULL DEFAULT 0,
    sequence_counter INTEGER NOT NULL DEFAULT 0,
    detail_json TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS bs_emulator_orders (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    client_order_id TEXT NOT NULL DEFAULT '',
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    order_type TEXT NOT NULL,
    quantity TEXT NOT NULL,
    limit_price TEXT,
    stop_price TEXT,
    filled_qty TEXT NOT NULL DEFAULT '0',
    avg_price TEXT NOT NULL DEFAULT '0',
    state TEXT NOT NULL DEFAULT 'PENDING',
    reject_reason TEXT NOT NULL DEFAULT '',
    sequence INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    FOREIGN KEY (session_id) REFERENCES bs_emulator_sessions(id)
);
CREATE INDEX IF NOT EXISTS idx_bs_emu_ord ON bs_emulator_orders(session_id, created_at);

CREATE TABLE IF NOT EXISTS bs_emulator_fills (
    id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    quantity TEXT NOT NULL,
    price TEXT NOT NULL,
    is_duplicate INTEGER NOT NULL DEFAULT 0,
    is_late INTEGER NOT NULL DEFAULT 0,
    sequence INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL,
    FOREIGN KEY (order_id) REFERENCES bs_emulator_orders(id)
);

CREATE TABLE IF NOT EXISTS bs_failure_events (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL DEFAULT '',
    scenario TEXT NOT NULL,
    input_json TEXT NOT NULL DEFAULT '{}',
    result_json TEXT NOT NULL DEFAULT '{}',
    fail_closed INTEGER NOT NULL DEFAULT 1,
    recovered INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS bs_security_checks (
    id TEXT PRIMARY KEY,
    check_name TEXT NOT NULL,
    result TEXT NOT NULL,
    detail_json TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS bs_audit_events (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    actor TEXT NOT NULL DEFAULT 'system',
    subject TEXT NOT NULL DEFAULT '',
    detail_json TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_bs_audit_ts ON bs_audit_events(created_at DESC);

CREATE TABLE IF NOT EXISTS bs_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at REAL NOT NULL
);
"""

__all__ = ["SANDBOX_SCHEMA_SQL", "SCHEMA_VERSION", "ENGINE_VERSION"]
