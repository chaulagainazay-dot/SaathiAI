"""Lexical knowledge retrieval with authority and freshness ranking."""
from __future__ import annotations

import time
from typing import Any

from .index import KnowledgeIndex
from .models import (
    DEFAULT_TOP_K,
    MAX_RETRIEVAL_TOP_K,
    FreshnessStatus,
    KnowledgeChunk,
    RetrievedChunk,
    SourceAuthority,
    authority_rank,
    tokenize,
)


class KnowledgeRetriever:
    """Bounded lexical retriever. Semantic retrieval is not implemented."""

    def __init__(self, index: KnowledgeIndex):
        self.index = index
        self.last_latency_ms = 0.0

    def search(
        self,
        query: str,
        *,
        top_k: int = DEFAULT_TOP_K,
        tenant_id: str = "platform",
        workspace_id: str = "",
        authority_min: str = "",
        source_types: list[str] | None = None,
        require_fresh: bool = False,
        expand_adjacent: bool = True,
        allow_restricted: bool = False,
    ) -> list[RetrievedChunk]:
        t0 = time.time()
        q = (query or "").strip()
        if not q:
            self.last_latency_ms = 0.0
            return []
        k = max(1, min(int(top_k or DEFAULT_TOP_K), MAX_RETRIEVAL_TOP_K))
        tokens = tokenize(q)
        if not tokens:
            self.last_latency_ms = (time.time() - t0) * 1000
            return []

        min_rank = authority_rank(authority_min) if authority_min else 0
        type_set = set(source_types or [])
        candidates: list[RetrievedChunk] = []
        seen_text_hashes: set[str] = set()

        for chunk in self.index.all_live_chunks():
            if not self._tenant_ok(chunk, tenant_id, workspace_id):
                continue
            if chunk.sensitivity == "secret":
                continue
            if chunk.sensitivity == "restricted" and not allow_restricted:
                continue
            if min_rank and authority_rank(chunk.authority) < min_rank:
                continue
            if type_set and chunk.source_type not in type_set:
                continue
            if require_fresh and chunk.freshness in {
                FreshnessStatus.STALE.value,
                FreshnessStatus.EXPIRED.value,
            }:
                continue
            if chunk.content_hash in seen_text_hashes:
                continue

            score, reasons = self._score(chunk, tokens, q.lower())
            if score <= 0:
                continue
            candidates.append(
                RetrievedChunk(chunk=chunk, score=score, rank_reasons=reasons)
            )
            seen_text_hashes.add(chunk.content_hash)

        candidates.sort(
            key=lambda r: (
                -r.score,
                -authority_rank(r.chunk.authority),
                r.chunk.relative_path,
                r.chunk.ordinal,
            )
        )
        top = candidates[:k]

        if expand_adjacent and top:
            top = self._expand_adjacent(top, k)

        # Suppress near-duplicates after expansion
        final: list[RetrievedChunk] = []
        seen_ids: set[str] = set()
        seen_hashes: set[str] = set()
        for item in top:
            if item.chunk.chunk_id in seen_ids:
                continue
            if item.chunk.content_hash in seen_hashes:
                continue
            seen_ids.add(item.chunk.chunk_id)
            seen_hashes.add(item.chunk.content_hash)
            final.append(item)
            if len(final) >= k:
                break

        self.last_latency_ms = (time.time() - t0) * 1000
        return final

    def _tenant_ok(
        self, chunk: KnowledgeChunk, tenant_id: str, workspace_id: str
    ) -> bool:
        # Platform-wide knowledge is available to all authenticated tenants after RBAC.
        if chunk.tenant_id in {"platform", "*", ""}:
            return True
        if chunk.tenant_id != tenant_id:
            return False
        if chunk.workspace_scope in {"*", "", None}:
            return True
        if not workspace_id:
            return False
        return chunk.workspace_scope == workspace_id

    def _score(
        self, chunk: KnowledgeChunk, tokens: list[str], query_lower: str
    ) -> tuple[float, list[str]]:
        text_low = (chunk.text or "").lower()
        title_low = (chunk.title or "").lower()
        path_low = (chunk.relative_path or "").lower()
        score = 0.0
        reasons: list[str] = []
        matched = 0
        for tok in tokens:
            if tok in text_low:
                c = text_low.count(tok)
                score += 2.0 + min(c, 5) * 0.15
                matched += 1
            if tok in title_low:
                score += 4.0
                reasons.append(f"title:{tok}")
            if tok in path_low:
                score += 2.5
                reasons.append(f"path:{tok}")
        if matched == 0:
            return 0.0, []
        # Phrase bonus
        if len(query_lower) >= 6 and query_lower in text_low:
            score += 6.0
            reasons.append("phrase_match")
        # Authority boost
        ar = authority_rank(chunk.authority)
        score += ar / 20.0
        reasons.append(f"authority:{chunk.authority}")
        # Freshness
        if chunk.freshness == FreshnessStatus.FRESH.value:
            score += 1.5
            reasons.append("fresh")
        elif chunk.freshness == FreshnessStatus.STALE.value:
            score -= 1.0
            reasons.append("stale_penalty")
        # Prefer runtime state for "current" questions
        if any(w in query_lower for w in ("current", "now", "latest", "active", "blocked")):
            if chunk.authority == SourceAuthority.AUTHORITATIVE_RUNTIME.value:
                score += 5.0
                reasons.append("runtime_current_boost")
            if "loop_state" in path_low or "current_goal" in path_low:
                score += 3.0
                reasons.append("current_state_file")
        if "production" in query_lower or "authorized" in query_lower:
            if "cert" in path_low or "evidence" in path_low or "capability" in path_low:
                score += 2.0
                reasons.append("authz_evidence_boost")
        if "voice" in query_lower and "voice" in path_low:
            score += 2.0
        if "ielts" in query_lower and "ielts" in (text_low + path_low):
            score += 2.0
        if "hcg" in query_lower and "hcg" in (text_low + path_low):
            score += 2.0
        coverage = matched / max(1, len(tokens))
        score *= 0.6 + 0.4 * coverage
        return score, reasons

    def _expand_adjacent(
        self, hits: list[RetrievedChunk], k: int
    ) -> list[RetrievedChunk]:
        expanded: list[RetrievedChunk] = []
        seen: set[str] = set()
        for hit in hits:
            for adj in self.index.get_adjacent(hit.chunk, radius=1):
                if adj.chunk_id in seen:
                    continue
                seen.add(adj.chunk_id)
                if adj.chunk_id == hit.chunk.chunk_id:
                    expanded.append(hit)
                else:
                    expanded.append(
                        RetrievedChunk(
                            chunk=adj,
                            score=hit.score * 0.55,
                            rank_reasons=hit.rank_reasons + ["adjacent"],
                            adjacent_expanded=True,
                        )
                    )
            if len(expanded) >= k * 2:
                break
        expanded.sort(key=lambda r: (-r.score, r.chunk.ordinal))
        return expanded[: max(k, min(len(expanded), k + 2))]
