"""M19.1 — Knowledge Service adoption gateway for first-wave callers.

Selected callers construct governed KnowledgeQuery objects and route through
KnowledgeService according to rollout mode. Legacy paths remain available.

Does not create parallel retrieval infrastructure.
"""
from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from saathi.knowledge.rollout import (
    CALLER_AUDIT_EVIDENCE,
    CALLER_CODEBASE_MEMORY_DOCUMENT,
    CALLER_CODEBASE_MEMORY_EXPLAIN,
    CALLER_CODEBASE_MEMORY_SEARCH,
    CALLER_CODEBASE_MEMORY_SYMBOL,
    CALLER_COMPAT_SEARCH,
    CALLER_MISSION_CONTEXT,
    RolloutMode,
    resolve_mode,
)
from saathi.knowledge.safety import safe_context_for_consumer, wrap_retrieved_context
from saathi.knowledge.service import KnowledgeService, default_knowledge_service
from saathi.knowledge.shadow import ShadowComparison, compare_retrieval
from saathi.knowledge.types import (
    KnowledgeQuery,
    KnowledgeResponse,
    RetrievalIntent,
    RetrievalProfile,
    TrustLevel,
)

# --- Fallback policy ---------------------------------------------------------

# Soft errors: may fall back under unified_with_fallback
FALLBACK_ALLOWED = frozenset({
    "source_unavailable",
    "timeout",
    "index_unavailable",
    "unsupported_adapter",
    "partial_below_threshold",
    "adapter_missing",
    "adapter_unsupported",
    "empty_results",
    "exception",
    "disabled",
})

# Hard denials: never fall back (security final)
FALLBACK_DENIED = frozenset({
    "permission_denied",
    "source_classification_denial",
    "secret_path_denial",
    "tenant_isolation",
    "invalid_query",
    "security_policy_denial",
    "empty_query",
    "write_ops_forbidden",
})

# Max query length extracted from free text (bounded intent)
_MAX_INTENT_CHARS = 240
_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_\.]{1,63}")


# --- Metrics (in-process; non-sensitive) ------------------------------------

_metrics_lock = threading.RLock()
_metrics: dict[str, Any] = {
    "calls_total": 0,
    "by_mode": {},
    "by_caller": {},
    "unified_success": 0,
    "unified_fail": 0,
    "fallback_count": 0,
    "fallback_denied_count": 0,
    "no_result": 0,
    "partial_result": 0,
    "permission_denial": 0,
    "shadow_comparisons": 0,
    "legacy_only_calls": 0,
    "compat_adapter_usage": 0,
    "latency_ms_sum": 0.0,
    "latency_ms_count": 0,
}


def metrics_snapshot() -> dict:
    with _metrics_lock:
        snap = dict(_metrics)
        snap["by_mode"] = dict(_metrics["by_mode"])
        snap["by_caller"] = dict(_metrics["by_caller"])
        n = snap["latency_ms_count"] or 0
        snap["latency_ms_avg"] = (
            round(snap["latency_ms_sum"] / n, 2) if n else 0.0
        )
        return snap


def reset_metrics() -> None:
    with _metrics_lock:
        _metrics["calls_total"] = 0
        _metrics["by_mode"] = {}
        _metrics["by_caller"] = {}
        _metrics["unified_success"] = 0
        _metrics["unified_fail"] = 0
        _metrics["fallback_count"] = 0
        _metrics["fallback_denied_count"] = 0
        _metrics["no_result"] = 0
        _metrics["partial_result"] = 0
        _metrics["permission_denial"] = 0
        _metrics["shadow_comparisons"] = 0
        _metrics["legacy_only_calls"] = 0
        _metrics["compat_adapter_usage"] = 0
        _metrics["latency_ms_sum"] = 0.0
        _metrics["latency_ms_count"] = 0


def _inc(key: str, n: int = 1) -> None:
    with _metrics_lock:
        _metrics[key] = int(_metrics.get(key, 0)) + n


def _inc_map(map_key: str, sub: str, n: int = 1) -> None:
    with _metrics_lock:
        m = _metrics[map_key]
        m[sub] = int(m.get(sub, 0)) + n


def _record_latency(ms: float) -> None:
    with _metrics_lock:
        _metrics["latency_ms_sum"] += float(ms)
        _metrics["latency_ms_count"] += 1


