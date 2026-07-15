"""M16 federated search — permission-scoped, secret-free.

Searches across canonical subsystems the caller owns. Every result carries
entity type, source, timestamp, and a deep link. Owner scoping is mandatory: a
query never returns another user's connectors/approvals/executions. Secrets are
never indexed or returned (credential rows expose only backend key NAMES).
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SearchResult:
    entity_type: str
    title: str
    summary: str
    source: str
    timestamp: float = 0.0
    link: str = ""
    relevance: float = 0.0

    def to_dict(self) -> dict:
        return {"entity_type": self.entity_type, "title": self.title,
                "summary": self.summary, "source": self.source,
                "timestamp": self.timestamp, "link": self.link,
                "relevance": self.relevance}


def _match(q: str, *fields) -> float:
    ql = q.lower().strip()
    if not ql:
        return 0.0
    hay = " ".join(str(f) for f in fields if f).lower()
    if ql in hay:
        return 1.0 if hay.startswith(ql) else 0.6
    # token overlap
    toks = [t for t in ql.split() if t]
    hit = sum(1 for t in toks if t in hay)
    return round(hit / len(toks), 3) if toks else 0.0


def federated_search(*, owner: str, query: str, entity_types: list | None = None,
                     limit: int = 30) -> dict:
    results: list[SearchResult] = []
    types = set(entity_types) if entity_types else None

    def want(t: str) -> bool:
        return types is None or t in types

    from saathi.connectors.platform import registry as R
    from saathi.connectors.platform import store as S
    store = S.default_store()

    # connectors (catalog is not owner-scoped — public capability info, no secrets)
    if want("connector"):
        for c in R.all_connectors():
            r = _match(query, c.connector_id, c.display_name, c.category)
            if r:
                results.append(SearchResult("connector", c.display_name,
                               f"{c.category} · {c.integration_status}", "connectors",
                               link=f"/control/connectors#{c.connector_id}", relevance=r))
    # tools/operations
    if want("operation"):
        for t in R.all_tools():
            r = _match(query, t.tool_id, t.name, t.capability_id)
            if r:
                results.append(SearchResult("operation", t.name,
                               f"{t.tool_id} · risk {int(t.risk_class)}", "connectors",
                               link=f"/control/connectors#{t.tool_id}", relevance=r))
    # OWNER-SCOPED: accounts (metadata only, no secrets)
    if want("account"):
        for a in store.list_accounts(owner):
            r = _match(query, a.get("label"), a.get("connector_id"))
            if r:
                results.append(SearchResult("account", a.get("label") or a["id"],
                               f"{a.get('connector_id')} · {a.get('state')}", "connectors",
                               link=f"/control/connectors#{a['id']}", relevance=r))
    # OWNER-SCOPED: approvals
    if want("approval"):
        for ap in store.pending_approvals(owner):
            r = _match(query, ap.get("tool_id"), ap.get("connector_id"))
            if r:
                results.append(SearchResult("approval", ap.get("tool_id", ""),
                               f"risk {ap.get('risk')} · pending", "approvals",
                               link=f"/control/approvals#{ap['id']}", relevance=r))
    # OWNER-SCOPED: executions
    if want("execution"):
        for ex in store.list_executions(owner, limit=100):
            r = _match(query, ex.get("tool_id"), ex.get("status"))
            if r:
                results.append(SearchResult("execution", ex.get("tool_id", ""),
                               f"{ex.get('status')}", "connectors",
                               link=f"/control/work#{ex['id']}", relevance=r))

    # M19.2: optional repository knowledge facet — explicit type only so default
    # federated_search behaviour (types=None) remains unchanged.
    if entity_types is not None and "repository" in entity_types and want("repository"):
        try:
            from saathi.knowledge.adoption import control_center_repository_search
            ks_out = control_center_repository_search(
                query, owner=owner, top_k=min(limit, 10),
            )
            for item in ks_out.get("operator_results") or []:
                results.append(SearchResult(
                    entity_type="repository",
                    title=str(item.get("title") or "")[:200],
                    summary=str(item.get("summary") or "")[:240],
                    source=str(item.get("source") or "knowledge"),
                    link=str(item.get("link") or ""),
                    relevance=float(item.get("relevance") or 0.0),
                ))
            # Surface adoption metadata without secrets
            adoption_meta = ks_out.get("adoption") or {}
        except Exception as e:
            adoption_meta = {"error": type(e).__name__, "path_used": "error"}
    else:
        adoption_meta = None

    results.sort(key=lambda x: x.relevance, reverse=True)
    out = {"query": query, "total": len(results),
           "results": [r.to_dict() for r in results[:limit]]}
    if adoption_meta is not None:
        out["repository_adoption"] = {
            k: adoption_meta[k]
            for k in ("caller_id", "mode", "path_used", "latency_ms", "fallback_reason")
            if k in adoption_meta
        }
        # Partial-result flag for operator visibility
        if any(r.entity_type == "repository" for r in results):
            out["partial_repository"] = False
        else:
            out["partial_repository"] = True
    return out
