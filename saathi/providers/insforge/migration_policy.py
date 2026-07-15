"""Fail-closed migration parse, allowlist, risk, and SQL generation (M18.4)."""
from __future__ import annotations

import re
from typing import Any

from saathi.providers.insforge.migration_types import (
    ALLOWED_COL_TYPES,
    ALLOWED_OPS,
    MAX_BODY_CHARS,
    MAX_COLUMNS,
    MAX_INDEX_COLS,
    MAX_OPS,
    ColumnSpec,
    MigrationOp,
    MigrationPlan,
    MigrationRequest,
    MigrationRisk,
    RISK_TO_APPROVAL,
    valid_ident,
)

# Deny patterns if raw SQL body ever provided
_DENIED_SQL = re.compile(
    r"\b(DROP|TRUNCATE|DELETE|UPDATE|INSERT|GRANT|REVOKE|ALTER\s+ROLE|"
    r"CREATE\s+EXTENSION|CREATE\s+DATABASE|DISABLE\s+ROW\s+LEVEL|"
    r"SET\s+ROLE|COPY\s+|EXECUTE|CALL\s+|DO\s+\$\$|pg_read_file|"
    r"lo_import|dblink|SUPERUSER)\b",
    re.I,
)

_DENIED_TABLE_PREFIXES = (
    "auth.", "pg_", "information_schema", "trading", "guardian",
    "exchange", "broker",
)


def parse_operations(raw: Any) -> tuple[list[MigrationOp], str]:
    """Parse structured ops list. Returns (ops, error)."""
    if raw is None:
        return [], "operations_required"
    if isinstance(raw, dict) and "operations" in raw:
        raw = raw["operations"]
    if not isinstance(raw, list):
        return [], "operations_must_be_list"
    if len(raw) == 0:
        return [], "operations_empty"
    if len(raw) > MAX_OPS:
        return [], f"too_many_operations:{len(raw)}>{MAX_OPS}"

    ops: list[MigrationOp] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            return [], f"op_{i}_not_object"
        op_name = str(item.get("op") or item.get("type") or "").lower().strip()
        if op_name not in ALLOWED_OPS:
            return [], f"op_denied:{op_name or 'missing'}"
        table = str(item.get("table") or "").lower().strip()
        if not valid_ident(table):
            return [], f"invalid_table:{table[:40]}"
        if any(table.startswith(p) or p.rstrip(".") == table for p in _DENIED_TABLE_PREFIXES):
            return [], f"table_namespace_denied:{table}"

        if op_name == "create_table":
            cols_raw = item.get("columns") or []
            if not isinstance(cols_raw, list) or not cols_raw:
                return [], "create_table_requires_columns"
            if len(cols_raw) > MAX_COLUMNS:
                return [], "too_many_columns"
            cols: list[ColumnSpec] = []
            for c in cols_raw:
                if not isinstance(c, dict):
                    return [], "column_not_object"
                cn = str(c.get("name") or "").lower()
                ct = str(c.get("type") or "text").lower().strip()
                if not valid_ident(cn):
                    return [], f"invalid_column:{cn[:40]}"
                if ct not in ALLOWED_COL_TYPES:
                    return [], f"column_type_denied:{ct}"
                cols.append(ColumnSpec(
                    name=cn, type=ct,
                    nullable=bool(c.get("nullable", True)),
                    primary_key=bool(c.get("primary_key", False)),
                ))
            ops.append(MigrationOp(op=op_name, table=table, columns=cols))

        elif op_name == "add_column":
            c = item.get("column") or {}
            if not isinstance(c, dict):
                return [], "add_column_requires_column_object"
            cn = str(c.get("name") or "").lower()
            ct = str(c.get("type") or "text").lower().strip()
            if not valid_ident(cn):
                return [], f"invalid_column:{cn[:40]}"
            if ct not in ALLOWED_COL_TYPES:
                return [], f"column_type_denied:{ct}"
            # Pilot: nullable only (non-null with default is elevated/denied)
            nullable = bool(c.get("nullable", True))
            if not nullable:
                return [], "add_column_must_be_nullable_in_pilot"
            ops.append(MigrationOp(
                op=op_name, table=table,
                column=ColumnSpec(name=cn, type=ct, nullable=True),
            ))

        elif op_name == "create_index":
            iname = str(item.get("index_name") or item.get("name") or "").lower()
            icols = item.get("index_columns") or item.get("columns") or []
            if not valid_ident(iname):
                return [], f"invalid_index_name:{iname[:40]}"
            if not isinstance(icols, list) or not icols:
                return [], "index_requires_columns"
            if len(icols) > MAX_INDEX_COLS:
                return [], "too_many_index_columns"
            names = []
            for x in icols:
                n = str(x).lower()
                if not valid_ident(n):
                    return [], f"invalid_index_column:{n[:40]}"
                names.append(n)
            unique = bool(item.get("unique", False))
            ops.append(MigrationOp(
                op=op_name, table=table, index_name=iname,
                index_columns=names, unique=unique,
            ))
    return ops, ""