# --- Events ------------------------------------------------------------------

_events: list[dict] = []
_events_lock = threading.RLock()


def recent_adoption_events(limit: int = 30) -> list[dict]:
    with _events_lock:
        return list(_events[-limit:])


def reset_adoption_events() -> None:
    with _events_lock:
        _events.clear()


def _emit(event_type: str, payload: dict) -> None:
    # Never log full query text or result bodies
    safe = {
        k: v for k, v in payload.items()
        if k not in ("query_text", "results_content", "snippet", "context_text")
    }
    if "query" in safe and isinstance(safe["query"], str) and len(safe["query"]) > 80:
        safe["query"] = safe["query"][:80] + "…"
    rec = {"type": event_type, "source": "knowledge_adoption", "payload": safe}
    with _events_lock:
        _events.append(rec)
        if len(_events) > 200:
            del _events[: len(_events) - 200]
    try:
        from saathi.events import bus as bus_mod
        b = getattr(bus_mod, "default_bus", None)
        if callable(b):
            b().emit(event_type, "knowledge_adoption", safe)
    except Exception:
        pass


# --- Query builders (deterministic) ------------------------------------------

def extract_bounded_intent(raw: str, *, max_chars: int = _MAX_INTENT_CHARS) -> str:
    """Deterministic intent extraction — no model required."""
    text = (raw or "").strip()
    if not text:
        return ""
    # Collapse whitespace; drop obvious instruction framing
    text = re.sub(r"\s+", " ", text)
    for prefix in (
        "please ", "can you ", "could you ", "i need you to ",
        "search for ", "find ", "look up ", "locate ",
    ):
        if text.lower().startswith(prefix):
            text = text[len(prefix):]
            break
    # Prefer identifier-like tokens when present
    tokens = _TOKEN_RE.findall(text)
    if tokens and len(text) > max_chars:
        # Keep distinctive tokens
        uniq: list[str] = []
        seen: set[str] = set()
        for t in tokens:
            tl = t.lower()
            if tl in seen or len(tl) < 2:
                continue
            seen.add(tl)
            uniq.append(t)
            if len(" ".join(uniq)) >= max_chars:
                break
        if uniq:
            return " ".join(uniq)[:max_chars]
    return text[:max_chars]


def build_code_search_query(
    raw_query: str,
    *,
    caller_id: str = CALLER_CODEBASE_MEMORY_SEARCH,
    profile: RetrievalProfile | None = None,
    documentation_only: bool = False,
    tests_only: bool = False,
    symbol_filter: str = "",
    path_filter: str = "",
    top_k: int = 10,
    mission_id: str = "",
    run_id: str = "",
    project_root: str | Path | None = None,
    requesting_component: str = "codebase_memory",
) -> KnowledgeQuery:
    intent_text = extract_bounded_intent(raw_query or symbol_filter)
    if symbol_filter and symbol_filter not in intent_text:
        intent_text = extract_bounded_intent(f"{symbol_filter} {intent_text}")

    if profile is None:
        if symbol_filter or caller_id == CALLER_CODEBASE_MEMORY_SYMBOL:
            profile = RetrievalProfile.FAST_LOOKUP
        elif documentation_only or caller_id == CALLER_CODEBASE_MEMORY_DOCUMENT:
            profile = RetrievalProfile.CODE_EXPLAIN
        else:
            profile = RetrievalProfile.CODE_EXPLAIN

    if tests_only:
        intent = RetrievalIntent.FIND_TESTS
    elif documentation_only:
        intent = RetrievalIntent.FIND_DOCUMENTATION
    elif symbol_filter or profile == RetrievalProfile.FAST_LOOKUP:
        intent = RetrievalIntent.LOCATE_SYMBOL
    else:
        intent = RetrievalIntent.FIND_IMPLEMENTATION

    path_filters = [path_filter] if path_filter else []
    return KnowledgeQuery(
        query=intent_text,
        profile=profile,
        intent=intent,
        requesting_component=requesting_component,
        mission_id=mission_id or "",
        run_id=run_id or "",
        max_results=max(1, min(int(top_k or 10), 40)),
        path_filters=path_filters,
        min_trust=TrustLevel.LOW,
        include_generated=False,
        permission_actor="system",
    )


