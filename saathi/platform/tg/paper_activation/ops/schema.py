"""M208 additive schema for operational graduation (extends m200.paper_gov).

PAPER ONLY tables. No live trading artifacts.
"""
from __future__ import annotations

from saathi.platform.tg.paper_activation.ops.models import SCHEMA_VERSION, ENGINE_VERSION

OPS_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS pg_campaign_groups (
    id TEXT PRIMARY KEY,
    org_id TEXT NOT NULL DEFAULT 'local',
    workspace_id TEXT NOT NULL DEFAULT 'local',
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    tags_json TEXT NOT NULL DEFAULT '[]',
    owner TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS pg_campaign_templates (
    id TEXT PRIMARY KEY,
    org_id TEXT NOT NULL DEFAULT 'local',
    name TEXT NOT NULL,
    strategy_slug TEXT NOT NULL DEFAULT '',
    body_json TEXT NOT NULL DEFAULT '{}',
    version INTEGER NOT NULL DEFAULT 1,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS pg_campaign_ext (
    campaign_id TEXT PRIMARY KEY,
    group_id TEXT NOT NULL DEFAULT '',
    template_id TEXT NOT NULL DEFAULT '',
    owner TEXT NOT NULL DEFAULT '',
    tags_json TEXT NOT NULL DEFAULT '[]',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    objectives_text TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    schedule_json TEXT NOT NULL DEFAULT '{}',
    depends_on_json TEXT NOT NULL DEFAULT '[]',
    cloned_from TEXT NOT NULL DEFAULT '',
    archived_at REAL,
    version_history_json TEXT NOT NULL DEFAULT '[]',
    updated_at REAL NOT NULL,
    FOREIGN KEY (campaign_id) REFERENCES pg_campaigns(id)
);

CREATE TABLE IF NOT EXISTS pg_ops_health (
    id TEXT PRIMARY KEY,
    scope TEXT NOT NULL DEFAULT 'system',
    scope_ref TEXT NOT NULL DEFAULT '',
    classification TEXT NOT NULL,
    components_json TEXT NOT NULL DEFAULT '{}',
    detail_json TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pg_ops_health_ts ON pg_ops_health(created_at DESC);

CREATE TABLE IF NOT EXISTS pg_graduation (
    id TEXT PRIMARY KEY,
    campaign_id TEXT NOT NULL,
    strategy_slug TEXT NOT NULL,
    classification TEXT NOT NULL,
    metrics_json TEXT NOT NULL DEFAULT '{}',
    gates_json TEXT NOT NULL DEFAULT '{}',
    reasons_json TEXT NOT NULL DEFAULT '[]',
    live_authorized INTEGER NOT NULL DEFAULT 0,
    auto_promoted_to_live INTEGER NOT NULL DEFAULT 0,
    evaluated_at REAL NOT NULL,
    actor TEXT NOT NULL DEFAULT 'system',
    immutable INTEGER NOT NULL DEFAULT 1,
    fingerprint TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_pg_grad_camp ON pg_graduation(campaign_id, evaluated_at DESC);

CREATE TABLE IF NOT EXISTS pg_ops_recommendations (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'info',
    title TEXT NOT NULL,
    detail_json TEXT NOT NULL DEFAULT '{}',
    campaign_id TEXT NOT NULL DEFAULT '',
    portfolio_id TEXT NOT NULL DEFAULT '',
    strategy_slug TEXT NOT NULL DEFAULT '',
    actionable INTEGER NOT NULL DEFAULT 1,
    auto_applied INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS pg_ops_simulations (
    id TEXT PRIMARY KEY,
    scenario TEXT NOT NULL,
    input_json TEXT NOT NULL DEFAULT '{}',
    result_json TEXT NOT NULL DEFAULT '{}',
    verdict TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS pg_ops_evidence (
    id TEXT PRIMARY KEY,
    campaign_id TEXT NOT NULL DEFAULT '',
    kind TEXT NOT NULL,
    outcome TEXT NOT NULL DEFAULT '',
    bundle_json TEXT NOT NULL DEFAULT '{}',
    fingerprint TEXT NOT NULL DEFAULT '',
    immutable INTEGER NOT NULL DEFAULT 1,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pg_ops_ev ON pg_ops_evidence(campaign_id, created_at DESC);

CREATE TABLE IF NOT EXISTS pg_equity_points (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    portfolio_id TEXT NOT NULL,
    campaign_id TEXT NOT NULL DEFAULT '',
    ts REAL NOT NULL,
    equity TEXT NOT NULL,
    drawdown_pct TEXT NOT NULL DEFAULT '0',
    mark_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_pg_eq ON pg_equity_points(portfolio_id, ts);

CREATE TABLE IF NOT EXISTS pg_ops_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at REAL NOT NULL
);
"""

__all__ = ["OPS_SCHEMA_SQL", "SCHEMA_VERSION", "ENGINE_VERSION"]
