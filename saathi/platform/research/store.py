"""M62.3 — research persistence (single-host SQLite, tenant-scoped, versioned).

Published thesis versions are immutable; corrections require a new version. Not
multi-node safe; distributed mode disabled.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time as _time
from pathlib import Path
from typing import Any

from saathi.platform.models import new_id

_SCHEMA = """
CREATE TABLE IF NOT EXISTS research_projects (
    project_id TEXT PRIMARY KEY, org_id TEXT NOT NULL, workspace_id TEXT NOT NULL,
    mission_id TEXT NOT NULL DEFAULT '', title TEXT NOT NULL, question TEXT NOT NULL DEFAULT '',
    scope TEXT NOT NULL DEFAULT '', plan_json TEXT NOT NULL DEFAULT '{}', state TEXT NOT NULL DEFAULT 'DRAFT',
    created_by TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1, created_at REAL NOT NULL, updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS research_sources (
    source_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, org_id TEXT NOT NULL, workspace_id TEXT NOT NULL,
    source_type TEXT NOT NULL, title TEXT NOT NULL, locator TEXT NOT NULL DEFAULT '', content TEXT NOT NULL DEFAULT '',
    publisher TEXT NOT NULL DEFAULT '', author TEXT NOT NULL DEFAULT '', published_at REAL NOT NULL DEFAULT 0,
    retrieved_at REAL NOT NULL DEFAULT 0, effective_at REAL NOT NULL DEFAULT 0, mime_type TEXT NOT NULL DEFAULT 'text/plain',
    language TEXT NOT NULL DEFAULT 'en', trust TEXT NOT NULL DEFAULT 'UNVERIFIED', quality TEXT NOT NULL DEFAULT 'UNVERIFIED',
    injection TEXT NOT NULL DEFAULT 'CLEAN', findings TEXT NOT NULL DEFAULT '[]', hash TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS research_claims (
    claim_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, org_id TEXT NOT NULL, source_id TEXT NOT NULL,
    statement TEXT NOT NULL, fact_class TEXT NOT NULL, locator TEXT NOT NULL DEFAULT '', confidence REAL NOT NULL DEFAULT 0.5,
    materiality TEXT NOT NULL DEFAULT 'medium', time_relevance REAL NOT NULL DEFAULT 0, agent_role TEXT NOT NULL DEFAULT '',
    model_provenance TEXT NOT NULL DEFAULT '', verification TEXT NOT NULL DEFAULT 'UNVERIFIED', excerpt TEXT NOT NULL DEFAULT '',
    meta_json TEXT NOT NULL DEFAULT '{}', created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS research_citations (
    citation_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, org_id TEXT NOT NULL, claim_id TEXT NOT NULL,
    source_id TEXT NOT NULL, locator TEXT NOT NULL, source_hash TEXT NOT NULL DEFAULT '',
    verification TEXT NOT NULL DEFAULT 'UNVERIFIED', detail TEXT NOT NULL DEFAULT '', created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS research_contradictions (
    contradiction_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, org_id TEXT NOT NULL,
    claim_a TEXT NOT NULL, claim_b TEXT NOT NULL, kind TEXT NOT NULL, severity TEXT NOT NULL DEFAULT 'medium',
    resolution TEXT NOT NULL DEFAULT 'UNRESOLVED', notes TEXT NOT NULL DEFAULT '', created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS research_theses (
    thesis_id TEXT NOT NULL, project_id TEXT NOT NULL, org_id TEXT NOT NULL, workspace_id TEXT NOT NULL,
    version INTEGER NOT NULL, state TEXT NOT NULL DEFAULT 'DRAFT', body_json TEXT NOT NULL DEFAULT '{}',
    confidence_json TEXT NOT NULL DEFAULT '{}', challenge_json TEXT NOT NULL DEFAULT '{}',
    change_rationale TEXT NOT NULL DEFAULT '', author TEXT NOT NULL DEFAULT '', published INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL,
    PRIMARY KEY (project_id, version)
);
CREATE INDEX IF NOT EXISTS idx_rsrc_proj ON research_sources(org_id, project_id);
CREATE INDEX IF NOT EXISTS idx_rclaim_proj ON research_claims(org_id, project_id);
CREATE INDEX IF NOT EXISTS idx_rthesis_proj ON research_theses(org_id, project_id, version DESC);
"""


class ResearchStore:
    def __init__(self, db_path: str | Path | None = None):
        env = os.environ.get("SAATHI_RESEARCH_DB") or os.environ.get("SAATHI_PLATFORM_DB", "")
        default = Path(__file__).resolve().parents[3] / "data" / "platform" / "platform.db"
        self.db_path = Path(db_path) if db_path else (Path(env) if env else default)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    @staticmethod
    def _j(v):
        try:
            return json.loads(v or "{}")
        except Exception:
            return {}

    # ── projects ─────────────────────────────────────────────────────────
    def create_project(self, *, org_id, workspace_id, mission_id, title, question, scope, created_by) -> dict:
        pid = new_id("rprj_")
        ts = _time.time()
        self._conn.execute(
            "INSERT INTO research_projects (project_id, org_id, workspace_id, mission_id, title, question, scope,"
            " plan_json, state, created_by, version, created_at, updated_at) VALUES (?,?,?,?,?,?,?,'{}','DRAFT',?,1,?,?)",
            (pid, org_id, workspace_id, mission_id, title, question, scope, created_by, ts, ts))
        self._conn.commit()
        return self.get_project(org_id, pid)

    def get_project(self, org_id, pid) -> dict | None:
        r = self._conn.execute("SELECT * FROM research_projects WHERE org_id=? AND project_id=?", (org_id, pid)).fetchone()
        if not r:
            return None
        d = dict(r); d["plan"] = self._j(d.pop("plan_json")); return d

    def list_projects(self, org_id, *, limit=200) -> list[dict]:
        rows = self._conn.execute("SELECT project_id, title, state, version, created_at, question FROM research_projects"
                                  " WHERE org_id=? ORDER BY created_at DESC LIMIT ?", (org_id, int(limit))).fetchall()
        return [dict(r) for r in rows]

    def update_project(self, org_id, pid, *, expected_version, state=None, plan=None, title=None, question=None, scope=None) -> tuple[str, dict | None]:
        cur = self.get_project(org_id, pid)
        if not cur:
            return ("not_found", None)
        if int(expected_version) != int(cur["version"]):
            return ("conflict", cur)
        self._conn.execute(
            "UPDATE research_projects SET state=?, plan_json=?, title=?, question=?, scope=?, version=?, updated_at=?"
            " WHERE project_id=?",
            (state or cur["state"], json.dumps(plan if plan is not None else cur["plan"]),
             title if title is not None else cur["title"], question if question is not None else cur["question"],
             scope if scope is not None else cur["scope"], int(cur["version"]) + 1, _time.time(), pid))
        self._conn.commit()
        return ("ok", self.get_project(org_id, pid))

    # ── sources / claims / citations / contradictions ────────────────────
    def add_source(self, org_id, s) -> None:
        self._conn.execute(
            "INSERT INTO research_sources (source_id, project_id, org_id, workspace_id, source_type, title, locator,"
            " content, publisher, author, published_at, retrieved_at, effective_at, mime_type, language, trust, quality,"
            " injection, findings, hash, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (s.source_id, s.project_id, org_id, s.workspace_id, s.source_type.value, s.title, s.locator, s.content,
             s.publisher, s.author, s.published_at, s.retrieved_at, s.effective_at, s.mime_type, s.language,
             s.trust.value, s.quality.value, s.injection.value, json.dumps(s.findings), s.hash, _time.time()))
        self._conn.commit()

    def list_sources(self, org_id, pid) -> list[dict]:
        rows = self._conn.execute("SELECT * FROM research_sources WHERE org_id=? AND project_id=? ORDER BY created_at",
                                  (org_id, pid)).fetchall()
        out = []
        for r in rows:
            d = dict(r); d["findings"] = self._j(d.get("findings") or "[]") if d.get("findings", "[]").startswith("[") else []
            d.pop("content", None)  # do not leak full content in list
            out.append(d)
        return out

    def get_source_row(self, org_id, source_id) -> dict | None:
        r = self._conn.execute("SELECT * FROM research_sources WHERE org_id=? AND source_id=?", (org_id, source_id)).fetchone()
        return dict(r) if r else None

    def add_claim(self, org_id, c, meta: dict) -> None:
        self._conn.execute(
            "INSERT INTO research_claims (claim_id, project_id, org_id, source_id, statement, fact_class, locator,"
            " confidence, materiality, time_relevance, agent_role, model_provenance, verification, excerpt, meta_json, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (c.claim_id, c.project_id, org_id, c.source_id, c.statement, c.fact_class.value, c.locator, c.confidence,
             c.materiality, c.time_relevance, c.agent_role, c.model_provenance, c.verification.value, c.excerpt,
             json.dumps(meta), _time.time()))
        self._conn.commit()

    def list_claims(self, org_id, pid) -> list[dict]:
        rows = self._conn.execute("SELECT * FROM research_claims WHERE org_id=? AND project_id=? ORDER BY created_at",
                                  (org_id, pid)).fetchall()
        out = []
        for r in rows:
            d = dict(r); d["meta"] = self._j(d.pop("meta_json")); out.append(d)
        return out

    def set_claim_verification(self, org_id, claim_id, verification) -> None:
        self._conn.execute("UPDATE research_claims SET verification=? WHERE org_id=? AND claim_id=?",
                           (verification, org_id, claim_id))
        self._conn.commit()

    def add_citation(self, org_id, pid, cit) -> None:
        self._conn.execute(
            "INSERT INTO research_citations (citation_id, project_id, org_id, claim_id, source_id, locator, source_hash,"
            " verification, detail, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (cit.citation_id, pid, org_id, cit.claim_id, cit.source_id, cit.locator, cit.source_hash,
             cit.verification.value, cit.detail, _time.time()))
        self._conn.commit()

    def list_citations(self, org_id, pid) -> list[dict]:
        return [dict(r) for r in self._conn.execute(
            "SELECT * FROM research_citations WHERE org_id=? AND project_id=? ORDER BY created_at", (org_id, pid)).fetchall()]

    def clear_derived(self, org_id, pid) -> None:
        """Idempotent re-run of extraction/contradiction: drop prior claims/citations/contradictions."""
        for tbl in ("research_claims", "research_citations", "research_contradictions"):
            self._conn.execute(f"DELETE FROM {tbl} WHERE org_id=? AND project_id=?", (org_id, pid))
        self._conn.commit()

    def add_contradiction(self, org_id, pid, con) -> None:
        self._conn.execute(
            "INSERT INTO research_contradictions (contradiction_id, project_id, org_id, claim_a, claim_b, kind, severity,"
            " resolution, notes, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (con.contradiction_id, pid, org_id, con.claim_a, con.claim_b, con.kind.value, con.severity,
             con.resolution, con.notes, _time.time()))
        self._conn.commit()

    def list_contradictions(self, org_id, pid) -> list[dict]:
        return [dict(r) for r in self._conn.execute(
            "SELECT * FROM research_contradictions WHERE org_id=? AND project_id=? ORDER BY created_at", (org_id, pid)).fetchall()]

    # ── theses (versioned; published immutable) ──────────────────────────
    def latest_thesis(self, org_id, pid) -> dict | None:
        r = self._conn.execute("SELECT * FROM research_theses WHERE org_id=? AND project_id=? ORDER BY version DESC LIMIT 1",
                               (org_id, pid)).fetchone()
        if not r:
            return None
        d = dict(r); d["body"] = self._j(d.pop("body_json")); d["confidence"] = self._j(d.pop("confidence_json"))
        d["challenge"] = self._j(d.pop("challenge_json")); return d

    def new_thesis_version(self, org_id, workspace_id, pid, *, state, body, confidence, challenge, author, rationale="") -> dict:
        prev = self.latest_thesis(org_id, pid)
        if prev and prev.get("published"):
            # published versions are immutable; a correction is a NEW version
            pass
        version = (prev["version"] + 1) if prev else 1
        self._conn.execute(
            "INSERT INTO research_theses (thesis_id, project_id, org_id, workspace_id, version, state, body_json,"
            " confidence_json, challenge_json, change_rationale, author, published, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,0,?)",
            (pid, pid, org_id, workspace_id, version, state, json.dumps(body), json.dumps(confidence),
             json.dumps(challenge), rationale, author, _time.time()))
        self._conn.commit()
        return self.thesis_version(org_id, pid, version)

    def set_thesis_state(self, org_id, pid, version, *, state, published=None, challenge=None) -> tuple[str, dict | None]:
        cur = self.thesis_version(org_id, pid, version)
        if not cur:
            return ("not_found", None)
        if cur.get("published"):
            return ("immutable", cur)  # cannot mutate a published version
        self._conn.execute(
            "UPDATE research_theses SET state=?, published=?, challenge_json=? WHERE project_id=? AND version=?",
            (state, 1 if published else (cur["published"]), json.dumps(challenge if challenge is not None else cur["challenge"]),
             pid, version))
        self._conn.commit()
        return ("ok", self.thesis_version(org_id, pid, version))

    def thesis_version(self, org_id, pid, version) -> dict | None:
        r = self._conn.execute("SELECT * FROM research_theses WHERE org_id=? AND project_id=? AND version=?",
                              (org_id, pid, version)).fetchone()
        if not r:
            return None
        d = dict(r); d["body"] = self._j(d.pop("body_json")); d["confidence"] = self._j(d.pop("confidence_json"))
        d["challenge"] = self._j(d.pop("challenge_json")); return d

    def list_thesis_versions(self, org_id, pid) -> list[dict]:
        rows = self._conn.execute("SELECT version, state, published, author, change_rationale, created_at FROM research_theses"
                                  " WHERE org_id=? AND project_id=? ORDER BY version", (org_id, pid)).fetchall()
        return [dict(r) for r in rows]
