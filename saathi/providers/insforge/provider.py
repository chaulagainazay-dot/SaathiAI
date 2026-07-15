"""Read-only InsForge provider — data plane pilot only.

All operations are GET-only against an allowlist. Writes raise WRITE_FORBIDDEN.
Trading Guardian is never engaged.
"""
from __future__ import annotations

import time
from typing import Any, Optional

from saathi.providers.insforge.client import InsForgeClient
from saathi.providers.insforge.config import InsForgeConfig, load_config
from saathi.providers.insforge.errors import InsForgeError, InsForgeErrorCategory
from saathi.providers.insforge.sanitization import (
    sanitize_logs,
    sanitize_value,
    summarize_for_audit,
)
from saathi.providers.insforge.types import OperationResult

PROVIDER_ID = "insforge"
PILOT_STATUS = "PILOT_APPROVED_READ_ONLY"

# Capabilities (read-only)
CAPS = frozenset({
    "health",
    "provider_metadata",
    "list_schema_objects",
    "list_edge_functions",
    "list_storage_buckets",
    "read_sanitized_logs",
})

# Explicit denylist for regression tests / docs
WRITE_DENYLIST = frozenset({
    "migrate", "run_sql", "create_table", "delete_table",
    "upload_object", "delete_object", "create_bucket", "delete_bucket",
    "deploy_function", "delete_function", "create_user", "delete_user",
    "create_secret", "update_secret", "configure_auth",
    "deploy_site", "create_schedule", "write_memory",
    "model_complete", "trade", "place_order", "mcp_invoke",
})