def build_mission_context_query(
    objective: str,
    *,
    mission_id: str = "",
    run_id: str = "",
    top_k: int = 14,
    requesting_component: str = "mission_prep",
) -> KnowledgeQuery:
    intent = extract_bounded_intent(objective)
    # Prefer architecture/policy tokens; strip huge mission blobs
    return KnowledgeQuery(
        query=intent,
        profile=RetrievalProfile.MISSION_CONTEXT,
        intent=RetrievalIntent.GATHER_MISSION_CONTEXT,
        requesting_component=requesting_component,
        mission_id=mission_id or "",
        run_id=run_id or "",
        max_results=max(1, min(int(top_k or 14), 40)),
        include_generated=False,
        min_trust=TrustLevel.LOW,
        permission_actor="system",
    )


def build_audit_evidence_query(
    topic: str,
    *,
    run_id: str = "",
    mission_id: str = "",
    top_k: int = 10,
    requesting_component: str = "audit",
) -> KnowledgeQuery:
    intent = extract_bounded_intent(topic)
    return KnowledgeQuery(
        query=intent,
        profile=RetrievalProfile.AUDIT_EVIDENCE,
        intent=RetrievalIntent.RETRIEVE_DECISION_HISTORY,
        requesting_component=requesting_component,
        mission_id=mission_id or "",
        run_id=run_id or "",
        max_results=max(1, min(int(top_k or 10), 40)),
        include_generated=False,
        min_trust=TrustLevel.MEDIUM,
        permission_actor="system",
    )


# --- Compatibility conversion ------------------------------------------------

def knowledge_response_to_legacy_hits(resp: KnowledgeResponse, *, query: str = "") -> dict:
    """Temporary adapter: KS → M18.2-like dict. Provenance preserved."""
    _inc("compat_adapter_usage")
    hits = []
    for r in resp.results or []:
        hits.append({
            "id": r.result_id,
            "path": r.path,
            "title": r.title,
            "snippet": r.excerpt,
            "score": r.final_score or r.native_score,
            "repository_id": r.repository_id,
            "source_id": r.source_id,
            "source_type": r.source_type,
            "evidence_class": r.evidence_class.value if hasattr(r.evidence_class, "value") else str(r.evidence_class),
            "is_generated": bool(r.is_generated),
            "provenance": dict(r.provenance or {}),
            "start_line": r.start_line,
            "end_line": r.end_line,
            "warnings": list(r.warnings or []),
            "content_fingerprint": r.content_fingerprint,
            "citation": (r.provenance or {}).get("citation") or r.path,
            "freshness": (r.provenance or {}).get("freshness") or "",
            "untrusted": True,
        })
    ctx = resp.context or {}
    truncated = bool(ctx.get("truncated")) if isinstance(ctx, dict) else False
    return {
        "ok": bool(resp.ok) and not resp.denied,
        "query": query or resp.query,
        "hits": hits,
        "mode": "unified_knowledge",
        "plan": resp.plan,
        "context": ctx,
        "context_safe": safe_context_for_consumer(ctx if isinstance(ctx, dict) else {}),
        "consulted_index": True,
        "legacy_compatible": True,
        "request_id": resp.request_id,
        "latency_ms": resp.latency_ms,
        "errors": list(resp.errors or []),
        "denied": bool(resp.denied),
        "error_category": resp.error_category or "",
        "truncated": truncated,
        "dedupe_meta": resp.dedupe_meta,
        "warnings": _collect_warnings(resp),
        "path_used": "unified",
    }


def _collect_warnings(resp: KnowledgeResponse) -> list[str]:
    w: list[str] = []
    if resp.errors:
        w.append(f"source_errors={len(resp.errors)}")
    ctx = resp.context or {}
    if isinstance(ctx, dict) and ctx.get("truncated"):
        w.append("context_truncated")
    for r in resp.results or []:
        for x in r.warnings or []:
            if x not in w:
                w.append(x)
    return w


# --- Fallback decision -------------------------------------------------------

