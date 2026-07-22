"""Provider-neutral codebase semantic-recall contract (SaathiOS-native).

Operations: health, search, get, list_namespaces, write_verified_lesson,
delete_or_archive_lesson.

Boundary rules:
- search/get may read semantic codebase memory
- writes accept only verified lessons (never speculative model output)
- namespace binds to exact project
- secret-like material rejected
- writes produce Evidence
- write failures must not break core execution
- MCP responses are untrusted input
"""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol

from saathi.mcp_governance import events as ev
from saathi.mcp_governance.inventory import CANONICAL_CODEBASE_MEMORY_ID
from saathi.mcp_governance.namespace import (
    NamespaceError,
    assert_namespace_bound,
    parse_namespace_query,
    project_namespace,
)
from saathi.mcp_governance.policy import (
    is_enabled,
    retry_policy,
    should_retry,
    timeout_policy,
)
from saathi.mcp_governance.redaction import contains_secret_like, redact_obj, safe_summary

# ── data types ──────────────────────────────────────────────────────────────


@dataclass
class MemoryHit:
    id: str
    namespace: str
    title: str
    snippet: str
    score: float = 0.0
    metadata: dict = field(default_factory=dict)
    untrusted: bool = True  # MCP responses are always untrusted

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "namespace": self.namespace,
            "title": self.title,
            "snippet": self.snippet[:500],
            "score": self.score,
            "metadata": safe_summary(self.metadata),
            "untrusted": True,
        }


@dataclass
class MemoryOpResult:
    ok: bool
    operation: str
    data: Any = None
    error: str = ""
    error_category: str = ""
    degraded: bool = False
    consulted: bool = False  # True only if memory backend was actually used
    evidence_id: str = ""
    denied: bool = False
    latency_ms: float = 0.0

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "operation": self.operation,
            "data": self.data,
            "error": self.error[:300],
            "error_category": self.error_category,
            "degraded": self.degraded,
            "consulted": self.consulted,
            "evidence_id": self.evidence_id,
            "denied": self.denied,
            "latency_ms": round(self.latency_ms, 2),
        }


@dataclass
class LessonWriteRequest:
    namespace: str
    title: str
    content: str
    verified: bool = False
    verification_source: str = ""  # e.g. test_id, human_approval_id
    actor: str = "system"
    project_root: str = ""
    speculative: bool = False  # model-generated speculative → reject
    metadata: dict = field(default_factory=dict)

    def is_governed_ready(self) -> tuple[bool, str]:
        if self.speculative:
            return False, "speculative lesson rejected"
        if not self.verified:
            return False, "lesson not verified"
        if not self.verification_source:
            return False, "verification_source required"
        if not (self.title or "").strip():
            return False, "title required"
        if not (self.content or "").strip():
            return False, "content required"
        if contains_secret_like(self.content) or contains_secret_like(self.title):
            return False, "secret-like content rejected"
        return True, ""


class MemoryBackend(Protocol):
    def ping(self) -> dict: ...
    def search(self, namespace: str, query: str, *, top_k: int = 8) -> list[dict]: ...
    def get(self, namespace: str, item_id: str) -> dict | None: ...
    def list_namespaces(self) -> list[str]: ...
    def write_lesson(self, namespace: str, title: str, content: str, meta: dict) -> dict: ...
    def archive_lesson(self, namespace: str, item_id: str) -> dict: ...


# ── fake backend (deterministic local test harness) ─────────────────────────