class InsForgeProvider:
    """Governed read-only pilot adapter."""

    id = PROVIDER_ID

    def __init__(
        self,
        config: InsForgeConfig | None = None,
        *,
        client: InsForgeClient | None = None,
        transport: Any = None,
        audit: bool = True,
    ):
        self.config = config or load_config()
        self._client = client or InsForgeClient(self.config, transport=transport)
        self._audit = audit
        self._last_audit: list[dict] = []

    # ── public operations ───────────────────────────────────────────────────

    def health(self) -> OperationResult:
        return self._run("health", self._op_health)

    def get_provider_metadata(self) -> OperationResult:
        return self._run("provider_metadata", self._op_metadata)

    def list_schema_objects(self) -> OperationResult:
        return self._run("list_schema_objects", self._op_tables)

    def list_edge_functions(self) -> OperationResult:
        return self._run("list_edge_functions", self._op_functions)

    def list_storage_buckets(self) -> OperationResult:
        return self._run("list_storage_buckets", self._op_buckets)

    def read_sanitized_logs(self, *, limit: int | None = None) -> OperationResult:
        return self._run(
            "read_sanitized_logs",
            lambda: self._op_logs(limit=limit),
        )

    def invoke(self, operation: str, **kwargs) -> OperationResult:
        """Dispatch by name. Unknown/write ops fail closed."""
        op = (operation or "").strip().lower()
        if op in WRITE_DENYLIST or op.startswith("write_") or op.startswith("deploy_"):
            return self._fail(
                op or "unknown",
                InsForgeErrorCategory.WRITE_FORBIDDEN,
                "write_or_deploy_not_in_pilot",
            )
        if op not in CAPS:
            return self._fail(
                op or "unknown",
                InsForgeErrorCategory.UNSUPPORTED_OPERATION,
                f"unsupported:{op}",
            )
        if op == "health":
            return self.health()
        if op == "provider_metadata":
            return self.get_provider_metadata()
        if op == "list_schema_objects":
            return self.list_schema_objects()
        if op == "list_edge_functions":
            return self.list_edge_functions()
        if op == "list_storage_buckets":
            return self.list_storage_buckets()
        if op == "read_sanitized_logs":
            return self.read_sanitized_logs(limit=kwargs.get("limit"))
        return self._fail(op, InsForgeErrorCategory.UNSUPPORTED_OPERATION, op)

    def config_public(self) -> dict:
        return self.config.public_dict()

    def recent_audit(self, limit: int = 20) -> list[dict]:
        return list(self._last_audit[-limit:])

    # ── internals ───────────────────────────────────────────────────────────

    def _run(self, operation: str, fn) -> OperationResult:
        t0 = time.time()
        if not self.config.enabled:
            return self._fail(
                operation, InsForgeErrorCategory.PROVIDER_DISABLED, "disabled_by_default",
                duration_ms=(time.time() - t0) * 1000,
            )
        try:
            data = fn()
            res = OperationResult(
                ok=True, operation=operation, data=data,
                duration_ms=(time.time() - t0) * 1000,
            )
            self._emit_audit(res)
            return res
        except InsForgeError as e:
            res = OperationResult(
                ok=False, operation=operation,
                error_category=e.category.value, detail=e.detail,
                duration_ms=(time.time() - t0) * 1000,
            )
            self._emit_audit(res)
            return res
        except Exception as e:
            res = OperationResult(
                ok=False, operation=operation,
                error_category=InsForgeErrorCategory.PROVIDER_UNAVAILABLE.value,
                detail=type(e).__name__,
                duration_ms=(time.time() - t0) * 1000,
            )
            self._emit_audit(res)
            return res

    def _fail(
        self, operation: str, cat: InsForgeErrorCategory, detail: str,
        *, duration_ms: float = 0.0,
    ) -> OperationResult:
        res = OperationResult(
            ok=False, operation=operation,
            error_category=cat.value, detail=detail[:300],
            duration_ms=duration_ms,
        )
        self._emit_audit(res)
        return res

    def _op_health(self) -> dict:
        raw = self._client.get_json("/api/health")
        if not isinstance(raw, dict):
            raise InsForgeError(
                InsForgeErrorCategory.INVALID_PROVIDER_RESPONSE, "health_not_object",
            )
        status = str(raw.get("status") or raw.get("state") or "unknown")[:40]
        return sanitize_value({
            "status": status,
            "version": str(raw.get("version") or "")[:40],
            "service": str(raw.get("service") or "Insforge")[:80],
            "reachable": True,
            "pilot_status": PILOT_STATUS,
            "writes_enabled": False,
        })

    def _op_metadata(self) -> dict:
        raw = self._client.get_json("/api/metadata")
        if not isinstance(raw, dict):
            # Some deployments may return nested structure — accept dict only
            raise InsForgeError(
                InsForgeErrorCategory.INVALID_PROVIDER_RESPONSE, "metadata_not_object",
            )
        # Keep high-level keys only
        allowed_top = (
            "auth", "database", "storage", "functions", "realtime",
            "version", "project", "app", "status",
        )
        slim = {k: raw[k] for k in allowed_top if k in raw}
        if not slim:
            slim = {"keys": sorted(str(k) for k in raw.keys())[:30]}
        return {
            "provider": PROVIDER_ID,
            "pilot_status": PILOT_STATUS,
            "metadata": sanitize_value(slim, max_str=200),
        }

    def _op_tables(self) -> dict:
        raw = self._client.get_json("/api/database/tables")
        tables = _as_list(raw, keys=("tables", "data", "items"))
        names = []
        for t in tables[:200]:
            if isinstance(t, str):
                names.append(t[:120])
            elif isinstance(t, dict):
                n = t.get("name") or t.get("table") or t.get("table_name") or t.get("id")
                if n:
                    names.append(str(n)[:120])
        return {
            "count": len(names),
            "tables": names,
            "sanitized": True,
        }

    def _op_functions(self) -> dict:
        raw = self._client.get_json("/api/functions")
        items = _as_list(raw, keys=("functions", "data", "items"))
        out = []
        for f in items[:100]:
            if isinstance(f, dict):
                out.append(sanitize_value({
                    "slug": f.get("slug") or f.get("name") or f.get("id"),
                    "name": f.get("name"),
                    "status": f.get("status"),
                    "updated_at": f.get("updated_at") or f.get("updatedAt"),
                }, max_str=120))
            elif isinstance(f, str):
                out.append({"slug": f[:120]})
        return {"count": len(out), "functions": out}

    def _op_buckets(self) -> dict:
        raw = self._client.get_json("/api/storage/buckets")
        items = _as_list(raw, keys=("buckets", "data", "items"))
        out = []
        for b in items[:100]:
            if isinstance(b, dict):
                out.append(sanitize_value({
                    "name": b.get("name") or b.get("id") or b.get("bucket"),
                    "public": b.get("public"),
                    "created_at": b.get("created_at") or b.get("createdAt"),
                }, max_str=120))
            elif isinstance(b, str):
                out.append({"name": b[:120]})
        return {"count": len(out), "buckets": out}

    def _op_logs(self, *, limit: int | None = None) -> dict:
        lim = limit if limit is not None else self.config.max_log_records
        lim = max(1, min(int(lim), self.config.max_log_records))
        try:
            raw = self._client.get_json("/api/logs", params={"limit": lim})
        except InsForgeError as e:
            if e.category in (
                InsForgeErrorCategory.PROVIDER_UNAVAILABLE,
                InsForgeErrorCategory.PERMISSION_DENIED,
            ):
                # Logs endpoint may be admin-only or absent — report unsupported cleanly
                if e.status_code in (404, 405):
                    raise InsForgeError(
                        InsForgeErrorCategory.UNSUPPORTED_OPERATION,
                        "logs_endpoint_unavailable",
                    ) from e
            raise
        records = _as_list(raw, keys=("logs", "data", "items", "records"))
        if isinstance(raw, list):
            records = raw
        cleaned = sanitize_logs(records, max_records=lim)
        return {
            "count": len(cleaned),
            "logs": cleaned,
            "sanitized": True,
        }

    def _emit_audit(self, res: OperationResult) -> None:
        if not self._audit:
            return
        summary = summarize_for_audit(
            res.operation, res.to_dict(), error=res.error_category,
        )
        record = {
            "provider": PROVIDER_ID,
            "operation": res.operation,
            "request_id": res.request_id,
            "ok": res.ok,
            "error_category": res.error_category,
            "duration_ms": res.duration_ms,
            "summary": summary,
            "pilot_status": PILOT_STATUS,
        }
        self._last_audit.append(record)
        if len(self._last_audit) > 100:
            del self._last_audit[: len(self._last_audit) - 100]

        # Platform event bus (best-effort)
        try:
            from saathi.events import bus as bus_mod
            b = getattr(bus_mod, "default_bus", None)
            if callable(b):
                b().emit(
                    "provider.insforge.operation",
                    "insforge_provider",
                    {
                        "operation": res.operation,
                        "ok": res.ok,
                        "error_category": res.error_category,
                        "request_id": res.request_id,
                        "duration_ms": res.duration_ms,
                    },
                )
        except Exception:
            pass

        # SecurityStore audit (best-effort)
        try:
            from saathi.security.store import SecurityStore
            SecurityStore().audit(
                f"insforge.{res.operation}",
                ok=res.ok,
                user_id="system",
                detail=(res.error_category or "ok")[:200],
            )
        except Exception:
            pass

        # Evidence for successful reads (bounded metadata only)
        if res.ok:
            try:
                from saathi.evidence.schema import Evidence
                from saathi.evidence import store as ev_mod
                e = Evidence(
                    department="engineering",
                    project="insforge_pilot",
                    episode=res.request_id,
                    director="insforge_provider",
                    workflow="m18.3",
                    provider=PROVIDER_ID,
                    status=res.operation,
                    confidence=1.0,
                    metrics={
                        "duration_ms": res.duration_ms,
                        "operation": res.operation,
                        "pilot": PILOT_STATUS,
                    },
                    recommendation="read_only_insforge_pilot",
                )
                res.evidence_id = ev_mod.EvidenceStore().record(e)
                res.audited = True
            except Exception:
                res.audited = True  # event/security may still have fired
        else:
            res.audited = True


def _as_list(raw: Any, *, keys: tuple[str, ...]) -> list:
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        for k in keys:
            v = raw.get(k)
            if isinstance(v, list):
                return v
        # single object wrapping
        if "name" in raw or "table" in raw:
            return [raw]
    return []


_default: InsForgeProvider | None = None


def default_provider(**kwargs) -> InsForgeProvider:
    global _default
    if kwargs or _default is None:
        if kwargs:
            return InsForgeProvider(**kwargs)
        _default = InsForgeProvider()
    return _default


def reset_default_provider() -> None:
    global _default
    _default = None
