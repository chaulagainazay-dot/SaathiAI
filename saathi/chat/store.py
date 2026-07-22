"""Saathi Chat durable store — normalized SQLite schema (M8, Layers 1/2/4/8).

Eleven normalized tables: conversation, message, attachment, memory_link,
citation, execution, tool_invocation, summary, project_ref, agent_run,
checkpoint. Auto-save is intrinsic (every write commits); crash recovery is
a read; checkpoints capture restorable conversation snapshots; message edits
keep version history in-place via parent_id chains.
"""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parent.parent.parent
DB_PATH = ROOT / "data" / "chat.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS conversation(
  id TEXT PRIMARY KEY, title TEXT DEFAULT '', summary TEXT DEFAULT '',
  created_at REAL, updated_at REAL,
  archived INTEGER DEFAULT 0, deleted INTEGER DEFAULT 0, pinned INTEGER DEFAULT 0,
  favorite INTEGER DEFAULT 0, folder TEXT DEFAULT '', tags TEXT DEFAULT '[]',
  model TEXT DEFAULT '', tools TEXT DEFAULT '[]',
  project_id TEXT DEFAULT '', tokens_in INTEGER DEFAULT 0, tokens_out INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS message(
  id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL,
  role TEXT NOT NULL, content TEXT NOT NULL,
  created_at REAL, model TEXT DEFAULT '', status TEXT DEFAULT 'complete',
  parent_id TEXT DEFAULT '', superseded_by TEXT DEFAULT '',
  reasoning TEXT DEFAULT '', tokens INTEGER DEFAULT 0, meta TEXT DEFAULT '{}');
CREATE TABLE IF NOT EXISTS attachment(
  id TEXT PRIMARY KEY, conversation_id TEXT, message_id TEXT DEFAULT '',
  kind TEXT, name TEXT, path TEXT, size INTEGER DEFAULT 0, created_at REAL);
CREATE TABLE IF NOT EXISTS memory_link(
  id TEXT PRIMARY KEY, conversation_id TEXT, memory_kind TEXT,
  memory_ref TEXT, relevance REAL DEFAULT 0, created_at REAL);
CREATE TABLE IF NOT EXISTS citation(
  id TEXT PRIMARY KEY, message_id TEXT, source TEXT, chunk_ref TEXT DEFAULT '',
  quote TEXT DEFAULT '', created_at REAL);
CREATE TABLE IF NOT EXISTS execution(
  id TEXT PRIMARY KEY, message_id TEXT, intent_id TEXT, provider TEXT DEFAULT '',
  status TEXT DEFAULT '', cost_usd REAL DEFAULT 0, duration_sec REAL DEFAULT 0,
  created_at REAL);
CREATE TABLE IF NOT EXISTS tool_invocation(
  id TEXT PRIMARY KEY, message_id TEXT, tool TEXT, intent_id TEXT DEFAULT '',
  args TEXT DEFAULT '{}', status TEXT DEFAULT 'pending',
  result TEXT DEFAULT '', created_at REAL, finished_at REAL DEFAULT 0);
CREATE TABLE IF NOT EXISTS summary(
  id TEXT PRIMARY KEY, conversation_id TEXT, content TEXT,
  upto_message_id TEXT DEFAULT '', created_at REAL);
CREATE TABLE IF NOT EXISTS project_ref(
  id TEXT PRIMARY KEY, project_id TEXT, kind TEXT, ref TEXT, created_at REAL);
CREATE TABLE IF NOT EXISTS agent_run(
  id TEXT PRIMARY KEY, conversation_id TEXT, agent TEXT, task TEXT,
  delegated_by TEXT DEFAULT '', status TEXT DEFAULT 'running',
  result_message_id TEXT DEFAULT '', created_at REAL, finished_at REAL DEFAULT 0);
CREATE TABLE IF NOT EXISTS checkpoint(
  id TEXT PRIMARY KEY, conversation_id TEXT, label TEXT DEFAULT '',
  snapshot TEXT NOT NULL, created_at REAL);