class FakeMemoryBackend:
    """Deterministic in-process MCP stand-in for tests and degraded demos."""

    def __init__(self, *, available: bool = True, identity: str = "fake-mcp-v1"):
        self.available = available
        self.identity = identity
        self._store: dict[str, dict[str, dict]] = {}  # ns -> id -> record
        self._lock = threading.RLock()
        self.call_counts: dict[str, int] = {}
        self.last_timeout_sec: float | None = None

    def _count(self, op: str) -> None:
        self.call_counts[op] = self.call_counts.get(op, 0) + 1

    def set_available(self, available: bool) -> None:
        self.available = available

    def ping(self) -> dict:
        self._count("ping")
        if not self.available:
            raise ConnectionError("fake backend unavailable")
        return {
            "ok": True,
            "backend_identity": self.identity,
            "transport": "inprocess",
        }

    def search(self, namespace: str, query: str, *, top_k: int = 8) -> list[dict]:
        self._count("search")
        if not self.available:
            raise ConnectionError("fake backend unavailable")
        q = (query or "").lower()
        hits = []
        with self._lock:
            for item_id, rec in self._store.get(namespace, {}).items():
                if rec.get("archived"):
                    continue
                blob = f"{rec.get('title','')} {rec.get('content','')}".lower()
                if q in blob or not q:
                    hits.append({
                        "id": item_id,
                        "namespace": namespace,
                        "title": rec.get("title", ""),
                        "snippet": (rec.get("content") or "")[:200],
                        "score": 1.0 if q and q in blob else 0.5,
                        "metadata": rec.get("meta") or {},
                    })
        hits.sort(key=lambda h: -h["score"])
        return hits[:top_k]

    def get(self, namespace: str, item_id: str) -> dict | None:
        self._count("get")
        if not self.available:
            raise ConnectionError("fake backend unavailable")
        with self._lock:
            rec = self._store.get(namespace, {}).get(item_id)
            if not rec or rec.get("archived"):
                return None
            return {
                "id": item_id,
                "namespace": namespace,
                "title": rec.get("title", ""),
                "content": rec.get("content", ""),
                "metadata": rec.get("meta") or {},
            }

    def list_namespaces(self) -> list[str]:
        self._count("list_namespaces")
        if not self.available:
            raise ConnectionError("fake backend unavailable")
        with self._lock:
            return sorted(self._store.keys())

    def write_lesson(self, namespace: str, title: str, content: str, meta: dict) -> dict:
        self._count("write_lesson")
        if not self.available:
            raise ConnectionError("fake backend unavailable")
        item_id = uuid.uuid4().hex[:12]
        with self._lock:
            self._store.setdefault(namespace, {})[item_id] = {
                "title": title,
                "content": content,
                "meta": dict(meta or {}),
                "archived": False,
            }
        return {"id": item_id, "namespace": namespace, "ok": True}

    def archive_lesson(self, namespace: str, item_id: str) -> dict:
        self._count("archive_lesson")
        if not self.available:
            raise ConnectionError("fake backend unavailable")
        with self._lock:
            rec = self._store.get(namespace, {}).get(item_id)
            if not rec:
                return {"ok": False, "error": "not_found"}
            rec["archived"] = True
        return {"ok": True, "id": item_id}


# ── service ─────────────────────────────────────────────────────────────────


