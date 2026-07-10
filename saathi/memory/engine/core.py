"""M9 MemoryEngine — the unified facade over store + embeddings + retrieval.

Lifecycle: observe → extract → classify → validate → store → embed → link →
retrieve → rank → use → reinforce → decay → archive/forget.

Privacy: every read is scoped to an allowed namespace list; a memory outside
those namespaces is never returned and the denial is logged. Deleted
(tombstoned) memories drop their embedding and are excluded from all reads.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Optional

from saathi.memory.engine import embeddings as emb
from saathi.memory.engine import retrieval as ret
from saathi.memory.engine.schema import MemoryStore, normalize, MEMORY_TYPES

# Reuse the platform memory retention semantics (audit: REUSE).
try:
    from saathi.memory.platform import RetentionPolicy, retention_expiry
except Exception:  # pragma: no cover - platform always present
    RetentionPolicy = None
    retention_expiry = None

RELATIONS = {"belongs_to", "mentions", "depends_on", "contradicts", "supersedes",
             "supports", "derived_from", "related_to", "created_by", "used_by",
             "part_of", "blocks", "completed_by"}


@dataclass
class ExtractionCandidate:
    content: str
    memory_type: str        # or "discard" / "working"
    confidence: float
    importance: float
    reason: str


# ── deterministic extraction (Phase 7) ─────────────────────────────────────
# Rule-based, testable, no LLM required. LLM-assisted extraction (optional) must
# route through ExecutionGateway; the deterministic path is the default.
_PREF = re.compile(r"\b(i (prefer|like|want|always|never)|please always|from now on)\b", re.I)
_DECISION = re.compile(r"\b(we (decided|will|chose|agreed)|let's|decision:|going with)\b", re.I)
_RULE = re.compile(r"\b(must|should|policy|rule|always|never|target is|budget is)\b", re.I)
_PROC = re.compile(r"\b(step \d|first,|then,|to (deploy|publish|build|run)|procedure)\b", re.I)
_FACT = re.compile(r"\b(is|are|uses|built with|located|consists of|architecture)\b", re.I)
_TASK = re.compile(r"\b(todo|to-do|need to|remember to|follow up|unresolved|pending)\b", re.I)


def extract_candidates(text: str) -> list[ExtractionCandidate]:
    """Bounded, deterministic extraction. Most chatter → discard/working."""
    t = text.strip()
    if len(t) < 12:
        return [ExtractionCandidate(t, "discard", 0.0, 0.0, "too short")]
    out: list[ExtractionCandidate] = []
    if _PREF.search(t):
        out.append(ExtractionCandidate(t, "user", 0.75, 0.7, "stated preference"))
    if _DECISION.search(t):
        out.append(ExtractionCandidate(t, "conversation", 0.7, 0.75, "explicit decision"))
    if _RULE.search(t):
        out.append(ExtractionCandidate(t, "business", 0.65, 0.8, "business rule"))
    if _PROC.search(t):
        out.append(ExtractionCandidate(t, "procedural", 0.6, 0.6, "procedure"))
    if _TASK.search(t):
        out.append(ExtractionCandidate(t, "conversation", 0.6, 0.65, "unresolved task"))
    if not out and _FACT.search(t) and len(t) < 300:
        out.append(ExtractionCandidate(t, "semantic", 0.5, 0.5, "stable fact"))
    if not out:
        out.append(ExtractionCandidate(t, "working", 0.3, 0.2, "transient context"))
    return out


class MemoryEngine:
    def __init__(self, store: MemoryStore | None = None,
                 embedder: emb.EmbeddingProvider | None = None,
                 weights: ret.Weights | None = None):
        self.store = store or MemoryStore()
        self.embedder = embedder or emb.select_provider("auto")
        self.weights = weights or ret.Weights()

    # ── store + embed (Phases 3/4) ────────────────────────────────────────
    def remember(self, *, namespace: str, content: str, memory_type: str = "semantic",
                 project_id: str = "", user_scope: str = "", agent_scope: str = "",
                 confidence: float = 0.5, importance: float = 0.5,
                 privacy: str = "internal", retention: str = "standard",
                 source_type: str = "", source_id: str = "", citation: str = "",
                 pinned: bool = False, embed: bool = True,
                 detect_conflicts: bool = True) -> str:
        expiry = None
        if retention_expiry and RetentionPolicy:
            try:
                expiry = retention_expiry(RetentionPolicy(retention), time.time())
            except Exception:
                expiry = None
        mid = self.store.add_item(
            namespace=namespace, memory_type=memory_type, content=content,
            project_id=project_id, user_scope=user_scope, agent_scope=agent_scope,
            confidence=confidence, importance=importance, privacy=privacy,
            retention=retention, expiry=expiry, pinned=pinned,
            provenance={"source_type": source_type, "source_id": source_id})
        if source_type or source_id or citation:
            self.store.add_source(mid, source_type=source_type, source_id=source_id,
                                  citation=citation or content[:120])
        if embed:
            self._embed_one(mid, content)
        if detect_conflicts:
            self._detect_conflicts(mid, namespace, content)
        return mid

    def _embed_one(self, mid: str, content: str) -> None:
        try:
            res = self.embedder.embed([content])
            vec = res.vectors[0]
            self.store.set_embedding(mid, emb.to_bytes(vec), res.dim, res.version,
                                     float((vec ** 2).sum() ** 0.5))
        except Exception:
            # embedding failure must not corrupt the memory; leave it keyword-only
            pass

    # ── extraction pipeline (Phase 7) ─────────────────────────────────────
    def observe(self, text: str, *, namespace: str, project_id: str = "",
                user_scope: str = "", agent_scope: str = "",
                source_type: str = "", source_id: str = "",
                min_confidence: float = 0.5) -> list[str]:
        """Observe raw text, extract bounded candidates, persist the worthy ones.
        Working/discard candidates are NOT persisted long-term."""
        stored = []
        # dedup: keep only the highest-confidence candidate for identical content
        cands = [c for c in extract_candidates(text)
                 if c.memory_type not in ("discard", "working")
                 and c.confidence >= min_confidence]
        best = max(cands, key=lambda c: c.confidence, default=None)
        for cand in ([best] if best else []):
            mid = self.remember(
                namespace=namespace, content=cand.content,
                memory_type=cand.memory_type, project_id=project_id,
                user_scope=user_scope, agent_scope=agent_scope,
                confidence=cand.confidence, importance=cand.importance,
                source_type=source_type, source_id=source_id,
                retention="semantic" if cand.memory_type in ("business", "semantic",
                                                             "user", "procedural")
                          else "standard")
            stored.append(mid)
        return stored

    # ── conflicts (Phase 8) ───────────────────────────────────────────────
    def _detect_conflicts(self, mid: str, namespace: str, content: str) -> None:
        """Flag same-namespace items about the same topic with opposing polarity."""
        from saathi.memory.evidence import _tokens, _topic_overlap
        _OPP = {"not", "no", "never", "stop", "instead", "replace", "avoid",
                "wrong", "deprecated", "old", "changed"}
        ct = _tokens(content)
        cmark = ct & _OPP
        for other in self.store.candidates([namespace]):
            if other["id"] == mid:
                continue
            ot = _tokens(other["content"])
            if _topic_overlap(ct, ot) < 0.4:
                continue
            if bool(cmark) != bool(ot & _OPP):
                self.store.add_conflict(mid, other["id"], "opposing_polarity")

    def supersede(self, old_id: str, new_content: str, *, reason: str = "updated") -> str:
        """New memory supersedes an old one; history preserved, old archived."""
        old = self.store.get_item(old_id)
        if not old:
            raise KeyError(old_id)
        new_id = self.remember(
            namespace=old["namespace"], content=new_content,
            memory_type=old["memory_type"], project_id=old["project_id"],
            user_scope=old["user_scope"], agent_scope=old["agent_scope"],
            confidence=min(1.0, old["confidence"] + 0.1),
            importance=old["importance"], privacy=old["privacy"],
            retention=old["retention"])
        self.store.add_relation(new_id, old_id, "supersedes")
        self.store.add_version(old_id, old["content"], old["confidence"],
                               f"superseded: {reason}")
        self.store.update_item(old_id, status="superseded")
        return new_id

    # ── lifecycle: decay + reinforce (Phase 9) ────────────────────────────
    def reinforce(self, mid: str, *, useful: bool = True) -> None:
        self.store.add_feedback(mid, useful)
        item = self.store.get_item(mid)
        if not item:
            return
        delta = 0.05 if useful else -0.08
        self.store.update_item(
            mid, confidence=max(0.0, min(1.0, item["confidence"] + delta)),
            status="reinforced" if useful else item["status"])

    def decay(self, *, stale_after_days: float = 60.0, now: float | None = None) -> dict:
        """Age active memories to stale/expired. Pinned and non-expiring
        retention (semantic/platform_wisdom) never decay automatically."""
        now = now or time.time()
        touched = {"stale": 0, "expired": 0}
        for it in self.store.list_items(status="any", limit=100_000):
            if it["status"] in ("deleted", "archived", "superseded"):
                continue
            if it["pinned"] or it["retention"] in ("semantic", "platform_wisdom"):
                continue
            if it["expiry"] and it["expiry"] < now:
                self.store.update_item(it["id"], status="expired")
                touched["expired"] += 1
                continue
            last = it["last_accessed"] or it["created_at"]
            if it["status"] in ("active", "reinforced") and \
                    now - last > stale_after_days * 86400:
                self.store.update_item(it["id"], status="stale")
                touched["stale"] += 1
        return touched

    # ── forgetting (Phase 10) ─────────────────────────────────────────────
    def forget(self, mid: str, *, reason: str = "user request",
               restorable: bool = True) -> None:
        self.store.tombstone(mid, reason, restorable)

    def forget_by(self, *, namespace: str | None = None, project_id: str | None = None,
                  source_id: str | None = None, reason: str = "bulk") -> int:
        n = 0
        for it in self.store.list_items(
                namespaces=[namespace] if namespace else None,
                project_id=project_id, status="any", limit=100_000):
            if source_id and it["provenance"].get("source_id") != source_id:
                continue
            if it["status"] == "deleted":
                continue
            self.forget(it["id"], reason=reason)
            n += 1
        return n

    def restore(self, mid: str) -> bool:
        ok = self.store.restore(mid)
        if ok:  # re-embed so it is searchable again
            item = self.store.get_item(mid)
            if item:
                self._embed_one(mid, item["content"])
        return ok

    # ── retrieval (Phases 5/6) ────────────────────────────────────────────
    def retrieve(self, query: str, *, plan: ret.QueryPlan,
                 actor: str = "system") -> tuple[list[ret.RetrievalResult], str, str]:
        """Scoped hybrid retrieval. Returns (results, mode, run_id)."""
        t0 = time.perf_counter()
        items = self.store.candidates(plan.namespaces)  # namespace firewall
        if plan.memory_types:
            items = [i for i in items if i["memory_type"] in plan.memory_types]
        qvec = None
        try:
            qvec = self.embedder.embed([query]).vectors[0]
        except Exception:
            qvec = None  # → keyword-only
        # bulk-load embeddings + feedback once (no per-item queries in ranking)
        ids = [i["id"] for i in items]
        emb_map = self.store.embeddings_for(ids) if qvec is not None else {}
        fb_map = self.store.feedback_ids()
        # Vectorized semantic scoring: one matrix·vector product instead of a
        # per-item Python cosine loop (query + all rows are unit-normalized).
        sem_map: dict[str, float] = {}
        if qvec is not None and emb_map:
            import numpy as np
            dim = qvec.shape[0]
            mids, rows = [], []
            for mid, e in emb_map.items():
                if e["dim"] == dim:
                    mids.append(mid)
                    rows.append(emb.from_bytes(e["vector"], dim))
            if rows:
                mat = np.vstack(rows)
                sims = mat @ qvec  # unit vectors → cosine
                for mid, s in zip(mids, sims):
                    sem_map[mid] = max(0.0, float(s))
        results, mode = ret.rank(query, items, query_vec=qvec, store=self.store,
                                 weights=self.weights, context=plan.context,
                                 top_k=plan.top_k, threshold=plan.threshold,
                                 emb_map=emb_map, fb_map=fb_map, sem_map=sem_map)
        # token-budget trim
        budget, kept = plan.token_budget, []
        for r in results:
            cost = len(r.content) // 4
            if budget - cost < 0:
                break
            budget -= cost
            kept.append(r)
            self.store.touch(r.memory_id)
            self.store.log_access(r.memory_id, actor, "allow", "in scope")
        latency = (time.perf_counter() - t0) * 1000
        run_id = self.store.record_run(query=query, namespaces=plan.namespaces,
                                       mode=mode, results=[k.to_dict() for k in kept],
                                       latency_ms=latency)
        return kept, mode, run_id

    # ── graph (Phase 11) ──────────────────────────────────────────────────
    def relate(self, src: str, dst: str, relation: str, weight: float = 1.0) -> None:
        if relation not in RELATIONS:
            raise ValueError(f"unknown relation: {relation}")
        self.store.add_relation(src, dst, relation, weight)

    def graph_expand(self, results: list[ret.RetrievalResult],
                     limit: int = 3) -> list[dict]:
        """Complement vector hits with 1-hop graph neighbors (not a replacement)."""
        seen = {r.memory_id for r in results}
        extra = []
        for r in results:
            for nid in self.store.neighbors(r.memory_id):
                if nid in seen:
                    continue
                seen.add(nid)
                item = self.store.get_item(nid)
                if item and item["status"] not in ("deleted", "superseded"):
                    extra.append({"memory_id": nid, "content": item["content"],
                                  "via": "graph", "memory_type": item["memory_type"]})
                if len(extra) >= limit:
                    return extra
        return extra

    # ── re-index (Phase 17) ───────────────────────────────────────────────
    def reindex(self, *, batch: int = 200) -> dict:
        """Controlled, bounded, resumable re-embedding to the current version."""
        version = self.embedder.version
        pending = self.store.items_missing_embedding(version, limit=batch)
        done = 0
        for it in pending:
            self._embed_one(it["id"], it["content"])
            done += 1
        remaining = len(self.store.items_missing_embedding(version, limit=100_000))
        return {"reindexed": done, "remaining": remaining,
                "version": version, "complete": remaining == 0}

    # ── chat integration (Phase 12) ───────────────────────────────────────
    def retrieve_for_chat(self, query: str, *, user: str = "ajay",
                          project_id: str = "", conversation_id: str = "",
                          agent: str = "", top_k: int = 6) -> dict:
        """Stable entry point ChatEngine calls before model execution.
        Returns retrieved memories (access-checked, thresholded, budgeted) +
        a context block + citations + retrieval metadata."""
        plan = ret.plan_query(user=user, project_id=project_id,
                              conversation_id=conversation_id, agent=agent,
                              top_k=top_k)
        results, mode, run_id = self.retrieve(query, plan=plan,
                                              actor=f"chat:{user}")
        neighbors = self.graph_expand(results, limit=2)
        block = "\n".join(f"[mem:{r.memory_id[:8]}] ({r.memory_type}) {r.content}"
                          for r in results)
        return {
            "results": [r.to_dict() for r in results],
            "graph_neighbors": neighbors,
            "context_block": block,
            "mode": mode, "run_id": run_id,
            "count": len(results),
            "citations": [{"source": r.citation or f"mem:{r.memory_id[:8]}",
                           "chunk_ref": r.memory_id, "quote": r.content[:160]}
                          for r in results if r.confidence >= 0.4],
        }


_default: MemoryEngine | None = None


def default_engine() -> MemoryEngine:
    global _default
    if _default is None:
        _default = MemoryEngine()
    return _default
