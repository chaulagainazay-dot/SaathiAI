"""Hybrid retrieval: path, symbol, lexical, optional local semantic, ranking."""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from saathi.codebase_memory.classify import CLASS_RANK_WEIGHT, FileClass
from saathi.codebase_memory.freshness import Freshness, verify_result
from saathi.codebase_memory.identity import RepoIdentity, resolve_identity
from saathi.codebase_memory.policy import default_limits
from saathi.codebase_memory.store import IndexStore, index_db_path, re_tokenize
from saathi.codebase_memory import events as cbm_events
from saathi.mcp_governance.namespace import NamespaceError, assert_namespace_bound, parse_namespace_query
from saathi.mcp_governance.redaction import contains_secret_like, redact_text


@dataclass
class RetrievalHit:
    result_id: str
    repository_id: str
    namespace: str
    branch: str
    commit_sha: str
    path: str
    symbol: str
    start_line: int
    end_line: int
    file_type: str
    snippet: str
    score: float
    ranking_signals: list[str] = field(default_factory=list)
    freshness: str = Freshness.UNKNOWN.value
    current_or_historical: str = "current"
    dirty_worktree: bool = False
    file_hash: str = ""
    citation: str = ""
    sensitivity: str = "internal"
    warnings: list[str] = field(default_factory=list)
    explanation: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RetrievalResult:
    ok: bool
    query: str
    hits: list[RetrievalHit] = field(default_factory=list)
    degraded: bool = False
    denied: bool = False
    error: str = ""
    error_category: str = ""
    mode: str = "lexical+symbol"
    latency_ms: float = 0.0
    namespace: str = ""
    identity: dict = field(default_factory=dict)
    consulted_index: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "query": self.query,
            "hits": [h.to_dict() for h in self.hits],
            "degraded": self.degraded,
            "denied": self.denied,
            "error": self.error,
            "error_category": self.error_category,
            "mode": self.mode,
            "latency_ms": round(self.latency_ms, 2),
            "namespace": self.namespace,
            "identity": self.identity,
            "consulted_index": self.consulted_index,
        }


_CANONICAL_NAMES = frozenset({
    "brain.md", "business.md", "writing and speaking style.md",
    "mcp_inventory.md", "external_capability_status.md",
    "autonomous_roadmap.md", "technical_debt.md",
    "capability_maturity_matrix.md",
})


def _optional_embed(texts: list[str]):
    try:
        from saathi.memory.engine.embeddings import LocalDeterministicEmbedder
        emb = LocalDeterministicEmbedder(dim=128)
        if emb.available():
            return emb.embed(texts)
    except Exception:
        return None
    return None


def _class_ok(
    cls: str,
    *,
    documentation_only: bool,
    tests_only: bool,
    file_type: str,
    include_generated: bool,
    include_vendored: bool,
) -> bool:
    if documentation_only and cls not in (
        "DOCUMENTATION", "ARCHITECTURE", "ROADMAP", "STYLE_GUIDE", "BUSINESS_CONTEXT",
    ):
        return False
    if tests_only and cls != "TEST_CODE":
        return False
    if file_type:
        ft = file_type.upper()
        if ft == "DOCUMENTATION" and cls not in (
            "DOCUMENTATION", "ARCHITECTURE", "ROADMAP", "STYLE_GUIDE", "BUSINESS_CONTEXT",
        ):
            return False
        if ft == "TESTS" and cls != "TEST_CODE":
            return False
        if ft == "SOURCE" and cls not in ("SOURCE_CODE", "TEST_CODE"):
            return False
        if ft == "ARCHITECTURE" and cls not in ("ARCHITECTURE", "DOCUMENTATION"):
            return False
    if not include_generated and cls == "GENERATED":
        return False
    if not include_vendored and cls == "VENDORED":
        return False
    return True


