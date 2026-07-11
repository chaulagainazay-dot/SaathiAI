"""M12 Voice OS durable store — data/voice_os.db.

Ten tables. Raw audio is never persisted by default — only references/metadata
unless a session's settings explicitly opt into retention. Every session is
owned by a user; every read/write is ownership-checked by the API layer.
"""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Optional

from saathi.voice_os.models import SessionState, validate_transition

ROOT = Path(__file__).resolve().parent.parent.parent
DB_PATH = ROOT / "data" / "voice_os.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS voice_session(
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL, conversation_id TEXT DEFAULT '',
  project_id TEXT DEFAULT '', chat_mode TEXT DEFAULT 'solo', agent TEXT DEFAULT '',
  strategy TEXT DEFAULT '', input_language TEXT DEFAULT 'en',
  output_language TEXT DEFAULT 'en', stt_provider TEXT DEFAULT '',
  tts_provider TEXT DEFAULT '', voice TEXT DEFAULT 'default',
  audio_format TEXT DEFAULT 'webm', sample_rate INTEGER DEFAULT 16000,
  state TEXT NOT NULL, active_turn_id TEXT DEFAULT '', active_execution_id TEXT DEFAULT '',
  interruption_count INTEGER DEFAULT 0, privacy TEXT DEFAULT 'standard',
  retain_raw_audio INTEGER DEFAULT 0, settings TEXT DEFAULT '{}',
  error_state TEXT DEFAULT '', started_at REAL, last_activity REAL, ended_at REAL DEFAULT 0);
CREATE TABLE IF NOT EXISTS voice_turn(
  id TEXT PRIMARY KEY, session_id TEXT, conversation_id TEXT DEFAULT '',
  final_transcript TEXT DEFAULT '', transcript_confidence REAL DEFAULT 0,
  detected_language TEXT DEFAULT '', normalized_text TEXT DEFAULT '',
  chat_message_id TEXT DEFAULT '', execution_id TEXT DEFAULT '',
  agent_run_id TEXT DEFAULT '', assistant_text TEXT DEFAULT '',
  playback_state TEXT DEFAULT 'pending', interrupted INTEGER DEFAULT 0,
  latency TEXT DEFAULT '{}', error TEXT DEFAULT '',
  created_at REAL, finished_at REAL DEFAULT 0);
CREATE TABLE IF NOT EXISTS transcript_fragment(
  id TEXT PRIMARY KEY, turn_id TEXT, kind TEXT, text TEXT,
  confidence REAL DEFAULT 0, created_at REAL);
CREATE TABLE IF NOT EXISTS audio_segment(
  id TEXT PRIMARY KEY, turn_id TEXT, direction TEXT, ref TEXT DEFAULT '',
  duration_sec REAL DEFAULT 0, retained INTEGER DEFAULT 0, created_at REAL);
CREATE TABLE IF NOT EXISTS playback_event(
  id TEXT PRIMARY KEY, turn_id TEXT, kind TEXT, detail TEXT DEFAULT '', created_at REAL);
CREATE TABLE IF NOT EXISTS interruption(
  id TEXT PRIMARY KEY, session_id TEXT, turn_id TEXT, stop_latency_ms REAL DEFAULT 0,
  created_at REAL);
CREATE TABLE IF NOT EXISTS voice_preference(
  id TEXT PRIMARY KEY, user_id TEXT UNIQUE, settings TEXT DEFAULT '{}', updated_at REAL);
CREATE TABLE IF NOT EXISTS provider_event(
  id TEXT PRIMARY KEY, session_id TEXT, provider TEXT, kind TEXT, ok INTEGER,
  detail TEXT DEFAULT '', created_at REAL);
CREATE TABLE IF NOT EXISTS voice_error(
  id TEXT PRIMARY KEY, session_id TEXT, turn_id TEXT DEFAULT '', kind TEXT,
  message TEXT, created_at REAL);
CREATE TABLE IF NOT EXISTS latency_measurement(
  id TEXT PRIMARY KEY, turn_id TEXT, metric TEXT, value_ms REAL, created_at REAL);