class CodebaseMemoryService:
    """Governed facade implementing MemoryCapability operations."""

    def __init__(
        self,
        backend: MemoryBackend | None = None,
        *,
        bound_project_root: str = "",
        bound_namespace: str = "",
        security_store: Any = None,
        evidence_store: Any = None,
    ):
        self.backend = backend or FakeMemoryBackend()
        self.bound_project_root = bound_project_root
        self.bound_namespace = bound_namespace or (
            project_namespace(bound_project_root) if bound_project_root else "saathiai"
        )
        self._security_store = security_store
        self._evidence_store = evidence_store
        self._circuit_open_until = 0.0
        self._last_error_category = ""
        self._last_success = 0.0
        self._lock = threading.RLock()

    # -- health ---------------------------------------------------------------
    def health(self) -> dict:
        from saathi.mcp_governance.health import build_health

        return build_health(self).to_dict()

    # -- search (read-only, low risk) ----------------------------------------
    def search(
        self,
        query: str,
        *,
        namespace: str | None = None,
        top_k: int = 8,
    ) -> MemoryOpResult:
        t0 = time.time()
        op = "search"
        if not is_enabled(CANONICAL_CODEBASE_MEMORY_ID):
            return self._degraded(op, "mcp disabled", "disabled", t0)
        try:
            ns = parse_namespace_query(namespace or self.bound_namespace)
            assert_namespace_bound(ns, bound_ns=self.bound_namespace)
        except NamespaceError as e:
            ev.emit(ev.MCP_NAMESPACE_VIOLATION, {"error": str(e), "op": op})
            self._audit("mcp.namespace_violation", ok=False, detail=str(e))
            return MemoryOpResult(
                ok=False, operation=op, error=str(e),
                error_category="namespace_violation", denied=True,
                latency_ms=(time.time() - t0) * 1000,
            )
        if self._circuit_blocked():
            return self._degraded(op, "circuit open", "circuit_open", t0)

        attempts = 0
        last_err = ""
        cat = "unavailable"
        while True:
            try:
                raw = self.backend.search(ns, query, top_k=top_k)
                # Treat as untrusted
                hits = [
                    MemoryHit(
                        id=str(r.get("id", "")),
                        namespace=ns,
                        title=str(r.get("title", ""))[:200],
                        snippet=str(r.get("snippet", r.get("content", "")))[:500],
                        score=float(r.get("score") or 0),
                        metadata=redact_obj(r.get("metadata") or {}),
                        untrusted=True,
                    ).to_dict()
                    for r in (raw or [])
                    if isinstance(r, dict)
                ]
                self._mark_success()
                ev.emit(ev.MCP_SEARCH_SUCCEEDED, {
                    "namespace": ns, "hit_count": len(hits), "consulted": True,
                })
                return MemoryOpResult(
                    ok=True, operation=op, data={"hits": hits, "untrusted": True},
                    consulted=True, latency_ms=(time.time() - t0) * 1000,
                )
            except Exception as e:
                last_err = str(e)[:200]
                cat = _classify_error(e)
                if should_retry(cat, operation=op, attempt=attempts):
                    attempts += 1
                    continue
                self._mark_failure(cat)
                ev.emit(ev.MCP_SEARCH_FAILED, {
                    "namespace": ns, "error_category": cat, "consulted": False,
                })
                return self._degraded(op, last_err, cat, t0)

    def get(self, item_id: str, *, namespace: str | None = None) -> MemoryOpResult:
        t0 = time.time()
        op = "get"
        if not is_enabled(CANONICAL_CODEBASE_MEMORY_ID):
            return self._degraded(op, "mcp disabled", "disabled", t0)
        try:
            ns = parse_namespace_query(namespace or self.bound_namespace)
            assert_namespace_bound(ns, bound_ns=self.bound_namespace)
        except NamespaceError as e:
            ev.emit(ev.MCP_NAMESPACE_VIOLATION, {"error": str(e), "op": op})
            return MemoryOpResult(
                ok=False, operation=op, error=str(e),
                error_category="namespace_violation", denied=True,
                latency_ms=(time.time() - t0) * 1000,
            )
        try:
            raw = self.backend.get(ns, item_id)
            self._mark_success()
            data = redact_obj(raw) if raw else None
            if isinstance(data, dict):
                data["untrusted"] = True
            return MemoryOpResult(
                ok=True, operation=op, data=data, consulted=True,
                latency_ms=(time.time() - t0) * 1000,
            )
        except Exception as e:
            cat = _classify_error(e)
            self._mark_failure(cat)
            return self._degraded(op, str(e)[:200], cat, t0)

    def list_namespaces(self) -> MemoryOpResult:
        t0 = time.time()
        op = "list_namespaces"
        if not is_enabled(CANONICAL_CODEBASE_MEMORY_ID):
            return self._degraded(op, "mcp disabled", "disabled", t0)
        try:
            names = self.backend.list_namespaces()
            # Only expose bound namespace to callers by default
            filtered = [n for n in names if n == self.bound_namespace]
            self._mark_success()
            return MemoryOpResult(
                ok=True, operation=op,
                data={"namespaces": filtered, "bound": self.bound_namespace},
                consulted=True, latency_ms=(time.time() - t0) * 1000,
            )
        except Exception as e:
            cat = _classify_error(e)
            self._mark_failure(cat)
            return self._degraded(op, str(e)[:200], cat, t0)

    # -- writes (approval-controlled) ----------------------------------------
    def write_verified_lesson(self, req: LessonWriteRequest) -> MemoryOpResult:
        t0 = time.time()
        op = "write_verified_lesson"
        ev.emit(ev.MCP_WRITE_REQUESTED, {
            "namespace": req.namespace, "verified": req.verified,
            "speculative": req.speculative, "actor": req.actor,
        })
        if not is_enabled(CANONICAL_CODEBASE_MEMORY_ID):
            return self._deny(op, "mcp disabled", "disabled", t0)

        ready, reason = req.is_governed_ready()
        if not ready:
            if "secret" in reason:
                ev.emit(ev.MCP_SECRET_REJECTED, {"reason": reason})
                self._audit("mcp.secret_rejected", ok=False, detail=reason)
            else:
                self._audit("mcp.write_denied", ok=False, detail=reason)
            ev.emit(ev.MCP_WRITE_DENIED, {"reason": reason})
            return self._deny(op, reason, "policy", t0)

        # Non-idempotent: never blind-retry (policy check for tests)
        pol = retry_policy(operation=op)
        assert pol["max_retries"] == 0 and pol["blind_retry_forbidden"]

        try:
            ns = parse_namespace_query(req.namespace or self.bound_namespace)
            assert_namespace_bound(
                ns,
                bound_ns=self.bound_namespace,
                project_root=req.project_root or self.bound_project_root or None,
                candidate_path=(req.project_root or None),
            )
        except NamespaceError as e:
            ev.emit(ev.MCP_NAMESPACE_VIOLATION, {"error": str(e), "op": op})
            self._audit("mcp.namespace_violation", ok=False, detail=str(e))
            return self._deny(op, str(e), "namespace_violation", t0)

        # ToolIntent / ExecutionGateway governance marker (family=mcp)
        intent_meta = {
            "family": "mcp",
            "mcp_id": CANONICAL_CODEBASE_MEMORY_ID,
            "operation": op,
            "risk": "medium",
            "approval_level": "L2",
            "verified": True,
            "verification_source": req.verification_source,
        }
        try:
            result = self.backend.write_lesson(
                ns, req.title, req.content,
                {
                    "verification_source": req.verification_source,
                    "actor": req.actor,
                    "intent": intent_meta,
                },
            )
            eid = self._record_evidence(op, ns, req, result)
            self._mark_success()
            ev.emit(ev.MCP_WRITE_SUCCEEDED, {
                "namespace": ns, "lesson_id": result.get("id"), "evidence_id": eid,
            })
            return MemoryOpResult(
                ok=True, operation=op,
                data={"id": result.get("id"), "namespace": ns, "untrusted_response": True},
                consulted=True, evidence_id=eid,
                latency_ms=(time.time() - t0) * 1000,
            )
        except Exception as e:
            # Write failure must not break core — return error, no raise
            cat = _classify_error(e)
            self._mark_failure(cat)
            self._audit("mcp.write_failed", ok=False, detail=str(e)[:200])
            return MemoryOpResult(
                ok=False, operation=op, error=str(e)[:200],
                error_category=cat, consulted=False,
                latency_ms=(time.time() - t0) * 1000,
            )

    def delete_or_archive_lesson(
        self, item_id: str, *, namespace: str | None = None, actor: str = "system",
    ) -> MemoryOpResult:
        t0 = time.time()
        op = "delete_or_archive_lesson"
        ev.emit(ev.MCP_WRITE_REQUESTED, {"namespace": namespace, "op": op, "actor": actor})
        if not is_enabled(CANONICAL_CODEBASE_MEMORY_ID):
            return self._deny(op, "mcp disabled", "disabled", t0)
        pol = retry_policy(operation=op)
        assert pol["blind_retry_forbidden"]
        try:
            ns = parse_namespace_query(namespace or self.bound_namespace)
            assert_namespace_bound(ns, bound_ns=self.bound_namespace)
            result = self.backend.archive_lesson(ns, item_id)
            if not result.get("ok"):
                return self._deny(op, result.get("error", "archive_failed"), "not_found", t0)
            eid = self._record_evidence_simple(op, ns, item_id)
            ev.emit(ev.MCP_WRITE_SUCCEEDED, {"namespace": ns, "lesson_id": item_id})
            return MemoryOpResult(
                ok=True, operation=op, data=result, consulted=True, evidence_id=eid,
                latency_ms=(time.time() - t0) * 1000,
            )
        except NamespaceError as e:
            ev.emit(ev.MCP_NAMESPACE_VIOLATION, {"error": str(e)})
            return self._deny(op, str(e), "namespace_violation", t0)
        except Exception as e:
            return MemoryOpResult(
                ok=False, operation=op, error=str(e)[:200],
                error_category=_classify_error(e),
                latency_ms=(time.time() - t0) * 1000,
            )

    # -- helpers --------------------------------------------------------------
    def _degraded(self, op: str, err: str, cat: str, t0: float) -> MemoryOpResult:
        ev.emit(ev.MCP_UNAVAILABLE, {"operation": op, "error_category": cat})
        return MemoryOpResult(
            ok=False, operation=op, error=err[:300], error_category=cat,
            degraded=True, consulted=False,
            data={"hits": [], "degraded": True, "memory_consulted": False},
            latency_ms=(time.time() - t0) * 1000,
        )

    def _deny(self, op: str, err: str, cat: str, t0: float) -> MemoryOpResult:
        ev.emit(ev.MCP_WRITE_DENIED, {"operation": op, "reason": err[:200]})
        self._audit(f"mcp.{cat}", ok=False, detail=err[:200])
        return MemoryOpResult(
            ok=False, operation=op, error=err[:300], error_category=cat,
            denied=True, consulted=False,
            latency_ms=(time.time() - t0) * 1000,
        )

    def _circuit_blocked(self) -> bool:
        return time.time() < self._circuit_open_until

    def _mark_success(self) -> None:
        with self._lock:
            self._last_success = time.time()
            self._last_error_category = ""
            self._circuit_open_until = 0.0

    def _mark_failure(self, category: str) -> None:
        with self._lock:
            self._last_error_category = category
            # short cooldown — no endless retry loop
            self._circuit_open_until = time.time() + 2.0

    def _audit(self, event: str, *, ok: bool, detail: str) -> None:
        if self._security_store is not None:
            try:
                self._security_store.audit(event, ok=ok, user_id="system", detail=detail[:400])
                return
            except Exception:
                pass
        ev.audit_security(event, ok=ok, detail=detail)

    def _record_evidence(
        self, op: str, ns: str, req: LessonWriteRequest, result: dict,
    ) -> str:
        try:
            from saathi.evidence.schema import Evidence
            from saathi.evidence import store as ev_store_mod
            store = self._evidence_store
            if store is None:
                store = ev_store_mod.EvidenceStore()
            e = Evidence(
                department="engineering",
                project=ns,
                episode=result.get("id", ""),
                director="mcp_governance",
                workflow="m17.25",
                provider=CANONICAL_CODEBASE_MEMORY_ID,
                model="codebase-memory",
                status="verified_lesson_written",
                confidence=1.0,
                metrics={
                    "operation": op,
                    "verification_source": req.verification_source,
                    "actor": req.actor,
                    # no full content
                    "title_len": len(req.title or ""),
                    "content_len": len(req.content or ""),
                },
                recommendation="verified lesson stored via governed MCP path",
            )
            return store.record(e)
        except Exception:
            return ""

    def _record_evidence_simple(self, op: str, ns: str, item_id: str) -> str:
        try:
            from saathi.evidence.schema import Evidence
            from saathi.evidence import store as ev_store_mod
            store = self._evidence_store or ev_store_mod.EvidenceStore()
            e = Evidence(
                department="engineering", project=ns, episode=item_id,
                director="mcp_governance", workflow="m17.25",
                provider=CANONICAL_CODEBASE_MEMORY_ID,
                status=op, metrics={"operation": op},
            )
            return store.record(e)
        except Exception:
            return ""


def _classify_error(e: Exception) -> str:
    name = type(e).__name__.lower()
    msg = str(e).lower()
    if "timeout" in name or "timeout" in msg:
        return "timeout"
    if "connect" in name or "unavailable" in msg or "connection" in msg:
        return "connection"
    if isinstance(e, PermissionError):
        return "permission"
    return "temporary" if "temp" in msg else "unavailable"


# Protocol-facing alias
MemoryCapability = CodebaseMemoryService

_default: CodebaseMemoryService | None = None
_default_lock = threading.Lock()


def default_memory_service(
    *,
    project_root: str = "",
    backend: MemoryBackend | None = None,
) -> CodebaseMemoryService:
    global _default
    with _default_lock:
        if backend is not None or project_root:
            return CodebaseMemoryService(
                backend=backend,
                bound_project_root=project_root or "",
            )
        if _default is None:
            _default = CodebaseMemoryService(bound_namespace="saathiai")
        return _default


def reset_memory_service() -> None:
    global _default
    with _default_lock:
        _default = None