def search(
    query: str,
    *,
    project_root: str | Path | None = None,
    namespace: str | None = None,
    identity: RepoIdentity | None = None,
    store: IndexStore | None = None,
    top_k: int = 10,
    path_filter: str = "",
    symbol_filter: str = "",
    file_type: str = "",
    current_only: bool = True,
    historical: bool = False,
    documentation_only: bool = False,
    tests_only: bool = False,
    include_generated: bool = False,
    include_vendored: bool = False,
    explain: bool = True,
    base_dir: Path | None = None,
) -> RetrievalResult:
    t0 = time.time()
    limits = default_limits()
    top_k = max(1, min(int(top_k), limits.max_query_results))

    if not (query or "").strip():
        return RetrievalResult(
            ok=False, query=query or "", error="empty_query",
            error_category="validation", latency_ms=0,
        )

    try:
        ident = identity or resolve_identity(project_root)
    except NamespaceError as e:
        cbm_events.emit("query_denied", {"reason": str(e)})
        return RetrievalResult(
            ok=False, query=query, error=str(e), error_category="namespace",
            denied=True, latency_ms=(time.time() - t0) * 1000,
        )
    except Exception as e:
        return RetrievalResult(
            ok=False, query=query, error=str(e)[:200], error_category="identity",
            denied=True, latency_ms=(time.time() - t0) * 1000,
        )

    try:
        ns = parse_namespace_query(namespace or ident.project_namespace)
        assert_namespace_bound(ns, bound_ns=ident.project_namespace)
    except NamespaceError as e:
        cbm_events.emit("namespace_mismatch", {"error": str(e)})
        return RetrievalResult(
            ok=False, query=query, error=str(e), error_category="namespace_violation",
            denied=True, namespace=ident.project_namespace, identity=ident.to_dict(),
            latency_ms=(time.time() - t0) * 1000,
        )

    qs = query.strip()
    if qs.startswith("~") or qs.startswith("/Users/") or qs.startswith("/home/"):
        return RetrievalResult(
            ok=False, query=query, error="home_or_absolute_path_query_denied",
            error_category="policy", denied=True,
            latency_ms=(time.time() - t0) * 1000,
        )

    owns = store is None
    st = None
    try:
        st = store or IndexStore(index_db_path(ident, base=base_dir))
        counts = st.counts()
        if counts["chunks"] == 0:
            return RetrievalResult(
                ok=True, query=query, hits=[], degraded=True,
                error="index_empty", error_category="empty", mode="none",
                namespace=ns, identity=ident.to_dict(), consulted_index=True,
                latency_ms=(time.time() - t0) * 1000,
            )

        q_lower = query.lower()
        tokens = re_tokenize(query)
        scored: dict[str, dict] = {}

        def add(row: dict, base: float, signal: str) -> None:
            cid = row["chunk_id"]
            ent = scored.setdefault(cid, {"row": row, "score": 0.0, "signals": []})
            ent["score"] += base
            if signal not in ent["signals"]:
                ent["signals"].append(signal)

        # Preload symbol names for boost
        sym_paths: set[tuple[str, str]] = set()
        for t in tokens:
            for srow in st.find_symbol(t, limit=30):
                sym_paths.add((srow.get("path") or "", srow.get("name") or ""))

        for row in st.all_chunks(limit=50_000):
            path = row.get("path") or ""
            if path_filter and path_filter not in path:
                continue
            if symbol_filter and symbol_filter.lower() not in (row.get("symbol") or "").lower():
                continue
            cls = row.get("classification") or ""
            if not _class_ok(
                cls,
                documentation_only=documentation_only,
                tests_only=tests_only,
                file_type=file_type,
                include_generated=include_generated,
                include_vendored=include_vendored,
            ):
                continue

            fname = path.rsplit("/", 1)[-1].lower()
            if q_lower in path.lower() or path.lower().endswith(q_lower):
                add(row, 12.0, "exact_path")
            for t in tokens:
                if t in fname:
                    add(row, 6.0, "filename")

            sym = (row.get("symbol") or "").lower()
            for t in tokens:
                if t == sym:
                    add(row, 15.0, "exact_symbol")
                elif t and t in sym:
                    add(row, 8.0, "symbol_partial")

            body = (row.get("text") or "").lower()
            hit_n = sum(1 for t in tokens if t in body)
            if hit_n:
                add(row, 2.0 * hit_n + (3.0 if tokens and hit_n == len(tokens) else 0), "lexical")

            if (path, row.get("symbol") or "") in sym_paths or any(
                p == path for p, _ in sym_paths
            ):
                if any(n.lower() in tokens or n.lower() == sym for _, n in sym_paths if n):
                    add(row, 10.0, "symbol_index")

            if row["chunk_id"] not in scored:
                continue

            try:
                w = CLASS_RANK_WEIGHT.get(FileClass(cls), 0.5)
            except Exception:
                w = 0.5
            # Prefer implementation over tests for "where is defined" style questions
            q_def = any(x in q_lower for x in ("defined", "definition", "entry point", "where is"))
            if q_def and cls == "SOURCE_CODE":
                w = max(w, 1.2)
            if q_def and cls == "TEST_CODE":
                w = min(w, 0.7)
            scored[row["chunk_id"]]["score"] *= (0.75 + 0.25 * w)

            if fname in _CANONICAL_NAMES:
                scored[row["chunk_id"]]["score"] += 4.0
                if "canonical_doc" not in scored[row["chunk_id"]]["signals"]:
                    scored[row["chunk_id"]]["signals"].append("canonical_doc")

            if row.get("commit_sha") == ident.commit_sha:
                scored[row["chunk_id"]]["score"] += 1.5
                if "current_commit" not in scored[row["chunk_id"]]["signals"]:
                    scored[row["chunk_id"]]["signals"].append("current_commit")

        mode = "lexical+symbol"
        cand = sorted(scored.values(), key=lambda x: -x["score"])[: max(top_k * 4, 24)]
        emb = _optional_embed([query] + [(c["row"].get("text") or "")[:800] for c in cand])
        if emb and len(emb.vectors) == len(cand) + 1:
            mode = "lexical+symbol+local_embed"
            import numpy as np
            qv = emb.vectors[0]
            for i, c in enumerate(cand):
                sim = float(np.dot(qv, emb.vectors[i + 1]))
                c["score"] += max(0.0, sim) * 5.0
                c["signals"].append(f"semantic:{sim:.2f}")

        ranked = sorted(cand, key=lambda x: -x["score"])
        hits: list[RetrievalHit] = []
        root = Path(ident.repository_root)
        for ent in ranked:
            if len(hits) >= top_k:
                break
            row = ent["row"]
            if ent["score"] <= 0:
                continue
            fres = verify_result(
                root=root,
                path=row["path"],
                indexed_hash=row.get("file_hash") or "",
                indexed_commit=row.get("commit_sha") or "",
                identity=ident,
                historical=historical,
            )
            freshness = fres["freshness"]
            warnings: list[str] = []
            if fres.get("warning"):
                warnings.append(str(fres["warning"]))
            score = float(ent["score"])
            if current_only and not historical and freshness in (
                Freshness.STALE_INDEX.value,
                Freshness.DELETED_SOURCE.value,
                Freshness.HISTORICAL.value,
                Freshness.UNKNOWN.value,
            ):
                warnings.append(f"not_current:{freshness}")
                score *= 0.4
                if freshness == Freshness.DELETED_SOURCE.value:
                    continue

            signals = list(ent["signals"])
            snippet = (row.get("text") or "")[:400]
            if contains_secret_like(snippet):
                snippet = redact_text(snippet, max_len=200)
                warnings.append("snippet_redacted")

            hits.append(RetrievalHit(
                result_id=row["chunk_id"],
                repository_id=ident.repository_id,
                namespace=ns,
                branch=row.get("branch") or ident.branch,
                commit_sha=row.get("commit_sha") or "",
                path=row["path"],
                symbol=row.get("symbol") or "",
                start_line=int(row.get("start_line") or 0),
                end_line=int(row.get("end_line") or 0),
                file_type=row.get("classification") or "",
                snippet=snippet,
                score=round(score, 4),
                ranking_signals=signals[:12],
                freshness=freshness,
                current_or_historical="historical" if historical else "current",
                dirty_worktree=bool(row.get("dirty") or ident.dirty_worktree),
                file_hash=(row.get("file_hash") or "")[:16],
                citation=f"{row['path']}:{row.get('start_line', 0)}-{row.get('end_line', 0)}",
                sensitivity=row.get("sensitivity") or "internal",
                warnings=warnings,
                explanation=_explain(signals, freshness) if explain else "",
            ))

        hits.sort(key=lambda h: -h.score)
        hits = hits[:top_k]
        cbm_events.emit("query_completed", {
            "hit_count": len(hits), "mode": mode, "namespace": ns,
        })
        return RetrievalResult(
            ok=True, query=query, hits=hits, mode=mode, namespace=ns,
            identity=ident.to_dict(), consulted_index=True,
            latency_ms=(time.time() - t0) * 1000,
        )
    except Exception as e:
        cbm_events.emit("query_degraded", {"error": type(e).__name__})
        return RetrievalResult(
            ok=False, query=query, error=str(e)[:200], error_category="query_error",
            degraded=True, namespace=ns, identity=ident.to_dict(),
            latency_ms=(time.time() - t0) * 1000,
        )
    finally:
        if owns and st is not None:
            try:
                st.close()
            except Exception:
                pass


def _explain(signals: list[str], freshness: str) -> str:
    parts = []
    if "exact_symbol" in signals:
        parts.append("Matched exact symbol name.")
    elif "symbol_index" in signals or "symbol_partial" in signals:
        parts.append("Matched symbol index.")
    if "exact_path" in signals or "filename" in signals:
        parts.append("Matched path/filename.")
    if "canonical_doc" in signals:
        parts.append("Architecture/canonical document prioritized.")
    if "current_commit" in signals:
        parts.append("Current branch/commit.")
    if any(s.startswith("semantic") for s in signals):
        parts.append("Local semantic similarity.")
    if "lexical" in signals:
        parts.append("Keyword/lexical overlap.")
    if freshness == Freshness.STALE_INDEX.value:
        parts.append("Warning: index may be stale — verify live file.")
    if freshness == Freshness.DELETED_SOURCE.value:
        parts.append("Warning: source deleted.")
    return " ".join(parts)[:300]