CREATE INDEX IF NOT EXISTS idx_turn_session ON voice_turn(session_id, created_at);
CREATE INDEX IF NOT EXISTS idx_session_user ON voice_session(user_id, started_at);
"""


def _now() -> float:
    return time.time()


def _id() -> str:
    return "v_" + uuid.uuid4().hex[:16]


class VoiceStore:
    def __init__(self, db_path: str | Path | None = None):
        self.db_path = Path(db_path) if db_path else DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.executescript(_SCHEMA)

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(str(self.db_path))
        c.row_factory = sqlite3.Row
        return c

    # ── sessions ──────────────────────────────────────────────────────────
    def create_session(self, *, user_id: str, conversation_id: str = "",
                       project_id: str = "", chat_mode: str = "solo",
                       agent: str = "", strategy: str = "",
                       settings: dict | None = None) -> str:
        sid = _id()
        now = _now()
        st = settings or {}
        with self._conn() as c:
            c.execute("INSERT INTO voice_session(id,user_id,conversation_id,project_id,"
                      "chat_mode,agent,strategy,state,settings,retain_raw_audio,"
                      "started_at,last_activity) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                      (sid, user_id, conversation_id, project_id, chat_mode, agent,
                       strategy, SessionState.CREATED.value, json.dumps(st),
                       1 if st.get("retain_raw_audio") else 0, now, now))
        self.event(sid, "voice.session.created", {"user_id": user_id})
        return sid

    def get_session(self, sid: str) -> Optional[dict]:
        with self._conn() as c:
            row = c.execute("SELECT * FROM voice_session WHERE id=?", (sid,)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["settings"] = json.loads(d.get("settings") or "{}")
        d["retain_raw_audio"] = bool(d["retain_raw_audio"])
        return d

    def owns(self, sid: str, user_id: str) -> bool:
        s = self.get_session(sid)
        return bool(s and s["user_id"] == user_id)

    def transition(self, sid: str, dst: SessionState, *, actor: str = "system") -> None:
        s = self.get_session(sid)
        if not s:
            raise KeyError(sid)
        src = SessionState(s["state"])
        validate_transition(src, dst)
        with self._conn() as c:
            c.execute("UPDATE voice_session SET state=?, last_activity=? WHERE id=?",
                      (dst.value, _now(), sid))
        self.event(sid, "voice.session.state", {"from": src.value, "to": dst.value,
                                                 "actor": actor})

    def set_conversation(self, sid: str, conversation_id: str) -> None:
        with self._conn() as c:
            c.execute("UPDATE voice_session SET conversation_id=? WHERE id=?",
                      (conversation_id, sid))

    def end_session(self, sid: str) -> None:
        with self._conn() as c:
            c.execute("UPDATE voice_session SET ended_at=? WHERE id=?", (_now(), sid))

    def list_sessions(self, *, user_id: str | None = None, limit: int = 50) -> list[dict]:
        where, args = "", []
        if user_id:
            where = " WHERE user_id=?"
            args.append(user_id)
        args.append(limit)
        with self._conn() as c:
            return [dict(r) for r in c.execute(
                f"SELECT id,user_id,conversation_id,state,chat_mode,started_at,ended_at "
                f"FROM voice_session{where} ORDER BY started_at DESC LIMIT ?", args).fetchall()]

    def bump_interruption(self, sid: str) -> None:
        with self._conn() as c:
            c.execute("UPDATE voice_session SET interruption_count=interruption_count+1 "
                      "WHERE id=?", (sid,))

    def set_active(self, sid: str, *, turn_id: str = None, execution_id: str = None) -> None:
        sets, args = [], []
        if turn_id is not None:
            sets.append("active_turn_id=?"); args.append(turn_id)
        if execution_id is not None:
            sets.append("active_execution_id=?"); args.append(execution_id)
        if not sets:
            return
        args.append(sid)
        with self._conn() as c:
            c.execute(f"UPDATE voice_session SET {','.join(sets)} WHERE id=?", args)

    # ── turns ─────────────────────────────────────────────────────────────
    def create_turn(self, sid: str, *, conversation_id: str = "") -> str:
        tid = _id()
        with self._conn() as c:
            c.execute("INSERT INTO voice_turn(id,session_id,conversation_id,created_at) "
                      "VALUES(?,?,?,?)", (tid, sid, conversation_id, _now()))
        self.set_active(sid, turn_id=tid)
        return tid

    def get_turn(self, tid: str) -> Optional[dict]:
        with self._conn() as c:
            row = c.execute("SELECT * FROM voice_turn WHERE id=?", (tid,)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["latency"] = json.loads(d.get("latency") or "{}")
        d["interrupted"] = bool(d["interrupted"])
        return d

    def update_turn(self, tid: str, **fields) -> None:
        cols = {"final_transcript", "transcript_confidence", "detected_language",
                "normalized_text", "chat_message_id", "execution_id", "agent_run_id",
                "assistant_text", "playback_state", "interrupted", "error"}
        sets, args = [], []
        for k, v in fields.items():
            if k == "latency":
                sets.append("latency=?"); args.append(json.dumps(v))
            elif k in cols:
                sets.append(f"{k}=?")
                args.append(int(v) if k == "interrupted" else v)
        if not sets:
            return
        args.append(tid)
        with self._conn() as c:
            c.execute(f"UPDATE voice_turn SET {','.join(sets)} WHERE id=?", args)

    def finish_turn(self, tid: str) -> None:
        with self._conn() as c:
            c.execute("UPDATE voice_turn SET finished_at=? WHERE id=?", (_now(), tid))

    def list_turns(self, sid: str) -> list[dict]:
        with self._conn() as c:
            rows = c.execute("SELECT * FROM voice_turn WHERE session_id=? "
                             "ORDER BY created_at", (sid,)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["latency"] = json.loads(d.get("latency") or "{}")
            d["interrupted"] = bool(d["interrupted"])
            out.append(d)
        return out

    # ── transcript fragments ─────────────────────────────────────────────
    def add_fragment(self, tid: str, *, kind: str, text: str, confidence: float = 0.0) -> None:
        with self._conn() as c:
            c.execute("INSERT INTO transcript_fragment VALUES(?,?,?,?,?,?)",
                      (_id(), tid, kind, text, confidence, _now()))

    def fragments(self, tid: str) -> list[dict]:
        with self._conn() as c:
            return [dict(r) for r in c.execute(
                "SELECT * FROM transcript_fragment WHERE turn_id=? ORDER BY created_at",
                (tid,)).fetchall()]

    # ── audio segments (reference-only unless retention enabled) ──────────
    def add_audio_segment(self, tid: str, *, direction: str, ref: str = "",
                          duration_sec: float = 0.0, retained: bool = False) -> None:
        with self._conn() as c:
            c.execute("INSERT INTO audio_segment VALUES(?,?,?,?,?,?,?)",
                      (_id(), tid, direction, ref, duration_sec, 1 if retained else 0, _now()))

    def audio_segments(self, tid: str) -> list[dict]:
        with self._conn() as c:
            return [dict(r) for r in c.execute(
                "SELECT * FROM audio_segment WHERE turn_id=?", (tid,)).fetchall()]

    # ── playback / interruption ────────────────────────────────────────────
    def add_playback_event(self, tid: str, kind: str, detail: str = "") -> None:
        with self._conn() as c:
            c.execute("INSERT INTO playback_event VALUES(?,?,?,?,?)",
                      (_id(), tid, kind, detail, _now()))

    def playback_events(self, tid: str) -> list[dict]:
        with self._conn() as c:
            return [dict(r) for r in c.execute(
                "SELECT * FROM playback_event WHERE turn_id=? ORDER BY created_at",
                (tid,)).fetchall()]

    def record_interruption(self, sid: str, tid: str, stop_latency_ms: float) -> None:
        with self._conn() as c:
            c.execute("INSERT INTO interruption VALUES(?,?,?,?,?)",
                      (_id(), sid, tid, stop_latency_ms, _now()))
        self.bump_interruption(sid)

    def interruptions(self, sid: str) -> list[dict]:
        with self._conn() as c:
            return [dict(r) for r in c.execute(
                "SELECT * FROM interruption WHERE session_id=?", (sid,)).fetchall()]

    # ── preferences ─────────────────────────────────────────────────────────
    def get_preferences(self, user_id: str) -> dict:
        with self._conn() as c:
            row = c.execute("SELECT * FROM voice_preference WHERE user_id=?",
                            (user_id,)).fetchone()
        return json.loads(row["settings"]) if row else {}

    def set_preferences(self, user_id: str, settings: dict) -> None:
        with self._conn() as c:
            c.execute("INSERT INTO voice_preference(id,user_id,settings,updated_at) "
                      "VALUES(?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET "
                      "settings=excluded.settings, updated_at=excluded.updated_at",
                      (_id(), user_id, json.dumps(settings), _now()))

    # ── provider / error / latency ───────────────────────────────────────
    def record_provider_event(self, sid: str, provider: str, kind: str, ok: bool,
                              detail: str = "") -> None:
        with self._conn() as c:
            c.execute("INSERT INTO provider_event VALUES(?,?,?,?,?,?,?)",
                      (_id(), sid, provider, kind, 1 if ok else 0, detail, _now()))

    def provider_events(self, sid: str) -> list[dict]:
        with self._conn() as c:
            return [dict(r) for r in c.execute(
                "SELECT * FROM provider_event WHERE session_id=? ORDER BY created_at DESC",
                (sid,)).fetchall()]

    def record_error(self, sid: str, kind: str, message: str, tid: str = "") -> None:
        with self._conn() as c:
            c.execute("INSERT INTO voice_error VALUES(?,?,?,?,?,?)",
                      (_id(), sid, tid, kind, message[:500], _now()))
            c.execute("UPDATE voice_session SET error_state=? WHERE id=?",
                      (f"{kind}: {message[:200]}", sid))

    def record_latency(self, tid: str, metric: str, value_ms: float) -> None:
        with self._conn() as c:
            c.execute("INSERT INTO latency_measurement VALUES(?,?,?,?,?)",
                      (_id(), tid, metric, value_ms, _now()))

    def latencies(self, tid: str) -> list[dict]:
        with self._conn() as c:
            return [dict(r) for r in c.execute(
                "SELECT * FROM latency_measurement WHERE turn_id=?", (tid,)).fetchall()]

    # ── events (mirrors to the fabric bus, never breaks session state) ────
    def event(self, sid: str, name: str, payload: dict | None = None) -> None:
        try:
            from saathi.events import bus
            bus.publish_sync(name, {"session_id": sid, **(payload or {})})
        except Exception:
            pass


_default: VoiceStore | None = None


def default_store() -> VoiceStore:
    global _default
    if _default is None:
        _default = VoiceStore()
    return _default