def classify_unified_failure(resp: KnowledgeResponse | None, exc: BaseException | None = None) -> str:
    if exc is not None:
        name = type(exc).__name__.lower()
        if "timeout" in name:
            return "timeout"
        if "permission" in name or "denied" in name:
            return "permission_denied"
        return "exception"
    if resp is None:
        return "source_unavailable"
    if resp.denied or resp.error_category in FALLBACK_DENIED:
        cat = resp.error_category or "permission_denied"
        if cat in FALLBACK_DENIED:
            return cat
        return "permission_denied"
    if resp.error_category in FALLBACK_ALLOWED:
        return resp.error_category
    if not resp.ok:
        return resp.error_category or "source_unavailable"
    if not (resp.results or []):
        # empty is soft — caller may allow fallback
        return "empty_results"
    # partial: some source errors
    if resp.errors and resp.results:
        return "partial_below_threshold" if len(resp.results) < 1 else ""
    return ""


def fallback_permitted(category: str) -> bool:
    if not category:
        return False
    if category in FALLBACK_DENIED:
        return False
    return category in FALLBACK_ALLOWED


# --- Core adoption retrieve --------------------------------------------------

@dataclass
class AdoptionResult:
    """Caller-facing adoption result."""
    ok: bool
    path_used: str  # legacy | unified | fallback
    mode: str
    caller_id: str
    payload: dict  # legacy-compatible dict or structured package
    knowledge: KnowledgeResponse | None = None
    shadow: ShadowComparison | None = None
    fallback_reason: str = ""
    warnings: list[str] = field(default_factory=list)
    latency_ms: float = 0.0
    partial: bool = False
    denied: bool = False
    error_category: str = ""

    def to_dict(self) -> dict:
        d = {
            "ok": self.ok,
            "path_used": self.path_used,
            "mode": self.mode,
            "caller_id": self.caller_id,
            "fallback_reason": self.fallback_reason,
            "warnings": self.warnings,
            "latency_ms": round(self.latency_ms, 2),
            "partial": self.partial,
            "denied": self.denied,
            "error_category": self.error_category,
            "payload": self.payload,
        }
        if self.shadow is not None:
            d["shadow"] = self.shadow.to_dict()
        if self.knowledge is not None:
            d["request_id"] = self.knowledge.request_id
        return d


LegacyFn = Callable[..., dict]


