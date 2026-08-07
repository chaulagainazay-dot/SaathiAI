"""IELTS persistence adapter over the existing serialized PlatformStore connection."""
from __future__ import annotations

import json
import sqlite3
from typing import Any

from saathi.platform.models import new_id

from .models import IELTSRecord


class IELTSRepository:
    def __init__(self, platform_store):
        self.store = platform_store

    def create(self, *, record_type: str, org_id: str, workspace_id: str, owner_id: str,
               status: str, body: dict[str, Any], project_id: str = "", mission_id: str = "",
               idempotency_key: str = "") -> IELTSRecord:
        now = self.store._now()
        record = IELTSRecord(
            record_id=new_id("ielts_"), record_type=record_type, org_id=org_id,
            workspace_id=workspace_id, owner_id=owner_id, project_id=project_id,
            mission_id=mission_id, status=status, body=body,
            idempotency_key=idempotency_key[:120], created_at=now, updated_at=now,
        )
        try:
            self.store._conn.execute(
                "INSERT INTO ielts_records (record_id,record_type,org_id,workspace_id,owner_id,"
                "project_id,mission_id,status,body_json,idempotency_key,version,created_at,updated_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (record.record_id, record.record_type, record.org_id, record.workspace_id,
                 record.owner_id, record.project_id, record.mission_id, record.status,
                 json.dumps(record.body, sort_keys=True, separators=(",", ":")),
                 record.idempotency_key, record.version, now, now),
            )
            self.store._conn.commit()
        except sqlite3.IntegrityError:
            if not idempotency_key:
                raise
            existing = self.find_idempotent(
                org_id=org_id, workspace_id=workspace_id, owner_id=owner_id,
                record_type=record_type, idempotency_key=idempotency_key,
            )
            if existing:
                return existing
            raise
        return record

    def find_idempotent(self, **scope) -> IELTSRecord | None:
        row = self.store._conn.execute(
            "SELECT * FROM ielts_records WHERE org_id=? AND workspace_id=? AND owner_id=?"
            " AND record_type=? AND idempotency_key=?",
            (scope["org_id"], scope["workspace_id"], scope["owner_id"],
             scope["record_type"], scope["idempotency_key"][:120]),
        ).fetchone()
        return self._row(row) if row else None

    def get(self, record_id: str, *, org_id: str, workspace_id: str) -> IELTSRecord | None:
        row = self.store._conn.execute(
            "SELECT * FROM ielts_records WHERE record_id=? AND org_id=? AND workspace_id=?",
            (record_id, org_id, workspace_id),
        ).fetchone()
        return self._row(row) if row else None

    def list(self, *, org_id: str, workspace_id: str, record_type: str = "",
             owner_id: str = "", limit: int = 200) -> list[IELTSRecord]:
        sql = "SELECT * FROM ielts_records WHERE org_id=? AND workspace_id=? AND archived_at=0"
        args: list[Any] = [org_id, workspace_id]
        if record_type:
            sql += " AND record_type=?"
            args.append(record_type)
        if owner_id:
            sql += " AND owner_id=?"
            args.append(owner_id)
        sql += " ORDER BY updated_at DESC, record_id LIMIT ?"
        args.append(max(1, min(int(limit), 500)))
        return [self._row(row) for row in self.store._conn.execute(sql, args).fetchall()]

    def transition(self, record: IELTSRecord, *, status: str, body_updates: dict[str, Any] | None = None) -> IELTSRecord:
        body = {**record.body, **(body_updates or {})}
        now = self.store._now()
        cur = self.store._conn.execute(
            "UPDATE ielts_records SET status=?,body_json=?,version=version+1,updated_at=?"
            " WHERE record_id=? AND version=? AND org_id=? AND workspace_id=?",
            (status, json.dumps(body, sort_keys=True, separators=(",", ":")), now,
             record.record_id, record.version, record.org_id, record.workspace_id),
        )
        self.store._conn.commit()
        if cur.rowcount != 1:
            raise RuntimeError("IELTS record update conflict")
        updated = self.get(record.record_id, org_id=record.org_id, workspace_id=record.workspace_id)
        if not updated:
            raise RuntimeError("IELTS record disappeared")
        return updated

    def evidence(self, *, record: IELTSRecord, event_type: str, summary: str, evidence_ref: str = "") -> dict:
        event_id = new_id("ielev_")
        now = self.store._now()
        self.store._conn.execute(
            "INSERT INTO ielts_evidence_events (event_id,org_id,workspace_id,owner_id,"
            "record_id,event_type,evidence_ref,summary,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (event_id, record.org_id, record.workspace_id, record.owner_id, record.record_id,
             event_type[:80], evidence_ref[:500], summary[:500], now),
        )
        self.store._conn.commit()
        return {"event_id": event_id, "record_id": record.record_id, "event_type": event_type,
                "evidence_ref": evidence_ref[:500], "summary": summary[:500], "created_at": now}

    def timeline(self, *, org_id: str, workspace_id: str, owner_id: str = "", limit: int = 200) -> list[dict]:
        sql = "SELECT * FROM ielts_evidence_events WHERE org_id=? AND workspace_id=?"
        args: list[Any] = [org_id, workspace_id]
        if owner_id:
            sql += " AND owner_id=?"
            args.append(owner_id)
        sql += " ORDER BY created_at DESC,event_id LIMIT ?"
        args.append(max(1, min(int(limit), 500)))
        return [dict(row) for row in self.store._conn.execute(sql, args).fetchall()]

    @staticmethod
    def _row(row) -> IELTSRecord:
        return IELTSRecord(
            record_id=row["record_id"], record_type=row["record_type"], org_id=row["org_id"],
            workspace_id=row["workspace_id"], owner_id=row["owner_id"],
            project_id=row["project_id"] or "", mission_id=row["mission_id"] or "",
            status=row["status"], body=json.loads(row["body_json"] or "{}"),
            idempotency_key=row["idempotency_key"] or "", version=int(row["version"]),
            created_at=float(row["created_at"]), updated_at=float(row["updated_at"]),
            archived_at=float(row["archived_at"] or 0),
        )