def reject_raw_sql(sql: str | None) -> str:
    """If free-form SQL is provided, only accept empty; deny any SQL console use."""
    if sql is None or str(sql).strip() == "":
        return ""
    s = str(sql).strip()
    if len(s) > MAX_BODY_CHARS:
        return "sql_body_too_large"
    if _DENIED_SQL.search(s):
        return "sql_keyword_denied"
    # Pilot: free SQL not accepted even if looks safe — use structured ops
    return "raw_sql_not_supported_use_structured_operations"


def classify_risk(ops: list[MigrationOp]) -> MigrationRisk:
    risk = MigrationRisk.LOW
    for o in ops:
        if o.op == "create_index" and o.unique:
            risk = MigrationRisk.ELEVATED
        if o.table in ("users", "accounts", "sessions", "credentials"):
            risk = MigrationRisk.ELEVATED
        if o.op == "create_table" and any(c.primary_key for c in o.columns):
            pass  # still low
    return risk


def default_rollback_ops(ops: list[MigrationOp]) -> list[dict]:
    """Generate reverse ops guidance (not auto-executed)."""
    rb: list[dict] = []
    for o in reversed(ops):
        if o.op == "create_table":
            rb.append({
                "op": "drop_table",
                "table": o.table,
                "warning": "data_loss_if_populated",
                "requires_separate_approval": True,
                "pilot_executable": False,
            })
        elif o.op == "add_column" and o.column:
            rb.append({
                "op": "drop_column",
                "table": o.table,
                "column": o.column.name,
                "warning": "data_loss_for_column",
                "requires_separate_approval": True,
                "pilot_executable": False,
            })
        elif o.op == "create_index":
            rb.append({
                "op": "drop_index",
                "index_name": o.index_name,
                "requires_separate_approval": True,
                "pilot_executable": False,
            })
    return rb


def default_postconditions(ops: list[MigrationOp]) -> dict:
    tables = sorted({o.table for o in ops})
    indexes = [o.index_name for o in ops if o.op == "create_index"]
    columns = []
    for o in ops:
        if o.op == "add_column" and o.column:
            columns.append(f"{o.table}.{o.column.name}")
        if o.op == "create_table":
            for c in o.columns:
                columns.append(f"{o.table}.{c.name}")
    return {
        "tables_must_exist": tables,
        "columns_must_exist": columns,
        "indexes_must_exist": indexes,
    }