def adopt_retrieve(
    *,
    caller_id: str,
    query: KnowledgeQuery,
    legacy_fn: LegacyFn | None,
    legacy_kwargs: dict | None = None,
    mode: RolloutMode | str | None = None,
    knowledge_service: KnowledgeService | None = None,
    saathi_root: str | Path | None = None,
    min_results_threshold: int = 1,
    return_legacy_shape: bool = True,
) -> AdoptionResult:
    """Canonical adoption entry: route by rollout mode with governed fallback."""
    t0 = time.time()
    resolved = resolve_mode(caller_id, explicit=mode)
    legacy_kwargs = dict(legacy_kwargs or {})
    _inc("calls_total")
    _inc_map("by_mode", resolved.value)
    _inc_map("by_caller", caller_id)

    _emit("knowledge.adoption.requested", {
        "caller_id": caller_id,
        "mode": resolved.value,
        "profile": query.profile.value,
        "mission_id": query.mission_id,
        "run_id": query.run_id,
        "max_results": query.resolved_top_k(),
    })
    _emit("knowledge.adoption.rollout_mode", {
        "caller_id": caller_id, "mode": resolved.value,
    })

    def _run_legacy() -> tuple[dict, float, str]:
        if legacy_fn is None:
            return {
                "ok": False, "hits": [], "error": "legacy_unavailable",
                "error_category": "source_unavailable",
            }, 0.0, "source_unavailable"
        lt0 = time.time()
        _emit("knowledge.adoption.legacy_started", {"caller_id": caller_id})
        try:
            out = legacy_fn(**legacy_kwargs) if not legacy_kwargs.get("__positional") else legacy_fn(
                *legacy_kwargs.get("__positional", ()),
                **{k: v for k, v in legacy_kwargs.items() if k != "__positional"},
            )
            if not isinstance(out, dict):
                out = {"ok": True, "hits": out}
        except Exception as e:
            out = {
                "ok": False, "hits": [], "error": type(e).__name__,
                "error_category": "exception",
            }
        ms = (time.time() - lt0) * 1000
        _emit("knowledge.adoption.legacy_completed", {
            "caller_id": caller_id,
            "ok": out.get("ok"),
            "hit_count": len(out.get("hits") or []),
            "latency_ms": round(ms, 2),
        })
        return out, ms, ""

    def _run_unified() -> tuple[KnowledgeResponse | None, float, str]:
        ks = knowledge_service or default_knowledge_service(
            saathi_root=saathi_root,
        ) if saathi_root is not None else (
            knowledge_service or default_knowledge_service()
        )
        ut0 = time.time()
        _emit("knowledge.adoption.unified_started", {
            "caller_id": caller_id, "profile": query.profile.value,
        })
        try:
            resp = ks.retrieve(query)
            ms = (time.time() - ut0) * 1000
            _emit("knowledge.adoption.unified_completed", {
                "caller_id": caller_id,
                "ok": resp.ok,
                "denied": resp.denied,
                "result_count": len(resp.results or []),
                "latency_ms": round(ms, 2),
                "errors": len(resp.errors or []),
            })
            return resp, ms, ""
        except Exception as e:
            ms = (time.time() - ut0) * 1000
            _emit("knowledge.adoption.unified_completed", {
                "caller_id": caller_id, "ok": False, "error": type(e).__name__,
                "latency_ms": round(ms, 2),
            })
            return None, ms, type(e).__name__

    # --- LEGACY only ---------------------------------------------------------
    if resolved == RolloutMode.LEGACY:
        _inc("legacy_only_calls")
        leg, lms, _ = _run_legacy()
        total = (time.time() - t0) * 1000
        _record_latency(total)
        if not (leg.get("hits") or []):
            _inc("no_result")
        return AdoptionResult(
            ok=bool(leg.get("ok", True)),
            path_used="legacy",
            mode=resolved.value,
            caller_id=caller_id,
            payload={**leg, "path_used": "legacy", "mode": resolved.value},
            latency_ms=total,
            partial=False,
            denied=bool(leg.get("denied")),
            error_category=str(leg.get("error_category") or ""),
        )

    # --- SHADOW: legacy authoritative ----------------------------------------
    if resolved == RolloutMode.SHADOW:
        leg, lms, _ = _run_legacy()
        uni, ums, uerr = _run_unified()
        shadow = compare_retrieval(
            legacy=leg, unified=uni, top_k=query.resolved_top_k(),
            legacy_latency_ms=lms, unified_latency_ms=ums,
        )
        if uerr:
            shadow.notes.append(f"unified_error:{uerr}")
        _inc("shadow_comparisons")
        if uni and uni.ok:
            _inc("unified_success")
        else:
            _inc("unified_fail")
        total = (time.time() - t0) * 1000
        _record_latency(total)
        _emit("knowledge.adoption.shadow_comparison", {
            "caller_id": caller_id,
            "top_k_overlap": shadow.top_k_overlap,
            "path_jaccard": shadow.path_jaccard,
            "legacy_count": shadow.legacy_count,
            "unified_count": shadow.unified_count,
        })
        payload = {
            **leg,
            "path_used": "legacy",
            "mode": resolved.value,
            "shadow": shadow.to_dict(),
            # KS must not affect behaviour — attach only
            "unified_shadow": {
                "ok": bool(uni and uni.ok),
                "request_id": uni.request_id if uni else "",
                "paths": [r.path for r in (uni.results if uni else [])[: query.resolved_top_k()]],
                "result_count": len(uni.results) if uni else 0,
            },
        }
        return AdoptionResult(
            ok=bool(leg.get("ok", True)),
            path_used="legacy",
            mode=resolved.value,
            caller_id=caller_id,
            payload=payload,
            knowledge=uni,
            shadow=shadow,
            latency_ms=total,
            denied=bool(leg.get("denied")),
            error_category=str(leg.get("error_category") or ""),
        )

    # --- UNIFIED paths -------------------------------------------------------
    uni, ums, uerr = _run_unified()
    fail_cat = classify_unified_failure(uni, None if uni is not None else Exception(uerr or "fail"))
    if uni is not None and uni.ok and (uni.results or []) and not uni.denied:
        fail_cat = ""
        # soft partial flag
        partial = bool(uni.errors)
        if partial:
            _inc("partial_result")
        _inc("unified_success")
        total = (time.time() - t0) * 1000
        _record_latency(total)
        if return_legacy_shape:
            payload = knowledge_response_to_legacy_hits(uni, query=query.query)
        else:
            payload = {
                "ok": True,
                "path_used": "unified",
                "mode": resolved.value,
                "knowledge": uni.to_dict(),
                "context_safe": safe_context_for_consumer(uni.context if isinstance(uni.context, dict) else {}),
            }
        payload["path_used"] = "unified"
        payload["mode"] = resolved.value
        _emit("knowledge.adoption.context_accepted", {
            "caller_id": caller_id, "path_used": "unified",
            "result_count": len(uni.results or []),
        })
        return AdoptionResult(
            ok=True,
            path_used="unified",
            mode=resolved.value,
            caller_id=caller_id,
            payload=payload,
            knowledge=uni,
            warnings=_collect_warnings(uni),
            latency_ms=total,
            partial=partial,
            denied=False,
        )

    # Unified failed or empty
    _inc("unified_fail")
    if uni and uni.denied:
        _inc("permission_denial")

    if resolved == RolloutMode.UNIFIED_ONLY:
        total = (time.time() - t0) * 1000
        _record_latency(total)
        cat = fail_cat or (uni.error_category if uni else "source_unavailable")
        if cat in FALLBACK_DENIED or (uni and uni.denied):
            _emit("knowledge.adoption.fallback_denied", {
                "caller_id": caller_id, "reason": cat,
            })
            _inc("fallback_denied_count")
        payload = {
            "ok": False,
            "hits": [],
            "path_used": "unified",
            "mode": resolved.value,
            "denied": bool(uni.denied) if uni else cat in FALLBACK_DENIED,
            "error_category": cat,
            "error": cat,
            "request_id": uni.request_id if uni else "",
            "errors": list(uni.errors) if uni else [],
        }
        if uni and not uni.denied and return_legacy_shape:
            # still map empty-ok responses
            payload = knowledge_response_to_legacy_hits(uni, query=query.query)
            payload["path_used"] = "unified"
            payload["mode"] = resolved.value
            if not uni.results:
                _inc("no_result")
                payload["ok"] = True  # empty success
        _emit("knowledge.adoption.context_rejected" if not payload.get("ok") else "knowledge.adoption.context_accepted", {
            "caller_id": caller_id, "path_used": "unified", "error_category": cat,
        })
        return AdoptionResult(
            ok=bool(payload.get("ok")),
            path_used="unified",
            mode=resolved.value,
            caller_id=caller_id,
            payload=payload,
            knowledge=uni,
            latency_ms=total,
            denied=bool(payload.get("denied")),
            error_category=cat,
        )

    # unified_with_fallback
    if not fallback_permitted(fail_cat):
        _inc("fallback_denied_count")
        _emit("knowledge.adoption.fallback_denied", {
            "caller_id": caller_id, "reason": fail_cat or "unknown",
        })
        total = (time.time() - t0) * 1000
        _record_latency(total)
        payload = {
            "ok": False,
            "hits": [],
            "path_used": "unified",
            "mode": resolved.value,
            "denied": True,
            "error_category": fail_cat or "permission_denied",
            "error": fail_cat or "permission_denied",
            "request_id": uni.request_id if uni else "",
        }
        return AdoptionResult(
            ok=False,
            path_used="unified",
            mode=resolved.value,
            caller_id=caller_id,
            payload=payload,
            knowledge=uni,
            latency_ms=total,
            denied=True,
            error_category=fail_cat or "permission_denied",
        )

    _inc("fallback_count")
    _emit("knowledge.adoption.fallback_invoked", {
        "caller_id": caller_id, "reason": fail_cat,
    })
    leg, lms, _ = _run_legacy()
    total = (time.time() - t0) * 1000
    _record_latency(total)
    # Prevent duplicate context: return only legacy payload
    payload = {
        **leg,
        "path_used": "fallback",
        "mode": resolved.value,
        "fallback_reason": fail_cat,
        "unified_error_category": fail_cat,
    }
    return AdoptionResult(
        ok=bool(leg.get("ok", True)),
        path_used="fallback",
        mode=resolved.value,
        caller_id=caller_id,
        payload=payload,
        knowledge=uni,
        fallback_reason=fail_cat,
        latency_ms=total,
        denied=bool(leg.get("denied")),
        error_category=str(leg.get("error_category") or fail_cat),
    )


