"""M19.1 — Deterministic shadow comparison (no ungoverned LLM scoring)."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Iterable


@dataclass
class ShadowComparison:
    """Structured comparison between legacy and unified retrieval."""
    ok: bool = True
    top_k: int = 0
    legacy_paths: list[str] = field(default_factory=list)
    unified_paths: list[str] = field(default_factory=list)
    source_overlap: float = 0.0
    top_k_overlap: float = 0.0
    path_jaccard: float = 0.0
    legacy_only_paths: list[str] = field(default_factory=list)
    unified_only_paths: list[str] = field(default_factory=list)
    legacy_count: int = 0
    unified_count: int = 0
    legacy_latency_ms: float = 0.0
    unified_latency_ms: float = 0.0
    legacy_ok: bool = True
    unified_ok: bool = True
    legacy_error: str = ""
    unified_error: str = ""
    primary_evidence_ratio_unified: float = 0.0
    duplicate_rate_unified: float = 0.0
    truncated_unified: bool = False
    context_chars_unified: int = 0
    permission_denied_unified: bool = False
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _norm_path(p: str) -> str:
    return (p or "").strip().replace("\\", "/").lstrip("./")


def _paths_from_legacy(legacy: dict | None) -> list[str]:
    if not legacy:
        return []
    hits = legacy.get("hits") or []
    out: list[str] = []
    for h in hits:
        if isinstance(h, dict):
            p = h.get("path") or h.get("citation") or ""
        else:
            p = getattr(h, "path", "") or ""
        p = _norm_path(str(p))
        if p:
            out.append(p)
    return out


def _paths_from_unified(unified: Any) -> list[str]:
    if unified is None:
        return []
    results = getattr(unified, "results", None)
    if results is None and isinstance(unified, dict):
        results = unified.get("results") or []
    out: list[str] = []
    for r in results or []:
        if isinstance(r, dict):
            p = r.get("path") or ""
        else:
            p = getattr(r, "path", "") or ""
        p = _norm_path(str(p))
        if p:
            out.append(p)
    return out


def _jaccard(a: Iterable[str], b: Iterable[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa and not sb:
        return 1.0
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def _overlap_at_k(a: list[str], b: list[str], k: int) -> float:
    if k <= 0:
        return 0.0
    sa, sb = set(a[:k]), set(b[:k])
    if not sa and not sb:
        return 1.0
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / max(len(sa), len(sb))


def compare_retrieval(
    *,
    legacy: dict | None,
    unified: Any,
    top_k: int = 10,
    legacy_latency_ms: float = 0.0,
    unified_latency_ms: float = 0.0,
) -> ShadowComparison:
    """Compare legacy dict (M18.2 shape) vs KnowledgeResponse / dict."""
    leg_paths = _paths_from_legacy(legacy)
    uni_paths = _paths_from_unified(unified)

    leg_ok = True if legacy is None else bool(legacy.get("ok", True))
    leg_err = "" if legacy is None else str(legacy.get("error") or legacy.get("error_category") or "")

    uni_ok = True
    uni_err = ""
    denied = False
    truncated = False
    ctx_chars = 0
    primary_ratio = 0.0
    dup_rate = 0.0

    if unified is not None:
        if hasattr(unified, "ok"):
            uni_ok = bool(unified.ok)
            uni_err = str(getattr(unified, "error_category", "") or "")
            denied = bool(getattr(unified, "denied", False))
            ctx = getattr(unified, "context", None) or {}
            if isinstance(ctx, dict):
                truncated = bool(ctx.get("truncated"))
                ctx_chars = int(ctx.get("char_count") or 0)
            results = getattr(unified, "results", None) or []
            if results:
                primary = 0
                for r in results:
                    ec = getattr(r, "evidence_class", None)
                    val = ec.value if hasattr(ec, "value") else str(ec or "")
                    if "primary" in val or val in ("primary_code", "primary_tests"):
                        primary += 1
                primary_ratio = primary / len(results)
            meta = getattr(unified, "dedupe_meta", None) or {}
            if isinstance(meta, dict) and meta.get("before") and meta.get("after") is not None:
                before = int(meta.get("before") or 0)
                after = int(meta.get("after") or 0)
                if before > 0:
                    dup_rate = max(0.0, (before - after) / before)
        elif isinstance(unified, dict):
            uni_ok = bool(unified.get("ok", True))
            uni_err = str(unified.get("error_category") or unified.get("error") or "")
            denied = bool(unified.get("denied"))
            ctx = unified.get("context") or {}
            if isinstance(ctx, dict):
                truncated = bool(ctx.get("truncated"))
                ctx_chars = int(ctx.get("char_count") or 0)

    k = max(1, int(top_k or 10))
    leg_only = [p for p in leg_paths if p not in set(uni_paths)]
    uni_only = [p for p in uni_paths if p not in set(leg_paths)]

    return ShadowComparison(
        ok=True,
        top_k=k,
        legacy_paths=leg_paths[:k],
        unified_paths=uni_paths[:k],
        source_overlap=_jaccard(leg_paths, uni_paths),
        top_k_overlap=_overlap_at_k(leg_paths, uni_paths, k),
        path_jaccard=_jaccard(leg_paths[:k], uni_paths[:k]),
        legacy_only_paths=leg_only[:k],
        unified_only_paths=uni_only[:k],
        legacy_count=len(leg_paths),
        unified_count=len(uni_paths),
        legacy_latency_ms=round(legacy_latency_ms, 2),
        unified_latency_ms=round(unified_latency_ms, 2),
        legacy_ok=leg_ok,
        unified_ok=uni_ok,
        legacy_error=leg_err[:80],
        unified_error=uni_err[:80],
        primary_evidence_ratio_unified=round(primary_ratio, 3),
        duplicate_rate_unified=round(dup_rate, 3),
        truncated_unified=truncated,
        context_chars_unified=ctx_chars,
        permission_denied_unified=denied,
        notes=[],
    )
