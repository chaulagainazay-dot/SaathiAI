"""M54 private-alpha operational readiness.

Adds three read-safe, tenant-scoped operator surfaces on top of the M53
runtime operations service — operational diagnostics, bounded evidence export,
and a dry-run retention policy. Introduces NO new runtime, gateway, RBAC,
identity, or database. All redaction reuses the M53 ``RuntimeOperationsService``
helpers so there is a single redaction authority.

Guarantees:
- Diagnostics never expose secrets, environment, credentials, or database paths.
- Export excludes passwords, hashes, tokens, invite codes, approval secrets,
  connector credentials, private keys, authorization headers, raw arguments,
  raw tool outputs, and internal database paths.
- Retention purge is DRY-RUN ONLY in M54; no operator data is deleted.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
from collections import Counter
from typing import Any

from saathi.platform.context import PlatformContextError, PlatformExecutionContext
from saathi.platform.models import (
    ApprovalStatus,
    PlatformAgentBindingState,
    PlatformExecutionState,
    PlatformPermission,
)
from saathi.platform.operations import RuntimeOperationsService

SCHEMA_VERSION = "m54.readiness.v1"
DEFAULT_RETENTION_DAYS = 90
ENVIRONMENT_CLASSIFICATION = "LOCAL_OR_TEST"
CERTIFICATION_CONFIG_KEY = "m54_last_certification"
RETENTION_HOLD_CONFIG_KEY = "m54_retention_holds"

PRIVATE_ALPHA_LABELS = [
    "PRIVATE_ALPHA",
    "LOCAL_OR_TEST_ENVIRONMENT",
    "NON_PRODUCTION",
    "CONNECTOR_MUTATIONS_DRY_RUN",
    "FINANCIAL_EXECUTION_DISABLED",
    "TRADING_DISABLED",
    "SINGLE_HOST_LOCAL_DATA",
]

# Fields safe to export per record kind. Everything not listed is dropped, so
# new sensitive fields do not leak by default (fail-closed allowlist).
_EXECUTION_EXPORT_FIELDS = (
    "execution_id",
    "state",
    "org_id",
    "workspace_id",
    "project_id",
    "mission_id",
    "agent_id",
    "binding_id",
    "binding_version",
    "run_id",
    "tool_id",
    "capability",
    "authority",
    "created_at",
    "updated_at",
    "deadline_at",
    "cancel_requested",
    "dispatch_started",
    "adapter_invoked",
    "error_code",
    "recovery_count",
    "attention_reasons",
)
_BINDING_EXPORT_FIELDS = (
    "binding_id",
    "agent_id",
    "name",
    "org_id",
    "workspace_id",
    "project_id",
    "mission_id",
    "authority_ceiling",
    "state",
    "version",
    "created_at",
    "updated_at",
)
_APPROVAL_EXPORT_FIELDS = (
    "approval_id",
    "status",
    "tool_id",
    "action",
    "authority",
    "side_effect_class",
    "capability",
    "created_at",
    "expires_at",
    "decided_at",
    "consumed_at",
    "run_id",
)
_AUDIT_EXPORT_FIELDS = (
    "event",
    "ts",
    "outcome",
    "tool_id",
    "authority",
    "execution_id",
    "approval_id",
    "role",
)
# Keys that must never appear in any exported payload, even if a future record
# gains them. Enforced by a final deep scrub.
_FORBIDDEN_EXPORT_KEYS = frozenset(
    {
        "password",
        "password_hash",
        "token",
        "token_hash",
        "session_token",
        "invite_token",
        "invite_code",
        "approval_secret",
        "secret",
        "api_key",
        "authorization",
        "private_key",
        "arguments_json",
        "arguments",
        "result_json",
        "result",
        "db_path",
        "database_path",
        "connector_credential",
        "credential",
    }
)

_EXPORT_KINDS = {
    "execution_summary",
    "lifecycle_timeline",
    "attention",
    "reconciliation_history",
    "binding_metadata",
    "approval_references",
    "audit_events",
    "certification_manifest",
}


class OperationalReadinessService:
    """M54 operator readiness surfaces built on M53 runtime operations."""

    def __init__(self, platform=None):
        self.ops = RuntimeOperationsService(platform)
        self.platform = self.ops.platform
        self.store = self.ops.store

    def context(self, token: str) -> PlatformExecutionContext:
        """Read context — requires RUNTIME_READ (viewer and above)."""
        return self.ops.context(token)

    # ── diagnostics ──────────────────────────────────────────────────────
    def diagnostics(self, ctx: PlatformExecutionContext) -> dict[str, Any]:
        ctx.require_permission(PlatformPermission.RUNTIME_READ)
        records = self.store.list_platform_executions(
            org_id=ctx.org_id, workspace_id=ctx.workspace_id, limit=500
        )
        states = Counter(r.state for r in records)
        attention = self.ops.attention(ctx, limit=200)
        bindings = self.store.list_agent_bindings(
            org_id=ctx.org_id, workspace_id=ctx.workspace_id, limit=500
        )
        binding_states = Counter(b.state for b in bindings)
        reconciliation_total = 0
        for record in records:
            reconciliation_total += len(
                self.store.list_runtime_reconciliations(record.execution_id)
            )
        connectors = self.store.get_config("connectors", {}) or {}
        connector_dry_run = str(connectors.get("mutations", "DRY_RUN_ONLY")).upper() == (
            "DRY_RUN_ONLY"
        ) and not connectors.get("live", False)
        return {
            "schema_version": SCHEMA_VERSION,
            "environment": {
                "classification": ENVIRONMENT_CLASSIFICATION,
                "private_alpha": True,
                "production_authorized": False,
                "labels": list(PRIVATE_ALPHA_LABELS),
            },
            "health": {
                "api": "ok",
                "frontend": "served_separately",
                "database": "available" if self._db_ok() else "unavailable",
                "platform_schema": self.store.get_config(
                    "platform_schema_version", "m53"
                ),
            },
            "runtime": {
                "total_recent_executions": len(records),
                "queue_state": dict(sorted(states.items())),
                "attention_count": len(attention),
                "waiting_approval": states[
                    PlatformExecutionState.WAITING_APPROVAL.value
                ],
                "paused": states[PlatformExecutionState.PAUSED.value],
                "recovering": states[PlatformExecutionState.RECOVERING.value],
                "reconciliation_records": reconciliation_total,
            },
            "bindings": {
                "total": len(bindings),
                "by_state": {
                    "ACTIVE": binding_states[PlatformAgentBindingState.ACTIVE.value],
                    "SUSPENDED": binding_states[
                        PlatformAgentBindingState.SUSPENDED.value
                    ],
                    "REVOKED": binding_states[
                        PlatformAgentBindingState.REVOKED.value
                    ],
                },
            },
            "safety": {
                "connector_mutations": "DRY_RUN_ONLY" if connector_dry_run else "REVIEW",
                "financial_execution": "DISABLED",
                "trading_execution": "DISABLED",
                "trading_guardian": "UNENGAGED_ADVISORY_ONLY",
                "registered_tool_authority": "ExecutionGateway",
                "canonical_runtime": "PlatformAgentRuntime",
            },
            "certification": {
                "latest_certification_at": float(
                    self.store.get_config(CERTIFICATION_CONFIG_KEY, 0) or 0
                ),
            },
        }

    def record_certification(self, ctx: PlatformExecutionContext, *, at: float) -> None:
        """Record a browser-certification timestamp (owner/admin)."""
        ctx.require_permission(PlatformPermission.SETTINGS_WRITE)
        self.store.set_config(
            CERTIFICATION_CONFIG_KEY, float(at), updated_by=ctx.user_id
        )
        self.platform._audit(
            "readiness.certification_recorded", ctx, outcome="RECORDED"
        )

    def _db_ok(self) -> bool:
        try:
            self.store.get_config("connectors", {})
            return True
        except Exception:
            return False

    # ── evidence export ──────────────────────────────────────────────────
    def export(
        self,
        ctx: PlatformExecutionContext,
        *,
        kind: str = "execution_summary",
        fmt: str = "json",
        limit: int = 200,
        execution_id: str = "",
    ) -> dict[str, Any]:
        ctx.require_permission(PlatformPermission.RUNTIME_READ)
        kind = (kind or "execution_summary").strip()
        fmt = (fmt or "json").strip().lower()
        if kind not in _EXPORT_KINDS:
            raise PlatformContextError(
                "EXPORT_KIND_UNSUPPORTED", f"unsupported export kind: {kind}"
            )
        if fmt not in {"json", "csv"}:
            raise PlatformContextError(
                "EXPORT_FORMAT_UNSUPPORTED", f"unsupported export format: {fmt}"
            )
        if kind == "audit_events":
            ctx.require_permission(PlatformPermission.AUDIT_READ)
        limit = max(1, min(int(limit or 200), 1000))
        rows, columns = self._export_rows(ctx, kind, limit, execution_id)
        rows = [self._scrub(row) for row in rows]
        content_hash = self._content_hash(rows)
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "kind": kind,
            "format": fmt,
            "scope": {"org_id": ctx.org_id, "workspace_id": ctx.workspace_id},
            "record_count": len(rows),
            "columns": list(columns),
            "content_hash": content_hash,
            "redaction": "safe_allowlist_v1",
            "production_data": False,
            "environment": ENVIRONMENT_CLASSIFICATION,
        }
        self.platform._audit(
            "readiness.evidence_exported",
            ctx,
            outcome="EXPORTED",
            evidence=content_hash,
            detail={"kind": kind, "format": fmt, "record_count": len(rows)},
        )
        payload: dict[str, Any] = {"manifest": manifest}
        if fmt == "csv":
            payload["csv"] = self._to_csv(columns, rows)
        else:
            payload["records"] = rows
        return payload

    def _export_rows(
        self,
        ctx: PlatformExecutionContext,
        kind: str,
        limit: int,
        execution_id: str,
    ) -> tuple[list[dict[str, Any]], tuple[str, ...]]:
        if kind == "execution_summary":
            records = self.ops.list_executions(ctx, limit=limit)
            return (
                [self._pick(r, _EXECUTION_EXPORT_FIELDS) for r in records],
                _EXECUTION_EXPORT_FIELDS,
            )
        if kind == "attention":
            records = self.ops.attention(ctx, limit=limit)
            return (
                [self._pick(r, _EXECUTION_EXPORT_FIELDS) for r in records],
                _EXECUTION_EXPORT_FIELDS,
            )
        if kind == "lifecycle_timeline":
            if not execution_id:
                raise PlatformContextError(
                    "EXPORT_EXECUTION_REQUIRED",
                    "execution_id is required for a lifecycle_timeline export",
                )
            entries = self.ops.timeline(ctx, execution_id)
            cols = (
                "timestamp",
                "previous_state",
                "new_state",
                "event_type",
                "actor_class",
                "actor_identifier",
                "reason_code",
                "recovery_classification",
            )
            return ([self._pick(e, cols) for e in entries], cols)
        if kind == "reconciliation_history":
            records = self.ops.list_executions(ctx, limit=limit)
            rows: list[dict[str, Any]] = []
            for record in records:
                for item in self.store.list_runtime_reconciliations(
                    record["execution_id"]
                ):
                    rows.append(item.to_public())
            cols = (
                "reconciliation_id",
                "execution_id",
                "action",
                "actor_id",
                "actor_role",
                "outcome",
                "created_at",
            )
            return ([self._pick(r, cols) for r in rows], cols)
        if kind == "binding_metadata":
            bindings = self.store.list_agent_bindings(
                org_id=ctx.org_id, workspace_id=ctx.workspace_id, limit=limit
            )
            return (
                [self._pick(b.to_public(), _BINDING_EXPORT_FIELDS) for b in bindings],
                _BINDING_EXPORT_FIELDS,
            )
        if kind == "approval_references":
            approvals = [
                a
                for a in self.store.list_approvals(org_id=ctx.org_id, limit=limit)
                if a.workspace_id == ctx.workspace_id
            ]
            return (
                [self._pick(a.to_public(), _APPROVAL_EXPORT_FIELDS) for a in approvals],
                _APPROVAL_EXPORT_FIELDS,
            )
        if kind == "audit_events":
            events = self.store.list_audit(org_id=ctx.org_id, limit=limit)
            events = [
                e
                for e in events
                if e.get("workspace_id", ctx.workspace_id) in ("", ctx.workspace_id)
            ]
            return (
                [self._pick(e, _AUDIT_EXPORT_FIELDS) for e in events],
                _AUDIT_EXPORT_FIELDS,
            )
        # certification_manifest
        diag = self.diagnostics(ctx)
        flat = {
            "schema_version": diag["schema_version"],
            "environment": diag["environment"]["classification"],
            "production_authorized": diag["environment"]["production_authorized"],
            "attention_count": diag["runtime"]["attention_count"],
            "waiting_approval": diag["runtime"]["waiting_approval"],
            "paused": diag["runtime"]["paused"],
            "bindings_total": diag["bindings"]["total"],
            "connector_mutations": diag["safety"]["connector_mutations"],
            "financial_execution": diag["safety"]["financial_execution"],
            "trading_execution": diag["safety"]["trading_execution"],
            "canonical_runtime": diag["safety"]["canonical_runtime"],
            "registered_tool_authority": diag["safety"]["registered_tool_authority"],
        }
        cols = tuple(flat.keys())
        return ([flat], cols)

    # ── retention (dry-run only) ─────────────────────────────────────────
    def retention_preview(
        self,
        ctx: PlatformExecutionContext,
        *,
        retention_days: int | None = None,
        now: float | None = None,
        dry_run: bool = True,
    ) -> dict[str, Any]:
        # Retention administration is owner/admin only.
        ctx.require_permission(PlatformPermission.ORG_MANAGE)
        days = int(retention_days if retention_days is not None else DEFAULT_RETENTION_DAYS)
        if days < 1:
            raise PlatformContextError(
                "RETENTION_PERIOD_INVALID", "retention_days must be >= 1"
            )
        now = float(now if now is not None else self.store._now())
        cutoff = now - days * 86400.0
        records = self.store.list_platform_executions(
            org_id=ctx.org_id, workspace_id=ctx.workspace_id, limit=1000
        )
        holds = set(self.store.get_config(RETENTION_HOLD_CONFIG_KEY, []) or [])
        eligible: list[str] = []
        protected_nonterminal = 0
        protected_recent = 0
        protected_held = 0
        for record in records:
            if not record.is_terminal():
                protected_nonterminal += 1
                continue
            if record.execution_id in holds:
                protected_held += 1
                continue
            if record.updated_at > cutoff:
                protected_recent += 1
                continue
            eligible.append(record.execution_id)
        plan = {
            "schema_version": SCHEMA_VERSION,
            "mode": "DRY_RUN",  # M54 never deletes operator data
            "purge_executed": False,
            "retention_days": days,
            "cutoff_at": cutoff,
            "scope": {"org_id": ctx.org_id, "workspace_id": ctx.workspace_id},
            "eligible_for_purge": len(eligible),
            "eligible_execution_ids": eligible[:100],
            "protected": {
                "non_terminal": protected_nonterminal,
                "recent_within_retention": protected_recent,
                "legal_or_operator_hold": protected_held,
            },
            "covered_record_classes": [
                "runtime_executions",
                "runtime_timelines",
                "audit_events",
                "reconciliation_records",
                "approval_metadata",
                "browser_certification_artifacts",
                "exported_evidence",
            ],
            "irreversible": True,
            "confirmation_required": True,
        }
        self.platform._audit(
            "readiness.retention_preview",
            ctx,
            outcome="DRY_RUN",
            detail={
                "retention_days": days,
                "eligible": len(eligible),
                "dry_run": True,
            },
        )
        if not dry_run:
            # M54 policy: purge is dry-run only regardless of caller intent.
            plan["note"] = "PURGE_DISABLED_IN_M54_DRY_RUN_ONLY"
        return plan

    def set_hold(
        self, ctx: PlatformExecutionContext, *, execution_id: str, held: bool
    ) -> dict[str, Any]:
        """Add/remove a legal-or-operator hold marker (owner/admin)."""
        ctx.require_permission(PlatformPermission.ORG_MANAGE)
        record = self.ops._scoped(ctx, execution_id)  # tenant-scoped, fail-closed
        holds = set(self.store.get_config(RETENTION_HOLD_CONFIG_KEY, []) or [])
        if held:
            holds.add(record.execution_id)
        else:
            holds.discard(record.execution_id)
        self.store.set_config(
            RETENTION_HOLD_CONFIG_KEY, sorted(holds), updated_by=ctx.user_id
        )
        self.platform._audit(
            "readiness.retention_hold",
            ctx,
            outcome="HELD" if held else "RELEASED",
            detail={"execution_id": record.execution_id, "held": held},
        )
        return {"execution_id": record.execution_id, "held": held}

    # ── helpers ──────────────────────────────────────────────────────────
    @staticmethod
    def _pick(row: dict[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
        return {key: row.get(key) for key in fields}

    def _scrub(self, row: dict[str, Any]) -> dict[str, Any]:
        """Fail-closed deep scrub — drop any forbidden key, redact secret text."""
        clean: dict[str, Any] = {}
        for key, value in row.items():
            if key.lower() in _FORBIDDEN_EXPORT_KEYS:
                continue
            if isinstance(value, str):
                value = self.ops._safe_text(value, 500)
            elif isinstance(value, dict):
                value = self._scrub(value)
            elif isinstance(value, list):
                value = [
                    self._scrub(v)
                    if isinstance(v, dict)
                    else (self.ops._safe_text(v, 500) if isinstance(v, str) else v)
                    for v in value
                ]
            clean[key] = value
        return clean

    @staticmethod
    def _content_hash(rows: list[dict[str, Any]]) -> str:
        canonical = json.dumps(rows, sort_keys=True, separators=(",", ":"))
        return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _to_csv(columns: tuple[str, ...], rows: list[dict[str, Any]]) -> str:
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=list(columns), extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    key: (
                        json.dumps(value, sort_keys=True)
                        if isinstance(value, (dict, list))
                        else value
                    )
                    for key, value in row.items()
                }
            )
        return buf.getvalue()