# --- First-wave caller facades -----------------------------------------------

def adopted_codebase_search(
    query: str,
    *,
    project_root: str | Path | None = None,
    base_dir: Path | None = None,
    top_k: int = 10,
    path_filter: str = "",
    symbol_filter: str = "",
    documentation_only: bool = False,
    tests_only: bool = False,
    current_only: bool = True,
    historical: bool = False,
    namespace: str | None = None,
    mission_id: str = "",
    run_id: str = "",
    mode: RolloutMode | str | None = None,
    knowledge_service: KnowledgeService | None = None,
    caller_id: str = CALLER_CODEBASE_MEMORY_SEARCH,
    **legacy_extra: Any,
) -> dict:
    """First-wave: codebase memory search with optional KS routing."""
    from saathi.codebase_memory.retrieve import search as memory_search

    kq = build_code_search_query(
        query,
        caller_id=caller_id,
        documentation_only=documentation_only,
        tests_only=tests_only,
        symbol_filter=symbol_filter,
        path_filter=path_filter,
        top_k=top_k,
        mission_id=mission_id,
        run_id=run_id,
        project_root=project_root,
    )

    def _legacy(**_kw) -> dict:
        r = memory_search(
            query,
            project_root=project_root,
            base_dir=base_dir,
            top_k=top_k,
            path_filter=path_filter,
            symbol_filter=symbol_filter,
            documentation_only=documentation_only,
            tests_only=tests_only,
            current_only=current_only,
            historical=historical,
            namespace=namespace,
            **legacy_extra,
        )
        return r.to_dict() if hasattr(r, "to_dict") else dict(r)

    result = adopt_retrieve(
        caller_id=caller_id,
        query=kq,
        legacy_fn=_legacy,
        mode=mode,
        knowledge_service=knowledge_service,
        saathi_root=project_root,
        return_legacy_shape=True,
    )
    out = dict(result.payload)
    out.setdefault("adoption", {
        "caller_id": caller_id,
        "mode": result.mode,
        "path_used": result.path_used,
        "fallback_reason": result.fallback_reason,
        "latency_ms": result.latency_ms,
    })
    return out


