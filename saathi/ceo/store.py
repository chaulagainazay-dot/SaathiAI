"""M14 CEO OS durable store — data/ceo_os.db.

Canonical entities with provenance. Every record is owner-scoped and
business-scoped; the API enforces ownership. Financial entries keep their
state (actual/estimated/forecast/unknown) — an estimate is never stored or
returned as an actual.
"""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent.parent
DB_PATH = ROOT / "data" / "ceo_os.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS business(
  id TEXT PRIMARY KEY, owner TEXT NOT NULL, name TEXT, kind TEXT DEFAULT 'business',
  parent_id TEXT DEFAULT '', status TEXT DEFAULT 'active', memory_namespace TEXT DEFAULT '',
  source TEXT DEFAULT '', created_at REAL, updated_at REAL, archived INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS goal(
  id TEXT PRIMARY KEY, owner TEXT NOT NULL, business_id TEXT DEFAULT '', description TEXT,
  unit TEXT DEFAULT '', target_value REAL DEFAULT 0, current_value REAL DEFAULT 0,
  status TEXT DEFAULT 'active', confidence REAL DEFAULT 0.5, start_date REAL,
  target_date REAL, kpi_id TEXT DEFAULT '', provenance TEXT DEFAULT '{}',
  created_at REAL, updated_at REAL, archived INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS kpi_definition(
  id TEXT PRIMARY KEY, owner TEXT NOT NULL, business_id TEXT DEFAULT '', name TEXT,
  kpi_type TEXT, unit TEXT DEFAULT '', target REAL DEFAULT 0, source TEXT DEFAULT '',
  warn_threshold REAL, critical_threshold REAL, refresh_interval_sec REAL DEFAULT 86400,
  created_at REAL, updated_at REAL);
CREATE TABLE IF NOT EXISTS metric_observation(
  id TEXT PRIMARY KEY, kpi_id TEXT, value REAL, source TEXT, authority TEXT DEFAULT 'internal',
  evidence_tier TEXT DEFAULT 'observed', evidence_refs TEXT DEFAULT '[]', observed_at REAL);
CREATE TABLE IF NOT EXISTS decision(
  id TEXT PRIMARY KEY, owner TEXT NOT NULL, business_id TEXT DEFAULT '', question TEXT,
  context TEXT DEFAULT '', options TEXT DEFAULT '[]', recommendation TEXT DEFAULT '',
  status TEXT DEFAULT 'proposed', decided_by TEXT DEFAULT '', reversibility TEXT DEFAULT '',
  goal_id TEXT DEFAULT '', mission_id TEXT DEFAULT '', provenance TEXT DEFAULT '{}',
  review_date REAL, created_at REAL, updated_at REAL);
CREATE TABLE IF NOT EXISTS risk(
  id TEXT PRIMARY KEY, owner TEXT NOT NULL, business_id TEXT DEFAULT '', title TEXT,
  category TEXT, likelihood REAL DEFAULT 0.5, impact REAL DEFAULT 0.5, score REAL DEFAULT 0,
  trend TEXT DEFAULT 'flat', mitigation TEXT DEFAULT '', status TEXT DEFAULT 'open',
  project_id TEXT DEFAULT '', kpi_id TEXT DEFAULT '', mission_id TEXT DEFAULT '',
  provenance TEXT DEFAULT '{}', last_review REAL, next_review REAL, created_at REAL, updated_at REAL);
CREATE TABLE IF NOT EXISTS opportunity(
  id TEXT PRIMARY KEY, owner TEXT NOT NULL, business_id TEXT DEFAULT '', title TEXT,
  kind TEXT DEFAULT '', value_estimate REAL DEFAULT 0, effort REAL DEFAULT 0.5,
  score REAL DEFAULT 0, status TEXT DEFAULT 'identified', converted_to TEXT DEFAULT '',
  provenance TEXT DEFAULT '{}', created_at REAL, updated_at REAL);
CREATE TABLE IF NOT EXISTS budget(
  id TEXT PRIMARY KEY, owner TEXT NOT NULL, scope TEXT, scope_id TEXT DEFAULT '',
  approved_usd REAL DEFAULT 0, committed_usd REAL DEFAULT 0, actual_usd REAL DEFAULT 0,
  forecast_usd REAL DEFAULT 0, period TEXT DEFAULT '', warn_fraction REAL DEFAULT 0.8,
  created_at REAL, updated_at REAL);
CREATE TABLE IF NOT EXISTS financial_entry(
  id TEXT PRIMARY KEY, owner TEXT NOT NULL, business_id TEXT DEFAULT '', kind TEXT,
  state TEXT DEFAULT 'actual', amount_usd REAL, scope TEXT DEFAULT 'business',
  label TEXT DEFAULT '', source TEXT DEFAULT '', occurred_at REAL, created_at REAL);
CREATE TABLE IF NOT EXISTS review(
  id TEXT PRIMARY KEY, owner TEXT NOT NULL, kind TEXT, period TEXT DEFAULT '',
  content TEXT DEFAULT '{}', provenance TEXT DEFAULT '{}', created_at REAL);
CREATE TABLE IF NOT EXISTS alert(
  id TEXT PRIMARY KEY, owner TEXT NOT NULL, kind TEXT, severity TEXT DEFAULT 'info',
  title TEXT, detail TEXT DEFAULT '', dedup_key TEXT DEFAULT '', status TEXT DEFAULT 'open',
  evidence_refs TEXT DEFAULT '[]', created_at REAL, resolved_at REAL DEFAULT 0);
CREATE TABLE IF NOT EXISTS brief(
  id TEXT PRIMARY KEY, owner TEXT NOT NULL, content TEXT, created_at REAL);
CREATE INDEX IF NOT EXISTS idx_goal_owner ON goal(owner, business_id);
CREATE INDEX IF NOT EXISTS idx_obs_kpi ON metric_observation(kpi_id, observed_at);
CREATE INDEX IF NOT EXISTS idx_risk_owner ON risk(owner, status);
CREATE UNIQUE INDEX IF NOT EXISTS idx_alert_dedup ON alert(dedup_key) WHERE dedup_key != '';
"""


def _now() -> float:
    return time.time()


def _id(prefix: str = "c") -> str:
    return f"{prefix}_" + uuid.uuid4().hex[:14]


class CEOStore:
    def __init__(self, db_path: str | Path | None = None):
        self.db_path = Path(db_path) if db_path else DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.executescript(_SCHEMA)

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(str(self.db_path))
        c.row_factory = sqlite3.Row
        return c

    def _put(self, table: str, row: dict) -> str:
        cols = ",".join(row)
        ph = ",".join("?" * len(row))
        with self._conn() as c:
            c.execute(f"INSERT INTO {table}({cols}) VALUES({ph})", list(row.values()))
        return row["id"]

    def event(self, name: str, payload: dict) -> None:
        try:
            from saathi.events import bus
            bus.publish_sync(name, payload)
        except Exception:
            pass

    # ── business ──────────────────────────────────────────────────────────
    def add_business(self, *, owner: str, name: str, kind: str = "business",
                    source: str = "manual", parent_id: str = "") -> str:
        bid = _id("biz")
        now = _now()
        self._put("business", {"id": bid, "owner": owner, "name": name, "kind": kind,
                              "parent_id": parent_id, "status": "active",
                              "memory_namespace": f"business:{bid}", "source": source,
                              "created_at": now, "updated_at": now, "archived": 0})
        self.event("ceo.business.created", {"owner": owner, "name": name})
        return bid

    def list_businesses(self, owner: str) -> list[dict]:
        with self._conn() as c:
            return [dict(r) for r in c.execute(
                "SELECT * FROM business WHERE owner=? AND archived=0 ORDER BY created_at",
                (owner,)).fetchall()]

    def get_business(self, bid: str) -> Optional[dict]:
        with self._conn() as c:
            row = c.execute("SELECT * FROM business WHERE id=?", (bid,)).fetchone()
        return dict(row) if row else None

    # ── goals ─────────────────────────────────────────────────────────────
    def add_goal(self, *, owner: str, description: str, business_id: str = "",
                unit: str = "", target_value: float = 0, target_date: float = None,
                kpi_id: str = "", provenance: dict | None = None) -> str:
        gid = _id("goal")
        now = _now()
        self._put("goal", {"id": gid, "owner": owner, "business_id": business_id,
                          "description": description, "unit": unit,
                          "target_value": target_value, "current_value": 0,
                          "status": "active", "confidence": 0.5, "start_date": now,
                          "target_date": target_date, "kpi_id": kpi_id,
                          "provenance": json.dumps(provenance or {}),
                          "created_at": now, "updated_at": now, "archived": 0})
        return gid

    def get_goal(self, gid: str) -> Optional[dict]:
        with self._conn() as c:
            row = c.execute("SELECT * FROM goal WHERE id=?", (gid,)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["provenance"] = json.loads(d.get("provenance") or "{}")
        return d

    def update_goal(self, gid: str, **fields) -> None:
        cols = {"current_value", "status", "confidence", "target_value", "archived"}
        sets, args = ["updated_at=?"], [_now()]
        for k, v in fields.items():
            if k in cols:
                sets.append(f"{k}=?"); args.append(v)
        args.append(gid)
        with self._conn() as c:
            c.execute(f"UPDATE goal SET {','.join(sets)} WHERE id=?", args)

    def list_goals(self, owner: str, business_id: str | None = None) -> list[dict]:
        q = "SELECT * FROM goal WHERE owner=? AND archived=0"
        args = [owner]
        if business_id:
            q += " AND business_id=?"; args.append(business_id)
        q += " ORDER BY created_at"
        with self._conn() as c:
            rows = c.execute(q, args).fetchall()
        out = []
        for r in rows:
            d = dict(r); d["provenance"] = json.loads(d.get("provenance") or "{}")
            out.append(d)
        return out

    # ── KPI + observations ────────────────────────────────────────────────
    def add_kpi(self, *, owner: str, name: str, kpi_type: str, unit: str = "",
               target: float = 0, source: str = "", business_id: str = "",
               warn: float = None, critical: float = None) -> str:
        kid = _id("kpi")
        now = _now()
        self._put("kpi_definition", {"id": kid, "owner": owner, "business_id": business_id,
                                    "name": name, "kpi_type": kpi_type, "unit": unit,
                                    "target": target, "source": source,
                                    "warn_threshold": warn, "critical_threshold": critical,
                                    "refresh_interval_sec": 86400,
                                    "created_at": now, "updated_at": now})
        return kid

    def get_kpi(self, kid: str) -> Optional[dict]:
        with self._conn() as c:
            row = c.execute("SELECT * FROM kpi_definition WHERE id=?", (kid,)).fetchone()
        return dict(row) if row else None

    def list_kpis(self, owner: str) -> list[dict]:
        with self._conn() as c:
            return [dict(r) for r in c.execute(
                "SELECT * FROM kpi_definition WHERE owner=? ORDER BY created_at",
                (owner,)).fetchall()]

    def add_observation(self, kpi_id: str, *, value: float, source: str,
                       authority: str = "internal", evidence_tier: str = "observed",
                       evidence_refs: list | None = None) -> str:
        oid = _id("obs")
        self._put("metric_observation", {"id": oid, "kpi_id": kpi_id, "value": value,
                                        "source": source, "authority": authority,
                                        "evidence_tier": evidence_tier,
                                        "evidence_refs": json.dumps(evidence_refs or []),
                                        "observed_at": _now()})
        return oid

    def latest_observation(self, kpi_id: str) -> Optional[dict]:
        with self._conn() as c:
            row = c.execute("SELECT * FROM metric_observation WHERE kpi_id=? "
                           "ORDER BY observed_at DESC LIMIT 1", (kpi_id,)).fetchone()
        if not row:
            return None
        d = dict(row); d["evidence_refs"] = json.loads(d.get("evidence_refs") or "[]")
        return d

    def observation_history(self, kpi_id: str, limit: int = 30) -> list[dict]:
        with self._conn() as c:
            rows = c.execute("SELECT * FROM metric_observation WHERE kpi_id=? "
                            "ORDER BY observed_at DESC LIMIT ?", (kpi_id, limit)).fetchall()
        return [dict(r) for r in rows]

    # ── decisions ─────────────────────────────────────────────────────────
    def add_decision(self, *, owner: str, question: str, context: str = "",
                    options: list | None = None, recommendation: str = "",
                    business_id: str = "", provenance: dict | None = None) -> str:
        did = _id("dec")
        now = _now()
        self._put("decision", {"id": did, "owner": owner, "business_id": business_id,
                              "question": question, "context": context,
                              "options": json.dumps(options or []),
                              "recommendation": recommendation, "status": "proposed",
                              "decided_by": "", "reversibility": "",
                              "goal_id": "", "mission_id": "",
                              "provenance": json.dumps(provenance or {}),
                              "review_date": None, "created_at": now, "updated_at": now})
        self.event("ceo.decision.created", {"owner": owner})
        return did

    def get_decision(self, did: str) -> Optional[dict]:
        with self._conn() as c:
            row = c.execute("SELECT * FROM decision WHERE id=?", (did,)).fetchone()
        if not row:
            return None
        d = dict(row); d["options"] = json.loads(d.get("options") or "[]")
        d["provenance"] = json.loads(d.get("provenance") or "{}")
        return d

    def set_decision_status(self, did: str, status: str, decided_by: str = "") -> None:
        with self._conn() as c:
            c.execute("UPDATE decision SET status=?, decided_by=?, updated_at=? WHERE id=?",
                     (status, decided_by, _now(), did))
        self.event("ceo.decision.resolved", {"status": status, "by": decided_by})

    def list_decisions(self, owner: str, status: str | None = None) -> list[dict]:
        q = "SELECT * FROM decision WHERE owner=?"
        args = [owner]
        if status:
            q += " AND status=?"; args.append(status)
        q += " ORDER BY created_at DESC"
        with self._conn() as c:
            rows = c.execute(q, args).fetchall()
        out = []
        for r in rows:
            d = dict(r); d["options"] = json.loads(d.get("options") or "[]")
            d["provenance"] = json.loads(d.get("provenance") or "{}")
            out.append(d)
        return out

    # ── risks ─────────────────────────────────────────────────────────────
    def add_risk(self, *, owner: str, title: str, category: str, likelihood: float = 0.5,
                impact: float = 0.5, mitigation: str = "", business_id: str = "",
                provenance: dict | None = None) -> str:
        rid = _id("risk")
        now = _now()
        score = round(likelihood * impact * 100, 1)
        self._put("risk", {"id": rid, "owner": owner, "business_id": business_id,
                          "title": title, "category": category, "likelihood": likelihood,
                          "impact": impact, "score": score, "trend": "flat",
                          "mitigation": mitigation, "status": "open",
                          "project_id": "", "kpi_id": "", "mission_id": "",
                          "provenance": json.dumps(provenance or {}),
                          "last_review": now, "next_review": now + 7 * 86400,
                          "created_at": now, "updated_at": now})
        return rid

    def get_risk(self, rid: str) -> Optional[dict]:
        with self._conn() as c:
            row = c.execute("SELECT * FROM risk WHERE id=?", (rid,)).fetchone()
        return dict(row) if row else None

    def update_risk(self, rid: str, **fields) -> None:
        r = self.get_risk(rid)
        if not r:
            return
        likelihood = fields.get("likelihood", r["likelihood"])
        impact = fields.get("impact", r["impact"])
        score = round(likelihood * impact * 100, 1)
        cols = {"likelihood", "impact", "mitigation", "status", "trend"}
        sets, args = ["score=?", "updated_at=?"], [score, _now()]
        for k, v in fields.items():
            if k in cols:
                sets.append(f"{k}=?"); args.append(v)
        args.append(rid)
        with self._conn() as c:
            c.execute(f"UPDATE risk SET {','.join(sets)} WHERE id=?", args)

    def list_risks(self, owner: str, status: str | None = None) -> list[dict]:
        q = "SELECT * FROM risk WHERE owner=?"
        args = [owner]
        if status:
            q += " AND status=?"; args.append(status)
        q += " ORDER BY score DESC"
        with self._conn() as c:
            return [dict(r) for r in c.execute(q, args).fetchall()]

    # ── opportunities ─────────────────────────────────────────────────────
    def add_opportunity(self, *, owner: str, title: str, kind: str = "",
                       value_estimate: float = 0, effort: float = 0.5,
                       business_id: str = "") -> str:
        oid = _id("opp")
        now = _now()
        score = round((value_estimate / max(1, value_estimate)) * (1 - effort) * 100 +
                      min(value_estimate / 1000, 50), 1)
        self._put("opportunity", {"id": oid, "owner": owner, "business_id": business_id,
                                 "title": title, "kind": kind,
                                 "value_estimate": value_estimate, "effort": effort,
                                 "score": score, "status": "identified",
                                 "converted_to": "", "provenance": "{}",
                                 "created_at": now, "updated_at": now})
        return oid

    def get_opportunity(self, oid: str) -> Optional[dict]:
        with self._conn() as c:
            row = c.execute("SELECT * FROM opportunity WHERE id=?", (oid,)).fetchone()
        return dict(row) if row else None

    def set_opportunity(self, oid: str, *, status: str, converted_to: str = "") -> None:
        with self._conn() as c:
            c.execute("UPDATE opportunity SET status=?, converted_to=?, updated_at=? WHERE id=?",
                     (status, converted_to, _now(), oid))

    def list_opportunities(self, owner: str) -> list[dict]:
        with self._conn() as c:
            return [dict(r) for r in c.execute(
                "SELECT * FROM opportunity WHERE owner=? ORDER BY score DESC",
                (owner,)).fetchall()]

    # ── budgets + financial entries ───────────────────────────────────────
    def add_budget(self, *, owner: str, scope: str, scope_id: str = "",
                  approved_usd: float = 0, period: str = "") -> str:
        bid = _id("bud")
        now = _now()
        self._put("budget", {"id": bid, "owner": owner, "scope": scope, "scope_id": scope_id,
                            "approved_usd": approved_usd, "committed_usd": 0, "actual_usd": 0,
                            "forecast_usd": 0, "period": period, "warn_fraction": 0.8,
                            "created_at": now, "updated_at": now})
        return bid

    def get_budget(self, bid: str) -> Optional[dict]:
        with self._conn() as c:
            row = c.execute("SELECT * FROM budget WHERE id=?", (bid,)).fetchone()
        return dict(row) if row else None

    def update_budget(self, bid: str, **fields) -> None:
        cols = {"approved_usd", "committed_usd", "actual_usd", "forecast_usd"}
        sets, args = ["updated_at=?"], [_now()]
        for k, v in fields.items():
            if k in cols:
                sets.append(f"{k}=?"); args.append(v)
        args.append(bid)
        with self._conn() as c:
            c.execute(f"UPDATE budget SET {','.join(sets)} WHERE id=?", args)

    def add_financial_entry(self, *, owner: str, kind: str, state: str, amount_usd: float,
                           business_id: str = "", scope: str = "business",
                           label: str = "", source: str = "") -> str:
        fid = _id("fin")
        now = _now()
        self._put("financial_entry", {"id": fid, "owner": owner, "business_id": business_id,
                                     "kind": kind, "state": state, "amount_usd": amount_usd,
                                     "scope": scope, "label": label, "source": source,
                                     "occurred_at": now, "created_at": now})
        return fid

    def financial_entries(self, owner: str, *, state: str | None = None) -> list[dict]:
        q = "SELECT * FROM financial_entry WHERE owner=?"
        args = [owner]
        if state:
            q += " AND state=?"; args.append(state)
        with self._conn() as c:
            return [dict(r) for r in c.execute(q, args).fetchall()]

    # ── reviews ───────────────────────────────────────────────────────────
    def add_review(self, *, owner: str, kind: str, content: dict, period: str = "",
                  provenance: dict | None = None) -> str:
        rid = _id("rev")
        self._put("review", {"id": rid, "owner": owner, "kind": kind, "period": period,
                            "content": json.dumps(content),
                            "provenance": json.dumps(provenance or {}), "created_at": _now()})
        return rid

    def list_reviews(self, owner: str, kind: str | None = None) -> list[dict]:
        q = "SELECT * FROM review WHERE owner=?"
        args = [owner]
        if kind:
            q += " AND kind=?"; args.append(kind)
        q += " ORDER BY created_at DESC"
        with self._conn() as c:
            rows = c.execute(q, args).fetchall()
        out = []
        for r in rows:
            d = dict(r); d["content"] = json.loads(d.get("content") or "{}")
            out.append(d)
        return out

    # ── alerts (deduplicated) ─────────────────────────────────────────────
    def add_alert(self, *, owner: str, kind: str, title: str, severity: str = "info",
                 detail: str = "", dedup_key: str = "", evidence_refs: list | None = None) -> str | None:
        if dedup_key:
            with self._conn() as c:
                existing = c.execute("SELECT id FROM alert WHERE dedup_key=? AND status='open'",
                                    (dedup_key,)).fetchone()
            if existing:
                return None  # suppress duplicate for the same unresolved condition
        aid = _id("alert")
        try:
            self._put("alert", {"id": aid, "owner": owner, "kind": kind, "severity": severity,
                              "title": title, "detail": detail, "dedup_key": dedup_key,
                              "status": "open", "evidence_refs": json.dumps(evidence_refs or []),
                              "created_at": _now(), "resolved_at": 0})
        except sqlite3.IntegrityError:
            return None
        return aid

    def list_alerts(self, owner: str, status: str = "open") -> list[dict]:
        with self._conn() as c:
            rows = c.execute("SELECT * FROM alert WHERE owner=? AND status=? "
                            "ORDER BY created_at DESC", (owner, status)).fetchall()
        out = []
        for r in rows:
            d = dict(r); d["evidence_refs"] = json.loads(d.get("evidence_refs") or "[]")
            out.append(d)
        return out

    def resolve_alert(self, aid: str) -> None:
        with self._conn() as c:
            c.execute("UPDATE alert SET status='resolved', resolved_at=? WHERE id=?",
                     (_now(), aid))

    # ── briefs ────────────────────────────────────────────────────────────
    def add_brief(self, owner: str, content: dict) -> str:
        bid = _id("brief")
        self._put("brief", {"id": bid, "owner": owner, "content": json.dumps(content),
                          "created_at": _now()})
        return bid

    def list_briefs(self, owner: str, limit: int = 14) -> list[dict]:
        with self._conn() as c:
            rows = c.execute("SELECT * FROM brief WHERE owner=? ORDER BY created_at DESC "
                            "LIMIT ?", (owner, limit)).fetchall()
        out = []
        for r in rows:
            d = dict(r); d["content"] = json.loads(d.get("content") or "{}")
            out.append(d)
        return out


_default: CEOStore | None = None


def default_store() -> CEOStore:
    global _default
    if _default is None:
        _default = CEOStore()
    return _default
