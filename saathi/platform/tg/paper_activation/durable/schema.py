"""M200 — Durable paper activation schema (versioned SQLite).

Schema version: m200.paper_gov.v1
PAPER ONLY. No live trading tables.
"""
from __future__ import annotations

SCHEMA_VERSION = "m200.paper_gov.v1"
ENGINE_VERSION = "m200.durable.engine.v1"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS pg_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS pg_portfolios (
    id TEXT PRIMARY KEY,
    org_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    name TEXT NOT NULL,
    status TEXT NOT NULL,
    base_currency TEXT NOT NULL DEFAULT 'USD',
    starting_cash TEXT NOT NULL,
    cash TEXT NOT NULL,
    reserved_cash TEXT NOT NULL DEFAULT '0',
    realized_pnl TEXT NOT NULL DEFAULT '0',
    fees_paid TEXT NOT NULL DEFAULT '0',
    slippage_paid TEXT NOT NULL DEFAULT '0',
    peak_equity TEXT NOT NULL,
    day_start_equity TEXT NOT NULL,
    week_start_equity TEXT NOT NULL,
    month_start_equity TEXT NOT NULL,
    halt_reason TEXT NOT NULL DEFAULT 'NONE',
    halt_detail TEXT NOT NULL DEFAULT '',
    risk_limits_json TEXT NOT NULL DEFAULT '{}',
    marks_json TEXT NOT NULL DEFAULT '{}',
    version INTEGER NOT NULL DEFAULT 1,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pg_port_org ON pg_portfolios(org_id, workspace_id);

CREATE TABLE IF NOT EXISTS pg_positions (
    portfolio_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    quantity TEXT NOT NULL DEFAULT '0',
    avg_price TEXT NOT NULL DEFAULT '0',
    realized_pnl TEXT NOT NULL DEFAULT '0',
    fees TEXT NOT NULL DEFAULT '0',
    strategy_slug TEXT NOT NULL DEFAULT '',
    lots_json TEXT NOT NULL DEFAULT '[]',
    history_json TEXT NOT NULL DEFAULT '[]',
    version INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (portfolio_id, symbol),
    FOREIGN KEY (portfolio_id) REFERENCES pg_portfolios(id)
);

CREATE TABLE IF NOT EXISTS pg_activations (
    id TEXT PRIMARY KEY,
    org_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    strategy_slug TEXT NOT NULL,
    strategy_version TEXT NOT NULL DEFAULT '1.0.0',
    state TEXT NOT NULL,
    qualification_verdict TEXT NOT NULL DEFAULT '',
    qualification_fingerprint TEXT NOT NULL DEFAULT '',
    dataset_id TEXT NOT NULL DEFAULT '',
    dataset_fingerprint TEXT NOT NULL DEFAULT '',
    approval_id TEXT NOT NULL DEFAULT '',
    portfolio_id TEXT NOT NULL DEFAULT '',
    activated_at REAL,
    halted_at REAL,
    halt_reason TEXT NOT NULL DEFAULT '',
    history_json TEXT NOT NULL DEFAULT '[]',
    version INTEGER NOT NULL DEFAULT 1,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    UNIQUE (org_id, workspace_id, strategy_slug)
);

CREATE TABLE IF NOT EXISTS pg_approvals (
    id TEXT PRIMARY KEY,
    org_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    strategy_slug TEXT NOT NULL,
    strategy_version TEXT NOT NULL DEFAULT '1.0.0',
    dataset_id TEXT NOT NULL DEFAULT '',
    dataset_fingerprint TEXT NOT NULL DEFAULT '',
    qualification_fingerprint TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL,
    reason TEXT NOT NULL,
    operator_id TEXT NOT NULL DEFAULT '',
    operator_identity TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL,
    decided_at REAL,
    expires_at REAL,
    single_use INTEGER NOT NULL DEFAULT 1,
    consumed_at REAL,
    notes TEXT NOT NULL DEFAULT '',
    evidence_json TEXT NOT NULL DEFAULT '{}',
    rejection_reason TEXT NOT NULL DEFAULT '',
    version INTEGER NOT NULL DEFAULT 1,
    immutable INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_pg_appr_status ON pg_approvals(org_id, status);

CREATE TABLE IF NOT EXISTS pg_orders (
    id TEXT PRIMARY KEY,
    portfolio_id TEXT NOT NULL,
    strategy_slug TEXT NOT NULL DEFAULT '',
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    order_type TEXT NOT NULL,
    tif TEXT NOT NULL DEFAULT 'DAY',
    quantity TEXT NOT NULL,
    filled_qty TEXT NOT NULL DEFAULT '0',
    limit_price TEXT,
    stop_price TEXT,
    status TEXT NOT NULL,
    reject_reason TEXT NOT NULL DEFAULT '',
    avg_fill_price TEXT NOT NULL DEFAULT '0',
    fees TEXT NOT NULL DEFAULT '0',
    slippage TEXT NOT NULL DEFAULT '0',
    fills_json TEXT NOT NULL DEFAULT '[]',
    notes TEXT NOT NULL DEFAULT '',
    correlation_id TEXT NOT NULL DEFAULT '',
    idempotency_key TEXT NOT NULL DEFAULT '',
    sim_inputs_json TEXT NOT NULL DEFAULT '{}',
    version INTEGER NOT NULL DEFAULT 1,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    FOREIGN KEY (portfolio_id) REFERENCES pg_portfolios(id)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_pg_ord_idem
    ON pg_orders(portfolio_id, idempotency_key) WHERE idempotency_key != '';
CREATE INDEX IF NOT EXISTS idx_pg_ord_status ON pg_orders(portfolio_id, status);

CREATE TABLE IF NOT EXISTS pg_order_queue (
    order_id TEXT PRIMARY KEY,
    portfolio_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING',
    attempts INTEGER NOT NULL DEFAULT 0,
    next_attempt_at REAL NOT NULL DEFAULT 0,
    lease_owner TEXT NOT NULL DEFAULT '',
    lease_until REAL NOT NULL DEFAULT 0,
    poison INTEGER NOT NULL DEFAULT 0,
    last_error TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    FOREIGN KEY (order_id) REFERENCES pg_orders(id)
);

CREATE TABLE IF NOT EXISTS pg_journal (
    id TEXT PRIMARY KEY,
    portfolio_id TEXT NOT NULL,
    strategy_slug TEXT NOT NULL DEFAULT '',
    order_id TEXT NOT NULL DEFAULT '',
    symbol TEXT NOT NULL DEFAULT '',
    side TEXT NOT NULL DEFAULT '',
    reason TEXT NOT NULL DEFAULT '',
    payload_json TEXT NOT NULL DEFAULT '{}',
    org_id TEXT NOT NULL DEFAULT '',
    workspace_id TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL,
    immutable INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_pg_jnl_port ON pg_journal(portfolio_id, created_at DESC);

CREATE TABLE IF NOT EXISTS pg_events (
    event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    aggregate_type TEXT NOT NULL,
    aggregate_id TEXT NOT NULL,
    expected_version INTEGER,
    resulting_version INTEGER,
    ts REAL NOT NULL,
    actor_type TEXT NOT NULL DEFAULT 'system',
    actor_id TEXT NOT NULL DEFAULT '',
    correlation_id TEXT NOT NULL DEFAULT '',
    causation_id TEXT NOT NULL DEFAULT '',
    idempotency_key TEXT NOT NULL DEFAULT '',
    payload_json TEXT NOT NULL,
    payload_fingerprint TEXT NOT NULL,
    previous_event_id TEXT NOT NULL DEFAULT '',
    audit_json TEXT NOT NULL DEFAULT '{}',
    seq INTEGER NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_pg_evt_idem
    ON pg_events(idempotency_key) WHERE idempotency_key != '';
CREATE INDEX IF NOT EXISTS idx_pg_evt_agg ON pg_events(aggregate_type, aggregate_id, seq);
CREATE INDEX IF NOT EXISTS idx_pg_evt_ts ON pg_events(ts);

CREATE TABLE IF NOT EXISTS pg_idempotency (
    scope TEXT NOT NULL,
    key TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    result_json TEXT NOT NULL,
    created_at REAL NOT NULL,
    PRIMARY KEY (scope, key)
);

CREATE TABLE IF NOT EXISTS pg_processed_effects (
    effect_key TEXT PRIMARY KEY,
    order_id TEXT NOT NULL DEFAULT '',
    fill_ref TEXT NOT NULL DEFAULT '',
    ts REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS pg_kill_switch (
    id TEXT PRIMARY KEY,
    scope TEXT NOT NULL,
    scope_ref TEXT NOT NULL DEFAULT '',
    active INTEGER NOT NULL DEFAULT 0,
    reason TEXT NOT NULL DEFAULT '',
    activated_by TEXT NOT NULL DEFAULT '',
    org_id TEXT NOT NULL DEFAULT '',
    workspace_id TEXT NOT NULL DEFAULT '',
    version INTEGER NOT NULL DEFAULT 1,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS pg_reconciliation (
    id TEXT PRIMARY KEY,
    portfolio_id TEXT NOT NULL,
    verdict TEXT NOT NULL,
    findings_json TEXT NOT NULL DEFAULT '[]',
    warnings_json TEXT NOT NULL DEFAULT '[]',
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS pg_snapshots (
    id TEXT PRIMARY KEY,
    portfolio_id TEXT NOT NULL,
    seq_upto INTEGER NOT NULL,
    state_json TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pg_snap ON pg_snapshots(portfolio_id, created_at DESC);

CREATE TABLE IF NOT EXISTS pg_campaigns (
    id TEXT PRIMARY KEY,
    org_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    portfolio_id TEXT NOT NULL DEFAULT '',
    strategy_slug TEXT NOT NULL,
    strategy_version TEXT NOT NULL DEFAULT '1.0.0',
    dataset_fingerprint TEXT NOT NULL DEFAULT '',
    qualification_fingerprint TEXT NOT NULL DEFAULT '',
    approval_id TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'DRAFT',
    start_date REAL,
    planned_end_date REAL,
    actual_end_date REAL,
    initial_cash TEXT NOT NULL DEFAULT '100000',
    allowed_symbols_json TEXT NOT NULL DEFAULT '[]',
    risk_policy_version TEXT NOT NULL DEFAULT '1.0.0',
    cost_model_version TEXT NOT NULL DEFAULT '1.0.0',
    objectives_json TEXT NOT NULL DEFAULT '{}',
    evaluation_criteria_json TEXT NOT NULL DEFAULT '{}',
    min_duration_sec REAL NOT NULL DEFAULT 0,
    min_trade_count INTEGER NOT NULL DEFAULT 0,
    operator_notes TEXT NOT NULL DEFAULT '',
    evidence_json TEXT NOT NULL DEFAULT '{}',
    version INTEGER NOT NULL DEFAULT 1,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pg_camp ON pg_campaigns(org_id, status);

CREATE TABLE IF NOT EXISTS pg_leases (
    lease_key TEXT PRIMARY KEY,
    owner TEXT NOT NULL,
    until REAL NOT NULL,
    meta_json TEXT NOT NULL DEFAULT '{}',
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS pg_scheduler (
    job_id TEXT PRIMARY KEY,
    enabled INTEGER NOT NULL DEFAULT 0,
    last_run_at REAL NOT NULL DEFAULT 0,
    last_status TEXT NOT NULL DEFAULT '',
    last_error TEXT NOT NULL DEFAULT '',
    interval_sec REAL NOT NULL DEFAULT 86400,
    meta_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS pg_incidents (
    id TEXT PRIMARY KEY,
    severity TEXT NOT NULL DEFAULT 'info',
    kind TEXT NOT NULL,
    message TEXT NOT NULL,
    portfolio_id TEXT NOT NULL DEFAULT '',
    campaign_id TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'OPEN',
    ack_by TEXT NOT NULL DEFAULT '',
    resolved_by TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS pg_trade_ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    portfolio_id TEXT NOT NULL,
    entry_json TEXT NOT NULL,
    ts REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS pg_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event TEXT NOT NULL,
    detail_json TEXT NOT NULL DEFAULT '{}',
    ts REAL NOT NULL
);
"""