def adopted_symbol_lookup(
    name: str,
    *,
    project_root: str | Path | None = None,
    base_dir: Path | None = None,
    top_k: int = 15,
    mode: RolloutMode | str | None = None,
    knowledge_service: KnowledgeService | None = None,
    **kwargs: Any,
) -> dict:
    return adopted_codebase_search(
        name,
        project_root=project_root,
        base_dir=base_dir,
        top_k=top_k,
        symbol_filter=name,
        mode=mode,
        knowledge_service=knowledge_service,
        caller_id=CALLER_CODEBASE_MEMORY_SYMBOL,
        **kwargs,
    )


def adopted_document_search(
    query: str,
    *,
    project_root: str | Path | None = None,
    base_dir: Path | None = None,
    top_k: int = 10,
    mode: RolloutMode | str | None = None,
    knowledge_service: KnowledgeService | None = None,
    **kwargs: Any,
) -> dict:
    return adopted_codebase_search(
        query,
        project_root=project_root,
        base_dir=base_dir,
        top_k=top_k,
        documentation_only=True,
        mode=mode,
        knowledge_service=knowledge_service,
        caller_id=CALLER_CODEBASE_MEMORY_DOCUMENT,
        **kwargs,
    )


def mission_context_prepare(
    objective: str,
    *,
    mission_id: str = "",
    run_id: str = "",
    project_root: str | Path | None = None,
    top_k: int = 14,
    mode: RolloutMode | str | None = None,
    knowledge_service: KnowledgeService | None = None,
) -> dict:
    """Mission preparation context via MISSION_CONTEXT profile.

    Default rollout is legacy (empty package without KS) unless mode opts in.
    Legacy for this facade is a no-op empty package (no prior mission KS path).
    """
    kq = build_mission_context_query(
        objective, mission_id=mission_id, run_id=run_id, top_k=top_k,
    )

    def _legacy_empty(**_kw) -> dict:
        return {
            "ok": True,
            "hits": [],
            "mode": "legacy_noop",
            "context": {
                "text": "",
                "char_count": 0,
                "budget": kq.resolved_budget(),
                "truncated": False,
                "included_result_ids": [],
                "excluded_reasons": [{"reason": "legacy_noop_mission_context"}],
                "fingerprint": "",
            },
            "note": "mission_context legacy is empty; enable shadow/unified to use KS",
        }

    result = adopt_retrieve(
        caller_id=CALLER_MISSION_CONTEXT,
        query=kq,
        legacy_fn=_legacy_empty,
        mode=mode,
        knowledge_service=knowledge_service,
        saathi_root=project_root,
        return_legacy_shape=True,
    )
    payload = dict(result.payload)
    # Ensure safe prompt wrapper present
    ctx = payload.get("context") or {}
    if isinstance(ctx, dict) and ctx.get("text"):
        payload["context_safe"] = safe_context_for_consumer(ctx)
        payload["prompt_block"] = wrap_retrieved_context(
            ctx.get("text") or "",
            fingerprint=str(ctx.get("fingerprint") or ""),
            truncated=bool(ctx.get("truncated")),
        )
    else:
        payload["context_safe"] = safe_context_for_consumer(ctx if isinstance(ctx, dict) else {})
        payload["prompt_block"] = ""
    payload["adoption"] = {
        "caller_id": CALLER_MISSION_CONTEXT,
        "mode": result.mode,
        "path_used": result.path_used,
        "mission_id": mission_id,
        "run_id": run_id,
    }
    # Priority note for consumers
    payload["assembly_priority"] = [
        "canonical_governance",
        "active_mission_objective",
        "exact_implementation",
        "relevant_tests",
        "architecture_docs",
        "milestone_decisions",
        "known_limitations",
        "supporting_memory",
        "lower_trust_generated",
    ]
    return payload


