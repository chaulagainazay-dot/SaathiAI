"""Mission Knowledge Graph — the Business Memory of SaathiOS.

Not a graph database — the persistent, evolving memory of a business that every
Director reads from and every connector writes into. One node per real thing
(company, brand, product, customer, competitor, document, revenue, KPI, account,
social channel …); nothing duplicated. Research fills it, connectors enrich it,
uploads extend it. Because knowledge lives in one place, the Mission's confidence
stops being an abstract score and becomes KNOWLEDGE COVERAGE — how much of the
business we actually hold in memory.

This is the differentiator: most platforms have workflows and dashboards; few
have a shared, growing business memory behind every AI Director and automation.
"""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from pathlib import Path

NODE_TYPES = (
    "company", "brand", "product", "service", "customer", "employee", "partner",
    "competitor", "document", "asset", "workflow", "automation", "prompt", "dataset",
    "evidence", "learning", "revenue", "kpi", "timeline", "decision", "risk",
    "opportunity", "account", "social_channel", "website", "file", "meeting", "task",
)

# the categories the Knowledge Coverage score is measured over (a business we "understand")
_COVERAGE = ["company", "website", "brand", "product", "customer", "document",
             "competitor", "revenue", "social_channel", "account", "kpi"]

_COLUMNS = ["id", "mission_id", "type", "key", "label", "data", "source", "updated"]


class KnowledgeGraph:
    def __init__(self, db_path: str | None = None):
        self.db_path = Path(db_path) if db_path else (Path.home() / ".saathi" / "mission_knowledge.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            cols = ", ".join(f"{col} {'REAL' if col == 'updated' else 'TEXT'}" for col in _COLUMNS)
            c.execute(f"CREATE TABLE IF NOT EXISTS node({cols}, PRIMARY KEY(id))")
            c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_node_uniq ON node(mission_id, type, key)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_node_m ON node(mission_id, type)")

    def _conn(self):
        return sqlite3.connect(str(self.db_path))

    def upsert(self, mission_id: str, node_type: str, key: str, *, label: str = "",
               data: dict | None = None, source: str = "") -> str:
        node_type = node_type if node_type in NODE_TYPES else "asset"
        with self._conn() as c:
            row = c.execute("SELECT id FROM node WHERE mission_id=? AND type=? AND key=?",
                            (mission_id, node_type, key)).fetchone()
            nid = row[0] if row else uuid.uuid4().hex[:16]
            c.execute("INSERT OR REPLACE INTO node(id,mission_id,type,key,label,data,source,updated) "
                      "VALUES(?,?,?,?,?,?,?,?)",
                      (nid, mission_id, node_type, key, label or key,
                       json.dumps(data or {}), source, time.time()))
        return nid

    def nodes(self, mission_id: str, *, node_type: str | None = None, limit: int = 500) -> list[dict]:
        sql = "SELECT " + ",".join(_COLUMNS) + " FROM node WHERE mission_id=?"
        args = [mission_id]
        if node_type:
            sql += " AND type=?"; args.append(node_type)
        sql += " ORDER BY type, updated DESC LIMIT ?"; args.append(limit)
        with self._conn() as c:
            rows = c.execute(sql, args).fetchall()
        out = []
        for r in rows:
            d = dict(zip(_COLUMNS, r))
            try:
                d["data"] = json.loads(d["data"]) if d["data"] else {}
            except Exception:
                d["data"] = {}
            out.append(d)
        return out

    def context(self, mission_id: str, types: list[str]) -> dict:
        """What a Director reads: nodes grouped by the types it cares about."""
        return {t: self.nodes(mission_id, node_type=t) for t in types}

    def counts(self, mission_id: str) -> dict:
        with self._conn() as c:
            rows = c.execute("SELECT type, COUNT(*) FROM node WHERE mission_id=? GROUP BY type",
                             (mission_id,)).fetchall()
        return {t: n for t, n in rows}

    def coverage(self, mission_id: str) -> dict:
        """Knowledge Coverage — how much of the business we actually hold in memory.
        Per category: 1.0 if a node exists with real data, 0.5 if present-but-thin, 0 absent."""
        by_type: dict[str, list] = {}
        for n in self.nodes(mission_id):
            by_type.setdefault(n["type"], []).append(n)
        cats = {}
        for cat in _COVERAGE:
            ns = by_type.get(cat, [])
            if not ns:
                cats[cat] = 0.0
            elif any(n["data"] for n in ns):
                cats[cat] = 1.0
            else:
                cats[cat] = 0.5
        overall = round(sum(cats.values()) / len(cats), 2) if cats else 0.0
        return {"overall": overall, "categories": cats, "node_count": sum(len(v) for v in by_type.values())}


_default = None
def default_graph() -> KnowledgeGraph:
    global _default
    if _default is None:
        _default = KnowledgeGraph()
    return _default


# ── Populate the graph from a Digital Twin (Research writes the memory) ────────
def populate_from_twin(mission: dict, twin: dict, *, graph: "KnowledgeGraph | None" = None) -> int:
    g = graph or default_graph()
    mid = mission.get("id", "")
    identity = mission.get("identity") or {}
    reports = twin.get("reports", {})
    briefing = twin.get("briefing", {})
    n = 0

    g.upsert(mid, "company", "company", label=mission.get("name", ""),
             data={"industry": identity.get("industry", ""), "country": identity.get("country", ""),
                   "type": mission.get("type", "")}, source="research"); n += 1

    website = identity.get("website") or (reports.get("company", {}) or {}).get("website", "")
    research = twin.get("research", {})
    if website or research.get("ok"):
        g.upsert(mid, "website", "website", label=website or research.get("url", ""),
                 data={"url": website or research.get("url", ""), "title": research.get("title", ""),
                       "seo_score": (reports.get("seo", {}) or {}).get("score")}, source="research"); n += 1

    for ch, url in (research.get("socials") or {}).items():
        g.upsert(mid, "social_channel", ch, label=ch, data={"url": url}, source="research"); n += 1

    for comp in (reports.get("competitors", {}) or {}).get("competitors", []) or []:
        g.upsert(mid, "competitor", str(comp)[:40], label=str(comp), data={"name": comp}, source="research"); n += 1

    for i, opp in enumerate(briefing.get("top_opportunities", [])):
        g.upsert(mid, "opportunity", f"opp-{i}", label=str(opp)[:60], data={"text": opp}, source="strategist"); n += 1
    for i, risk in enumerate(briefing.get("top_risks", [])):
        g.upsert(mid, "risk", f"risk-{i}", label=str(risk)[:60], data={"text": risk}, source="strategist"); n += 1

    if identity.get("services"):
        g.upsert(mid, "service", "services", label="Services",
                 data={"list": identity["services"]}, source="intake"); n += 1
    return n