def plan_migration(req: MigrationRequest) -> MigrationPlan:
    """Validate + normalize + risk-classify. Fail closed."""
    if req.provider != "insforge":
        return MigrationPlan(
            ok=False, fingerprint="", risk=MigrationRisk.PROHIBITED,
            approval_level="L4", operations=[], affected_objects=[],
            reversible=False, rollback_ops=[],
            denied_reason="provider_must_be_insforge",
        )
    if req.environment not in ("dev", "staging", "test", "pilot"):
        return MigrationPlan(
            ok=False, fingerprint="", risk=MigrationRisk.PROHIBITED,
            approval_level="L4", operations=[], affected_objects=[],
            reversible=False, rollback_ops=[],
            denied_reason=f"environment_denied:{req.environment}",
        )
    if req.irreversible:
        return MigrationPlan(
            ok=False, fingerprint="", risk=MigrationRisk.PROHIBITED,
            approval_level="L4", operations=[], affected_objects=[],
            reversible=False, rollback_ops=[],
            denied_reason="irreversible_not_allowed_in_pilot",
        )

    ops = req.operations
    if not ops:
        return MigrationPlan(
            ok=False, fingerprint="", risk=MigrationRisk.PROHIBITED,
            approval_level="L4", operations=[], affected_objects=[],
            reversible=False, rollback_ops=[],
            denied_reason="no_operations",
        )

    risk = classify_risk(ops)
    if risk == MigrationRisk.PROHIBITED:
        return MigrationPlan(
            ok=False, fingerprint="", risk=risk,
            approval_level="L4", operations=[o.canonical() for o in ops],
            affected_objects=[], reversible=False, rollback_ops=[],
            denied_reason="risk_prohibited",
        )

    # Re-bind request fields for fingerprint
    req.operations = ops
    if not req.expected_postconditions:
        req.expected_postconditions = default_postconditions(ops)
    if not req.rollback_ops:
        req.rollback_ops = default_rollback_ops(ops)
    if not req.migration_name:
        req.migration_name = f"mig_{ops[0].op}_{ops[0].table}"

    fp = req.fingerprint()
    req.ensure_idempotency_key()
    affected = sorted({o.table for o in ops})
    warnings: list[str] = []
    if risk == MigrationRisk.ELEVATED:
        warnings.append("elevated_risk_requires_L4_approval")
    warnings.append("rollback_not_auto_executed")

    return MigrationPlan(
        ok=True,
        fingerprint=fp,
        risk=risk,
        approval_level=RISK_TO_APPROVAL[risk],
        operations=[o.canonical() for o in ops],
        affected_objects=affected,
        reversible=True,
        rollback_ops=req.rollback_ops,
        warnings=warnings,
        requestor=req.requestor,
        environment=req.environment,
        project_id=req.project_id,
        migration_name=req.migration_name,
        provider=req.provider,
    )


def ops_to_sql(ops: list[MigrationOp]) -> list[str]:
    """Generate deterministic SQL statements for provider execution payload."""
    stmts: list[str] = []
    for o in ops:
        if o.op == "create_table":
            parts = []
            for c in o.columns:
                null = "" if c.nullable else " NOT NULL"
                pk = " PRIMARY KEY" if c.primary_key else ""
                parts.append(f"{c.name} {c.type}{null}{pk}")
            stmts.append(f"CREATE TABLE IF NOT EXISTS {o.table} ({', '.join(parts)})")
        elif o.op == "add_column" and o.column:
            c = o.column
            stmts.append(
                f"ALTER TABLE {o.table} ADD COLUMN IF NOT EXISTS {c.name} {c.type}"
            )
        elif o.op == "create_index":
            uq = "UNIQUE " if o.unique else ""
            cols = ", ".join(o.index_columns)
            stmts.append(
                f"CREATE {uq}INDEX IF NOT EXISTS {o.index_name} ON {o.table} ({cols})"
            )
    return stmts


def build_request_from_dict(d: dict) -> tuple[MigrationRequest | None, str]:
    """Construct MigrationRequest from agent/operator input."""
    if not isinstance(d, dict):
        return None, "request_not_object"
    raw_sql = d.get("sql") or d.get("body") or d.get("migration_body")
    err = reject_raw_sql(raw_sql if isinstance(raw_sql, str) else None)
    if err:
        return None, err

    ops, oerr = parse_operations(d.get("operations") or d)
    if oerr and d.get("operations") is not None:
        return None, oerr
    if oerr and not d.get("operations"):
        # try nested
        ops, oerr = parse_operations(d)
        if oerr:
            return None, oerr

    req = MigrationRequest(
        provider=str(d.get("provider") or "insforge"),
        project_id=str(d.get("project_id") or d.get("project") or "pilot"),
        environment=str(d.get("environment") or "dev").lower(),
        migration_name=str(d.get("migration_name") or d.get("name") or ""),
        version=str(d.get("version") or "1"),
        operations=ops,
        expected_preconditions=dict(d.get("expected_preconditions") or {}),
        expected_postconditions=dict(d.get("expected_postconditions") or {}),
        rollback_ops=list(d.get("rollback_ops") or []),
        irreversible=bool(d.get("irreversible", False)),
        requestor=str(d.get("requestor") or d.get("actor") or "system"),
        mission_id=str(d.get("mission_id") or ""),
        run_id=str(d.get("run_id") or ""),
        idempotency_key=str(d.get("idempotency_key") or ""),
        approval_id=str(d.get("approval_id") or ""),
        max_duration_sec=float(d.get("max_duration_sec") or 30.0),
        metadata=dict(d.get("metadata") or {}),
    )
    return req, ""