CREATE INDEX IF NOT EXISTS idx_msg_conv ON message(conversation_id, created_at);
CREATE INDEX IF NOT EXISTS idx_conv_updated ON conversation(updated_at);
CREATE INDEX IF NOT EXISTS idx_ckpt_conv ON checkpoint(conversation_id, created_at);
"""


def _now() -> float:
    return time.time()


def _id() -> str:
    return uuid.uuid4().hex


class ChatStore:
    """All persistence for Saathi Chat. One store per db file."""

    def __init__(self, db_path: str | Path | None = None):
        self.db_path = Path(db_path) if db_path else DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.executescript(_SCHEMA)

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(str(self.db_path))
        c.row_factory = sqlite3.Row
        return c

    # ── Layer 1: conversations ────────────────────────────────────────────
    def create_conversation(self, *, title: str = "", model: str = "",
                            project_id: str = "", tools: list[str] | None = None,
                            folder: str = "", tags: list[str] | None = None) -> dict:
        cid = _id()
        now = _now()
        with self._conn() as c:
            c.execute("INSERT INTO conversation(id,title,created_at,updated_at,model,"
                      "project_id,tools,folder,tags) VALUES(?,?,?,?,?,?,?,?,?)",
                      (cid, title, now, now, model, project_id,
                       json.dumps(tools or []), folder, json.dumps(tags or [])))
        return self.get_conversation(cid)

    def get_conversation(self, cid: str) -> Optional[dict]:
        with self._conn() as c:
            row = c.execute("SELECT * FROM conversation WHERE id=?", (cid,)).fetchone()
        return self._conv(row) if row else None

    def _conv(self, row) -> dict:
        d = dict(row)
        d["tags"] = json.loads(d.get("tags") or "[]")
        d["tools"] = json.loads(d.get("tools") or "[]")
        for k in ("archived", "deleted", "pinned", "favorite"):
            d[k] = bool(d[k])
        return d

    def update_conversation(self, cid: str, **fields) -> Optional[dict]:
        allowed = {"title", "summary", "folder", "model", "project_id"}
        flags = {"archived", "deleted", "pinned", "favorite"}
        json_fields = {"tags", "tools"}
        sets, args = ["updated_at=?"], [_now()]
        for k, v in fields.items():
            if k in allowed:
                sets.append(f"{k}=?"); args.append(v)
            elif k in flags:
                sets.append(f"{k}=?"); args.append(1 if v else 0)
            elif k in json_fields:
                sets.append(f"{k}=?"); args.append(json.dumps(v))
        args.append(cid)
        with self._conn() as c:
            c.execute(f"UPDATE conversation SET {','.join(sets)} WHERE id=?", args)
        return self.get_conversation(cid)

    def rename(self, cid: str, title: str) -> Optional[dict]:
        return self.update_conversation(cid, title=title)

    def archive(self, cid: str, flag: bool = True):
        return self.update_conversation(cid, archived=flag)

    def delete(self, cid: str):
        """Soft delete — restorable. Nothing is ever hard-lost."""
        return self.update_conversation(cid, deleted=True)

    def restore(self, cid: str):
        return self.update_conversation(cid, deleted=False, archived=False)

    def pin(self, cid: str, flag: bool = True):
        return self.update_conversation(cid, pinned=flag)

    def list_conversations(self, *, folder: str | None = None,
                           project_id: str | None = None,
                           include_archived: bool = False,
                           include_deleted: bool = False,
                           pinned_only: bool = False,
                           limit: int = 50, offset: int = 0) -> list[dict]:
        where, args = [], []
        if not include_deleted:
            where.append("deleted=0")
        if not include_archived:
            where.append("archived=0")
        if folder is not None:
            where.append("folder=?"); args.append(folder)
        if project_id is not None:
            where.append("project_id=?"); args.append(project_id)
        if pinned_only:
            where.append("pinned=1")
        sql = "SELECT * FROM conversation"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY pinned DESC, updated_at DESC LIMIT ? OFFSET ?"
        args += [limit, offset]
        with self._conn() as c:
            return [self._conv(r) for r in c.execute(sql, args).fetchall()]

    def search(self, query: str, *, limit: int = 20) -> list[dict]:
        """Search conversation titles/summaries and message content."""
        like = f"%{query}%"
        with self._conn() as c:
            convs = c.execute(
                "SELECT DISTINCT cv.* FROM conversation cv "
                "LEFT JOIN message m ON m.conversation_id=cv.id "
                "WHERE cv.deleted=0 AND (cv.title LIKE ? OR cv.summary LIKE ? "
                "OR m.content LIKE ?) ORDER BY cv.updated_at DESC LIMIT ?",
                (like, like, like, limit)).fetchall()
        return [self._conv(r) for r in convs]

    def add_tokens(self, cid: str, tokens_in: int = 0, tokens_out: int = 0):
        with self._conn() as c:
            c.execute("UPDATE conversation SET tokens_in=tokens_in+?, "
                      "tokens_out=tokens_out+?, updated_at=? WHERE id=?",
                      (tokens_in, tokens_out, _now(), cid))

    # ── Layer 2: messages ─────────────────────────────────────────────────
    def add_message(self, cid: str, role: str, content: str, *, model: str = "",
                    status: str = "complete", parent_id: str = "",
                    reasoning: str = "", tokens: int = 0,
                    meta: dict | None = None) -> dict:
        mid = _id()
        with self._conn() as c:
            c.execute("INSERT INTO message(id,conversation_id,role,content,created_at,"
                      "model,status,parent_id,reasoning,tokens,meta) "
                      "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                      (mid, cid, role, content, _now(), model, status, parent_id,
                       reasoning, tokens, json.dumps(meta or {})))
            c.execute("UPDATE conversation SET updated_at=? WHERE id=?", (_now(), cid))
        return self.get_message(mid)

    def get_message(self, mid: str) -> Optional[dict]:
        with self._conn() as c:
            row = c.execute("SELECT * FROM message WHERE id=?", (mid,)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["meta"] = json.loads(d.get("meta") or "{}")
        return d

    def edit_message(self, mid: str, new_content: str) -> dict:
        """Edit keeps version history: old row is superseded, new row chains."""
        old = self.get_message(mid)
        if not old:
            raise KeyError(mid)
        new = self.add_message(old["conversation_id"], old["role"], new_content,
                               model=old["model"], parent_id=mid)
        with self._conn() as c:
            c.execute("UPDATE message SET superseded_by=? WHERE id=?", (new["id"], mid))
        return new

    def message_versions(self, mid: str) -> list[dict]:
        """Walk the parent chain back to the original."""
        chain, cur = [], self.get_message(mid)
        while cur:
            chain.append(cur)
            cur = self.get_message(cur["parent_id"]) if cur["parent_id"] else None
        return list(reversed(chain))

    def list_messages(self, cid: str, *, limit: int = 200, offset: int = 0,
                      include_superseded: bool = False) -> list[dict]:
        sql = "SELECT * FROM message WHERE conversation_id=?"
        if not include_superseded:
            sql += " AND superseded_by=''"
        sql += " ORDER BY created_at ASC LIMIT ? OFFSET ?"
        with self._conn() as c:
            rows = c.execute(sql, (cid, limit, offset)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["meta"] = json.loads(d.get("meta") or "{}")
            out.append(d)
        return out

    # ── attachments / citations / memory links ────────────────────────────
    def add_attachment(self, cid: str, *, kind: str, name: str, path: str,
                       size: int = 0, message_id: str = "") -> dict:
        aid = _id()
        with self._conn() as c:
            c.execute("INSERT INTO attachment VALUES(?,?,?,?,?,?,?,?)",
                      (aid, cid, message_id, kind, name, path, size, _now()))
        return {"id": aid, "conversation_id": cid, "kind": kind, "name": name,
                "path": path, "size": size}

    def list_attachments(self, cid: str) -> list[dict]:
        with self._conn() as c:
            return [dict(r) for r in c.execute(
                "SELECT * FROM attachment WHERE conversation_id=?", (cid,)).fetchall()]

    def add_citation(self, message_id: str, *, source: str, chunk_ref: str = "",
                     quote: str = "") -> dict:
        cid_ = _id()
        with self._conn() as c:
            c.execute("INSERT INTO citation VALUES(?,?,?,?,?,?)",
                      (cid_, message_id, source, chunk_ref, quote, _now()))
        return {"id": cid_, "message_id": message_id, "source": source,
                "chunk_ref": chunk_ref, "quote": quote}

    def list_citations(self, message_id: str) -> list[dict]:
        with self._conn() as c:
            return [dict(r) for r in c.execute(
                "SELECT * FROM citation WHERE message_id=?", (message_id,)).fetchall()]

    def add_memory_link(self, cid: str, *, memory_kind: str, memory_ref: str,
                        relevance: float = 0.0) -> dict:
        lid = _id()
        with self._conn() as c:
            c.execute("INSERT INTO memory_link VALUES(?,?,?,?,?,?)",
                      (lid, cid, memory_kind, memory_ref, relevance, _now()))
        return {"id": lid, "conversation_id": cid, "memory_kind": memory_kind,
                "memory_ref": memory_ref, "relevance": relevance}

    def list_memory_links(self, cid: str) -> list[dict]:
        with self._conn() as c:
            return [dict(r) for r in c.execute(
                "SELECT * FROM memory_link WHERE conversation_id=? "
                "ORDER BY relevance DESC", (cid,)).fetchall()]

    # ── executions / tools / agents ───────────────────────────────────────
    def record_execution(self, message_id: str, *, intent_id: str, provider: str = "",
                         status: str = "", cost_usd: float = 0.0,
                         duration_sec: float = 0.0) -> dict:
        eid = _id()
        with self._conn() as c:
            c.execute("INSERT INTO execution VALUES(?,?,?,?,?,?,?,?)",
                      (eid, message_id, intent_id, provider, status, cost_usd,
                       duration_sec, _now()))
        return {"id": eid, "message_id": message_id, "intent_id": intent_id,
                "provider": provider, "status": status}

    def list_executions(self, cid: str) -> list[dict]:
        with self._conn() as c:
            return [dict(r) for r in c.execute(
                "SELECT e.* FROM execution e JOIN message m ON m.id=e.message_id "
                "WHERE m.conversation_id=? ORDER BY e.created_at", (cid,)).fetchall()]

    def record_tool(self, message_id: str, *, tool: str, args: dict,
                    intent_id: str = "") -> dict:
        tid = _id()
        with self._conn() as c:
            c.execute("INSERT INTO tool_invocation(id,message_id,tool,intent_id,args,"
                      "status,created_at) VALUES(?,?,?,?,?,?,?)",
                      (tid, message_id, tool, intent_id, json.dumps(args),
                       "pending", _now()))
        return {"id": tid, "tool": tool, "status": "pending"}

    def finish_tool(self, tid: str, *, status: str, result: str = "") -> None:
        with self._conn() as c:
            c.execute("UPDATE tool_invocation SET status=?, result=?, finished_at=? "
                      "WHERE id=?", (status, result, _now(), tid))

    def list_tools(self, message_id: str) -> list[dict]:
        with self._conn() as c:
            rows = c.execute("SELECT * FROM tool_invocation WHERE message_id=?",
                             (message_id,)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["args"] = json.loads(d.get("args") or "{}")
            out.append(d)
        return out

    def record_agent_run(self, cid: str, *, agent: str, task: str,
                         delegated_by: str = "") -> dict:
        rid = _id()
        with self._conn() as c:
            c.execute("INSERT INTO agent_run(id,conversation_id,agent,task,delegated_by,"
                      "status,created_at) VALUES(?,?,?,?,?,?,?)",
                      (rid, cid, agent, task, delegated_by, "running", _now()))
        return {"id": rid, "agent": agent, "task": task, "status": "running"}

    def finish_agent_run(self, rid: str, *, status: str,
                         result_message_id: str = "") -> None:
        with self._conn() as c:
            c.execute("UPDATE agent_run SET status=?, result_message_id=?, finished_at=? "
                      "WHERE id=?", (status, result_message_id, _now(), rid))

    def list_agent_runs(self, cid: str) -> list[dict]:
        with self._conn() as c:
            return [dict(r) for r in c.execute(
                "SELECT * FROM agent_run WHERE conversation_id=? ORDER BY created_at",
                (cid,)).fetchall()]

    # ── Layer 4: summaries + checkpoints ──────────────────────────────────
    def add_summary(self, cid: str, content: str, upto_message_id: str = "") -> dict:
        sid = _id()
        with self._conn() as c:
            c.execute("INSERT INTO summary VALUES(?,?,?,?,?)",
                      (sid, cid, content, upto_message_id, _now()))
            c.execute("UPDATE conversation SET summary=? WHERE id=?", (content, cid))
        return {"id": sid, "content": content}

    def create_checkpoint(self, cid: str, label: str = "") -> dict:
        snapshot = json.dumps({
            "conversation": self.get_conversation(cid),
            "messages": self.list_messages(cid, limit=10_000,
                                           include_superseded=True),
        }, default=str)
        kid = _id()
        with self._conn() as c:
            c.execute("INSERT INTO checkpoint VALUES(?,?,?,?,?)",
                      (kid, cid, label, snapshot, _now()))
        return {"id": kid, "conversation_id": cid, "label": label}

    def list_checkpoints(self, cid: str) -> list[dict]:
        with self._conn() as c:
            return [{"id": r["id"], "label": r["label"], "created_at": r["created_at"]}
                    for r in c.execute(
                        "SELECT id,label,created_at FROM checkpoint "
                        "WHERE conversation_id=? ORDER BY created_at DESC",
                        (cid,)).fetchall()]

    def restore_checkpoint(self, checkpoint_id: str) -> dict:
        """Restore a conversation to a checkpoint snapshot (messages replaced)."""
        with self._conn() as c:
            row = c.execute("SELECT * FROM checkpoint WHERE id=?",
                            (checkpoint_id,)).fetchone()
            if not row:
                raise KeyError(checkpoint_id)
            snap = json.loads(row["snapshot"])
            cid = row["conversation_id"]
            c.execute("DELETE FROM message WHERE conversation_id=?", (cid,))
            for m in snap["messages"]:
                c.execute("INSERT INTO message(id,conversation_id,role,content,"
                          "created_at,model,status,parent_id,superseded_by,reasoning,"
                          "tokens,meta) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                          (m["id"], cid, m["role"], m["content"], m["created_at"],
                           m.get("model", ""), m.get("status", "complete"),
                           m.get("parent_id", ""), m.get("superseded_by", ""),
                           m.get("reasoning", ""), m.get("tokens", 0),
                           json.dumps(m.get("meta", {}))))
            c.execute("UPDATE conversation SET updated_at=? WHERE id=?", (_now(), cid))
        return {"restored": True, "conversation_id": cid,
                "messages": len(snap["messages"])}

    # ── Layer 8: project references ───────────────────────────────────────
    def add_project_ref(self, project_id: str, *, kind: str, ref: str) -> dict:
        pid = _id()
        with self._conn() as c:
            c.execute("INSERT INTO project_ref VALUES(?,?,?,?,?)",
                      (pid, project_id, kind, ref, _now()))
        return {"id": pid, "project_id": project_id, "kind": kind, "ref": ref}

    def list_project_refs(self, project_id: str) -> list[dict]:
        with self._conn() as c:
            return [dict(r) for r in c.execute(
                "SELECT * FROM project_ref WHERE project_id=?", (project_id,)).fetchall()]


_default: ChatStore | None = None


def default_store() -> ChatStore:
    global _default
    if _default is None:
        _default = ChatStore()
    return _default
