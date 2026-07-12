"""M17.5 SQLite live application harness — a SECOND real application.

Wraps the system `sqlite3` CLI in the harness contract. Read ops use `-readonly`;
the DB path is confined to the pilot workspace; ATTACH / dot-commands / multi-
statement injection in untrusted SQL are rejected. Independent verification opens
the DB and runs `PRAGMA integrity_check` + counts. Argv-only through the adapter —
never a shell string. safe_mutation is risk 2 and reversible (operates only on a
pilot-workspace DB).
"""
from __future__ import annotations

import re
import shutil
import sqlite3 as _py_sqlite

from saathi.application_harness.models import (
    HarnessDefinition, HarnessOperation, TrustStatus, SideEffect,
)

# untrusted SQL must be a SINGLE read/simple statement — reject dangerous forms.
# dot-commands (.shell/.import/.output/...) are especially dangerous → any
# leading-or-standalone dot-command is rejected.
_FORBIDDEN_SQL = re.compile(
    r"(?i)(\battach\b|\bdetach\b|\bpragma\b|\bvacuum\b|load_extension|;|(^|\s)\.\w+)")
_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")


def sqlite_path() -> str | None:
    return shutil.which("sqlite3")


def available() -> dict:
    p = sqlite_path()
    return {"sqlite3": p, "available": bool(p)}


def definition() -> HarnessDefinition:
    present = available()["available"]
    return HarnessDefinition(
        harness_id="sqlite", display_name="SQLite", application_name="sqlite",
        application_vendor="SQLite", version="system" if present else "unknown",
        source_type="local", license="public-domain",
        install_method="system_executable", entrypoint=sqlite_path() or "sqlite3",
        required_executables=["sqlite3"], risk_ceiling=2,
        supported_operations=["inspect_schema", "query_readonly", "safe_mutation"],
        verification_strategy="integrity_check+count",
        trust_status=(TrustStatus.APPROVED.value if present
                      else TrustStatus.DISCOVERED.value),
        validation_status="wrapped_canonical" if present else "dependency_blocked")


def operations() -> list[HarnessOperation]:
    return [
        HarnessOperation("inspect_schema", "sqlite", "Inspect schema", risk=0,
                         side_effect_type=SideEffect.NONE.value, allowed_file_access="roots",
                         idempotency_behavior="idempotent", verification_rules=["sqlite_db"]),
        HarnessOperation("query_readonly", "sqlite", "Read-only query", risk=0,
                         side_effect_type=SideEffect.NONE.value, allowed_file_access="roots",
                         idempotency_behavior="idempotent", verification_rules=["sqlite_db"]),
        HarnessOperation("safe_mutation", "sqlite", "Reversible mutation", risk=2,
                         side_effect_type=SideEffect.LOCAL_REVERSIBLE.value,
                         allowed_file_access="roots", idempotency_behavior="conditional",
                         verification_rules=["sqlite_db"], reversibility="reversible"),
    ]


# ── argv builders (read ops enforce -readonly; untrusted SQL validated) ─────
def validate_sql(sql: str) -> tuple[bool, str]:
    if not sql or len(sql) > 4000:
        return False, "HARNESS_ARGUMENT_REJECTED:sql_size"
    if _FORBIDDEN_SQL.search(sql):
        return False, "HARNESS_ARGUMENT_REJECTED:forbidden_sql"
    return True, "ok"


def build_schema_argv(*, db_path: str) -> list[str]:
    return [sqlite_path() or "sqlite3", "-readonly", "-batch", "-bail",
            "-json", db_path, "SELECT name,type FROM sqlite_master ORDER BY name"]


def build_query_argv(*, db_path: str, sql: str) -> list[str]:
    return [sqlite_path() or "sqlite3", "-readonly", "-batch", "-bail",
            "-json", db_path, sql]


def build_mutation_argv(*, db_path: str, table: str) -> list[str]:
    """Reversible mutation built from CONSTANTS + a validated identifier only —
    no untrusted SQL string is interpolated."""
    # (caller validates table via valid_identifier)
    return [sqlite_path() or "sqlite3", "-batch", "-bail", db_path,
            f"CREATE TABLE IF NOT EXISTS {table}(id INTEGER PRIMARY KEY, v TEXT); "
            f"INSERT INTO {table}(v) VALUES('saathi-pilot')"]


def valid_identifier(name: str) -> bool:
    return bool(_IDENT.match(name or ""))


# ── independent verification (open DB directly, not via the CLI's word) ─────
def verify_db(db_path: str) -> dict:
    try:
        con = _py_sqlite.connect(f"file:{db_path}?mode=ro", uri=True)
        integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
        tables = con.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table'").fetchone()[0]
        con.close()
        return {"verified": integrity == "ok", "integrity": integrity,
                "tables": tables}
    except Exception as e:
        return {"verified": False, "reason": str(e)[:120]}