def audit_evidence_lookup(
    topic: str,
    *,
    run_id: str = "",
    mission_id: str = "",
    project_root: str | Path | None = None,
    top_k: int = 10,
    mode: RolloutMode | str | None = None,
    knowledge_service: KnowledgeService | None = None,
) -> dict:
    """Audit / milestone validation evidence via AUDIT_EVIDENCE profile."""
    kq = build_audit_evidence_query(
        topic, run_id=run_id, mission_id=mission_id, top_k=top_k,
    )

    def _legacy_empty(**_kw) -> dict:
        return {
            "ok": True,
            "hits": [],
            "mode": "legacy_noop",
            "context": {
                "text": "", "char_count": 0, "budget": kq.resolved_budget(),
                "truncated": False, "included_result_ids": [],
                "excluded_reasons": [{"reason": "legacy_noop_audit"}],
                "fingerprint": "",
            },
        }

    result = adopt_retrieve(
        caller_id=CALLER_AUDIT_EVIDENCE,
        query=kq,
        legacy_fn=_legacy_empty,
        mode=mode,
        knowledge_service=knowledge_service,
        saathi_root=project_root,
        return_legacy_shape=True,
    )
    payload = dict(result.payload)
    hits = payload.get("hits") or []
    primary = [
        h for h in hits
        if str(h.get("evidence_class") or "").startswith("primary")
        or h.get("evidence_class") in ("primary_code", "primary_tests")
    ]
    generated = [h for h in hits if h.get("is_generated")]
    payload["audit"] = {
        "primary_evidence_count": len(primary),
        "generated_count": len(generated),
        "missing_primary": len(primary) == 0 and len(hits) > 0,
        "provenance_required": True,
        "prefer_primary_code_and_tests": True,
        "generated_not_sufficient_alone": True,
    }
    if payload["audit"]["missing_primary"] and generated:
        payload.setdefault("warnings", []).append(
            "audit_generated_without_primary_evidence",
        )
    ctx = payload.get("context") or {}
    payload["context_safe"] = safe_context_for_consumer(ctx if isinstance(ctx, dict) else {})
    payload["adoption"] = {
        "caller_id": CALLER_AUDIT_EVIDENCE,
        "mode": result.mode,
        "path_used": result.path_used,
        "run_id": run_id,
    }
    return payload
