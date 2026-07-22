"""M20.5 — Canonical Engineering Session Ledger.

Append-only, hash-chained event log for engineering sessions and integrity
evidence references. This is **not** the harness RunLedger (M17.9) and does not
schedule work or execute tools.

Authority:
  - sessions.json remains mutable session *state*
  - session_ledger.jsonl is immutable evidence *history*
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterator, Optional

# Well-known event types (extend, never rewrite meanings)
EVENT_TYPES = frozenset({
    "session_created",
    "session_started",
    "session_heartbeat",
    "session_status",
    "checkpoint",
    "integrity_baseline",
    "integrity_check",
    "integrity_violation",
    "quarantine",
    "approval_bound",
    "approval_consumed",
    "validation",
    "retry",
    "stop",
    "recovery_scan",
    "recovery_action",
    "handoff",
    "note",
})

TERMINAL_SESSION_STATUSES = frozenset({
    "completed", "failed", "stopped", "crashed", "timed_out",
    "terminated", "usage_limit", "cancelled",
})


def _fp_payload(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass
class LedgerEvent:
    event_id: str
    seq: int
    ts: float
    event_type: str
    session_id: str = ""
    task_id: str = ""
    item_id: str = ""
    prev_hash: str = ""
    entry_hash: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    evidence_ref: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "LedgerEvent":
        return cls(
            event_id=str(d.get("event_id") or ""),
            seq=int(d.get("seq") or 0),
            ts=float(d.get("ts") or 0),
            event_type=str(d.get("event_type") or ""),
            session_id=str(d.get("session_id") or ""),
            task_id=str(d.get("task_id") or ""),
            item_id=str(d.get("item_id") or ""),
            prev_hash=str(d.get("prev_hash") or ""),
            entry_hash=str(d.get("entry_hash") or ""),
            payload=dict(d.get("payload") or {}),
            evidence_ref=str(d.get("evidence_ref") or ""),
        )


class SessionLedger:
    """Append-only JSONL ledger with optional hash chain verification."""

    SCHEMA = "engineering_session_ledger.v1"

    def __init__(self, root: Path | str):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "session_ledger.jsonl"
        self.meta_path = self.root / "session_ledger_meta.json"
        self._ensure_meta()

    def _ensure_meta(self) -> None:
        if not self.meta_path.exists():
            self._write_meta({"schema": self.SCHEMA, "next_seq": 1, "last_hash": ""})

    def _write_meta(self, meta: dict[str, Any]) -> None:
        tmp = self.meta_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        os.replace(tmp, self.meta_path)

    def _read_meta(self) -> dict[str, Any]:
        if not self.meta_path.exists():
            return {"schema": self.SCHEMA, "next_seq": 1, "last_hash": ""}
        try:
            return json.loads(self.meta_path.read_text(encoding="utf-8"))
        except Exception:
            return {"schema": self.SCHEMA, "next_seq": 1, "last_hash": "", "corrupt_meta": True}

    def append(
        self,
        event_type: str,
        *,
        session_id: str = "",
        task_id: str = "",
        item_id: str = "",
        payload: Optional[dict[str, Any]] = None,
        evidence_ref: str = "",
    ) -> LedgerEvent:
        if event_type not in EVENT_TYPES:
            raise ValueError(f"unknown_event_type:{event_type}")
        # Strip sensitive keys from payload
        clean = _sanitize_payload(payload or {})
        meta = self._read_meta()
        seq = int(meta.get("next_seq") or 1)
        prev = str(meta.get("last_hash") or "")
        event_id = f"lev_{seq:08d}_{hashlib.sha256(f'{seq}{time.time()}'.encode()).hexdigest()[:10]}"
        body = {
            "event_id": event_id,
            "seq": seq,
            "ts": time.time(),
            "event_type": event_type,
            "session_id": session_id,
            "task_id": task_id,
            "item_id": item_id,
            "prev_hash": prev,
            "payload": clean,
            "evidence_ref": evidence_ref,
            "schema": self.SCHEMA,
        }
        entry_hash = "sha256:" + _fp_payload({k: v for k, v in body.items() if k != "entry_hash"})
        body["entry_hash"] = entry_hash
        line = json.dumps(body, default=str, separators=(",", ":"))
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
            f.flush()
            try:
                os.fsync(f.fileno())
            except Exception:
                pass
        meta["next_seq"] = seq + 1
        meta["last_hash"] = entry_hash
        self._write_meta(meta)
        return LedgerEvent.from_dict(body)

    def iter_events(
        self,
        *,
        session_id: str = "",
        event_type: str = "",
        limit: int = 0,
    ) -> Iterator[LedgerEvent]:
        if not self.path.exists():
            return
            yield  # pragma: no cover
        count = 0
        with open(self.path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if session_id and d.get("session_id") != session_id:
                    continue
                if event_type and d.get("event_type") != event_type:
                    continue
                yield LedgerEvent.from_dict(d)
                count += 1
                if limit and count >= limit:
                    return

    def list_events(
        self,
        *,
        session_id: str = "",
        event_type: str = "",
        limit: int = 100,
        newest_first: bool = True,
    ) -> list[LedgerEvent]:
        events = list(self.iter_events(session_id=session_id, event_type=event_type))
        if newest_first:
            events.reverse()
        if limit:
            events = events[:limit]
        return events

    def verify_chain(self) -> dict[str, Any]:
        """Verify hash chain integrity. Fail-closed on break."""
        prev = ""
        n = 0
        broken_at: Optional[int] = None
        last_err = ""
        for ev in self.iter_events():
            n += 1
            body = {
                "event_id": ev.event_id,
                "seq": ev.seq,
                "ts": ev.ts,
                "event_type": ev.event_type,
                "session_id": ev.session_id,
                "task_id": ev.task_id,
                "item_id": ev.item_id,
                "prev_hash": ev.prev_hash,
                "payload": ev.payload,
                "evidence_ref": ev.evidence_ref,
                "schema": self.SCHEMA,
            }
            expect = "sha256:" + _fp_payload(body)
            if ev.prev_hash != prev:
                broken_at = ev.seq
                last_err = "prev_hash_mismatch"
                break
            if ev.entry_hash != expect:
                # recompute allowing missing schema in old rows
                body_alt = dict(body)
                expect2 = "sha256:" + _fp_payload(body_alt)
                if ev.entry_hash != expect2:
                    broken_at = ev.seq
                    last_err = "entry_hash_mismatch"
                    break
            prev = ev.entry_hash
        return {
            "ok": broken_at is None,
            "events": n,
            "broken_at_seq": broken_at,
            "error": last_err,
            "last_hash": prev,
            "schema": self.SCHEMA,
        }

    def session_timeline(self, session_id: str) -> list[dict[str, Any]]:
        return [e.to_dict() for e in self.list_events(session_id=session_id, limit=500, newest_first=False)]

    def census(self) -> dict[str, Any]:
        by_type: dict[str, int] = {}
        sessions: set[str] = set()
        for ev in self.iter_events():
            by_type[ev.event_type] = by_type.get(ev.event_type, 0) + 1
            if ev.session_id:
                sessions.add(ev.session_id)
        chain = self.verify_chain()
        return {
            "schema": self.SCHEMA,
            "path": str(self.path),
            "event_counts": by_type,
            "session_count": len(sessions),
            "chain_ok": chain["ok"],
            "total_events": chain["events"],
        }


def _sanitize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    banned = {
        "prompt", "output", "stdout", "stderr", "token", "secret", "password",
        "api_key", "authorization", "cookie",
    }
    out: dict[str, Any] = {}
    for k, v in payload.items():
        lk = str(k).lower()
        if any(b in lk for b in banned):
            out[k] = "[redacted]"
            continue
        if isinstance(v, str) and len(v) > 2000:
            out[k] = v[:2000] + "…[truncated]"
        elif isinstance(v, dict):
            out[k] = _sanitize_payload(v)
        else:
            out[k] = v
    return out


def default_ledger(store_root: Path | str) -> SessionLedger:
    return SessionLedger(store_root)
