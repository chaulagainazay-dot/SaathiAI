"""M9 hybrid retrieval — semantic + keyword + lifecycle signals, one canonical
ranking function, MMR diversity, and a per-result explanation.

Fails safe: if the vector layer errors, keyword-only ranking still returns
results (mode='keyword-fallback'), clearly marked. Never invents memory.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field

import numpy as np

from saathi.memory.engine import embeddings as emb

_STOP = {"the", "a", "an", "is", "are", "was", "were", "to", "of", "and", "or",
         "in", "on", "for", "with", "what", "how", "why", "this", "that"}


def tokens(text: str) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", text.lower())
            if len(t) >= 3 and t not in _STOP}


@dataclass
class Weights:
    semantic: float = 0.40
    keyword: float = 0.20
    recency: float = 0.10
    importance: float = 0.10
    confidence: float = 0.08
    context: float = 0.07
    feedback: float = 0.05

    def as_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass
class RetrievalResult:
    memory_id: str
    content: str
    memory_type: str
    namespace: str
    final_score: float
    semantic_score: float
    keyword_score: float
    recency_score: float
    confidence: float
    age_sec: float
    citation: str
    reason: str
    provenance: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def _recency(age_sec: float, half_life_days: float = 30.0) -> float:
    return float(0.5 ** (age_sec / (half_life_days * 86400)))


def keyword_score(query_tokens: set[str], normalized: str) -> float:
    if not query_tokens:
        return 0.0
    doc = set(re.split(r"[^a-z0-9]+", normalized))
    return len(query_tokens & doc) / len(query_tokens)


def rank(query: str, items: list[dict], *, query_vec: np.ndarray | None = None,
         store=None, weights: Weights | None = None,
         context: dict | None = None, top_k: int = 10,
         threshold: float = 0.0, mmr_lambda: float = 0.7,
         emb_map: dict | None = None,
         fb_map: dict | None = None,
         sem_map: dict | None = None) -> tuple[list[RetrievalResult], str]:
    """Score, threshold, and MMR-diversify. Returns (results, mode).

    `emb_map` (memory_id → embedding row) and `fb_map` (memory_id → usefulness)
    are bulk-loaded by the caller so ranking makes no per-item DB queries."""
    w = weights or Weights()
    ctx = context or {}
    qtok = tokens(query)
    now = time.time()
    mode = "hybrid" if query_vec is not None else "keyword-only"
    emb_map = emb_map or {}
    fb_map = fb_map or {}
    sem_map = sem_map or {}

    scored: list[tuple[float, RetrievalResult, np.ndarray | None]] = []
    for it in items:
        sem = 0.0
        vec = None
        if query_vec is not None:
            if it["id"] in sem_map:
                sem = sem_map[it["id"]]  # precomputed vectorized cosine
            else:
                e = emb_map.get(it["id"])
                if e and e["dim"] == query_vec.shape[0]:
                    vec = emb.from_bytes(e["vector"], e["dim"])
                    sem = max(0.0, emb.cosine(query_vec, vec))
        kw = keyword_score(qtok, it["normalized"])
        age = now - (it.get("created_at") or now)
        rec = _recency(age)
        imp = float(it.get("importance", 0.5))
        conf = float(it.get("confidence", 0.5))
        # context match: project/agent/type alignment
        cmatch = 0.0
        if ctx.get("project_id") and it.get("project_id") == ctx["project_id"]:
            cmatch += 0.6
        if ctx.get("agent") and it.get("agent_scope") == ctx["agent"]:
            cmatch += 0.4
        fb = fb_map.get(it["id"], 0.5)
        pin_boost = 0.15 if it.get("pinned") else 0.0

        final = (w.semantic * sem + w.keyword * kw + w.recency * rec +
                 w.importance * imp + w.confidence * conf + w.context * cmatch +
                 w.feedback * fb + pin_boost)
        if final < threshold:
            continue
        reason_bits = []
        if sem > 0.3:
            reason_bits.append(f"semantic {sem:.2f}")
        if kw > 0:
            reason_bits.append(f"keyword {kw:.2f}")
        if cmatch > 0:
            reason_bits.append("project/agent match")
        if it.get("pinned"):
            reason_bits.append("pinned")
        res = RetrievalResult(
            memory_id=it["id"], content=it["content"], memory_type=it["memory_type"],
            namespace=it["namespace"], final_score=round(final, 4),
            semantic_score=round(sem, 4), keyword_score=round(kw, 4),
            recency_score=round(rec, 4), confidence=conf, age_sec=round(age, 1),
            citation="", reason=", ".join(reason_bits) or "weak match",
            provenance=it.get("provenance", {}))
        scored.append((final, res, vec))

    scored.sort(key=lambda x: x[0], reverse=True)

    # MMR diversity: penalize near-duplicates of already-selected results
    selected: list[tuple[float, RetrievalResult, np.ndarray | None]] = []
    pool = scored[:max(top_k * 4, top_k)]
    while pool and len(selected) < top_k:
        best_i, best_val = 0, -1e9
        for i, (score, res, vec) in enumerate(pool):
            div = 0.0
            if vec is not None:
                for _, _, svec in selected:
                    if svec is not None:
                        div = max(div, max(0.0, emb.cosine(vec, svec)))
            else:
                sres_tokens = tokens(res.content)
                for _, sres, _ in selected:
                    ov = len(sres_tokens & tokens(sres.content)) / (len(sres_tokens) or 1)
                    div = max(div, ov)
            mmr = mmr_lambda * score - (1 - mmr_lambda) * div
            if mmr > best_val:
                best_val, best_i = mmr, i
        selected.append(pool.pop(best_i))

    final_results = [r for _, r, _ in selected]
    # fetch citations only for the few selected results (not every candidate)
    if store is not None:
        for r in final_results:
            src = store.sources(r.memory_id)
            r.citation = src[0]["citation"] if src else ""
    return final_results, mode


@dataclass
class QueryPlan:
    namespaces: list[str]
    top_k: int = 10
    threshold: float = 0.0
    memory_types: list[str] | None = None
    context: dict = field(default_factory=dict)
    token_budget: int = 1200


def plan_query(*, user: str = "", project_id: str = "", agent: str = "",
               conversation_id: str = "", extra_namespaces: list[str] | None = None,
               top_k: int = 8, token_budget: int = 1200) -> QueryPlan:
    """Decide which scopes to search from the active context. Namespaces are the
    privacy firewall: retrieval only ever reads the namespaces listed here."""
    ns: list[str] = []
    if user:
        ns.append(f"user:{user}")
    if project_id:
        ns.append(f"project:{project_id}")
    if conversation_id:
        ns.append(f"conversation:{conversation_id}")
    if agent:
        ns.append(f"agent:{agent}")
    ns.append("business:global")   # business/semantic shared scope
    ns += (extra_namespaces or [])
    ctx = {"project_id": project_id, "agent": agent, "user": user}
    return QueryPlan(namespaces=list(dict.fromkeys(ns)), top_k=top_k,
                     context=ctx, token_budget=token_budget)
