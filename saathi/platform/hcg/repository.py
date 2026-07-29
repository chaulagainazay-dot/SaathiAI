"""HCG persistence over PlatformStore SQLite (workspace-isolated records)."""
from __future__ import annotations

import json
import sqlite3
from typing import Any

from saathi.platform.models import new_id

from .models import FINANCIAL_IMMUTABLE_TYPES, HcgRecord, HcgValidationError


class HcgRepository:
    def __init__(self, platform_store):
        self.store = platform_store

    def create(self, *, record_type: str, org_id: str, workspace_id: str,
               app_instance_id: str, body: dict[str, Any], status: str = "ACTIVE",
               location_id: str = "", created_by: str = "", idempotency_key: str = "",
               demo: bool = False, reverses_id: str = "", audit_ref: str = "") -> HcgRecord:
        now = self.store._now()
        record = HcgRecord(
            record_id=new_id("hcg_"),
            record_type=record_type,
            org_id=org_id,
            workspace_id=workspace_id,
            app_instance_id=app_instance_id,
            location_id=location_id,
            status=status,
            body=body,
            idempotency_key=(idempotency_key or "")[:120],
            created_at=now,
            updated_at=now,
            created_by=created_by,
            updated_by=created_by,
            demo=demo,
            reverses_id=reverses_id,
            audit_ref=audit_ref,
        )
        try:
            self.store._conn.execute(
                "INSERT INTO hcg_records (record_id,record_type,org_id,workspace_id,app_instance_id,"
                "location_id,status,body_json,idempotency_key,version,created_at,updated_at,"
                "created_by,updated_by,audit_ref,reversed_by,reverses_id,archived_at,demo)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    record.record_id, record.record_type, record.org_id, record.workspace_id,
                    record.app_instance_id, record.location_id, record.status,
                    json.dumps(record.body, sort_keys=True, separators=(",", ":")),
                    record.idempotency_key, record.version, now, now,
                    record.created_by, record.updated_by, record.audit_ref,
                    record.reversed_by, record.reverses_id, 0, 1 if demo else 0,
                ),
            )
            self.store._conn.commit()
        except sqlite3.IntegrityError:
            if not idempotency_key:
                raise
            existing = self.find_idempotent(
                org_id=org_id, workspace_id=workspace_id, app_instance_id=app_instance_id,
                record_type=record_type, idempotency_key=idempotency_key,
            )
            if existing:
                return existing
            raise
        return record

    def find_idempotent(self, **scope) -> HcgRecord | None:
        row = self.store._conn.execute(
            "SELECT * FROM hcg_records WHERE org_id=? AND workspace_id=? AND app_instance_id=?"
            " AND record_type=? AND idempotency_key=? AND archived_at=0",
            (
                scope["org_id"], scope["workspace_id"], scope["app_instance_id"],
                scope["record_type"], scope["idempotency_key"][:120],
            ),
        ).fetchone()
        return self._row(row) if row else None

    def get(self, record_id: str, *, org_id: str, workspace_id: str,
            app_instance_id: str = "") -> HcgRecord | None:
        sql = "SELECT * FROM hcg_records WHERE record_id=? AND org_id=? AND workspace_id=?"
        args: list[Any] = [record_id, org_id, workspace_id]
        if app_instance_id:
            sql += " AND app_instance_id=?"
            args.append(app_instance_id)
        row = self.store._conn.execute(sql, args).fetchone()
        return self._row(row) if row else None

    def list(
        self,
        *,
        org_id: str,
        workspace_id: str,
        app_instance_id: str = "",
        record_type: str = "",
        status: str = "",
        location_id: str = "",
        q: str = "",
        limit: int = 200,
        offset: int = 0,
        include_archived: bool = False,
    ) -> list[HcgRecord]:
        sql = "SELECT * FROM hcg_records WHERE org_id=? AND workspace_id=?"
        args: list[Any] = [org_id, workspace_id]
        if not include_archived:
            sql += " AND archived_at=0"
        if app_instance_id:
            sql += " AND app_instance_id=?"
            args.append(app_instance_id)
        if record_type:
            sql += " AND record_type=?"
            args.append(record_type)
        if status:
            sql += " AND status=?"
            args.append(status)
        if location_id:
            sql += " AND location_id=?"
            args.append(location_id)
        if q:
            sql += " AND (record_id LIKE ? OR body_json LIKE ? OR status LIKE ?)"
            like = f"%{q[:80]}%"
            args.extend([like, like, like])
        sql += " ORDER BY updated_at DESC, record_id LIMIT ? OFFSET ?"
        args.append(max(1, min(int(limit), 500)))
        args.append(max(0, int(offset)))
        return [self._row(row) for row in self.store._conn.execute(sql, args).fetchall()]

    def count(
        self,
        *,
        org_id: str,
        workspace_id: str,
        app_instance_id: str = "",
        record_type: str = "",
        status: str = "",
    ) -> int:
        sql = "SELECT COUNT(*) AS c FROM hcg_records WHERE org_id=? AND workspace_id=? AND archived_at=0"
        args: list[Any] = [org_id, workspace_id]
        if app_instance_id:
            sql += " AND app_instance_id=?"
            args.append(app_instance_id)
        if record_type:
            sql += " AND record_type=?"
            args.append(record_type)
        if status:
            sql += " AND status=?"
            args.append(status)
        row = self.store._conn.execute(sql, args).fetchone()
        return int(row["c"] if row else 0)

    def update_mutable(
        self,
        record: HcgRecord,
        *,
        status: str | None = None,
        body_updates: dict[str, Any] | None = None,
        updated_by: str = "",
        audit_ref: str = "",
        reversed_by: str = "",
        allow_financial_status: bool = False,
    ) -> HcgRecord:
        """Update non-financial or allowed status fields. Never silently rewrite completed financials."""
        if record.record_type in FINANCIAL_IMMUTABLE_TYPES and body_updates and not allow_financial_status:
            # Only status/reversed_by markers permitted for financial rows
            raise HcgValidationError(
                "FINANCIAL_IMMUTABLE",
                "completed financial records cannot be silently edited; use reversal/correction",
            )
        body = {**record.body, **(body_updates or {})} if body_updates is not None else dict(record.body)
        new_status = status if status is not None else record.status
        now = self.store._now()
        cur = self.store._conn.execute(
            "UPDATE hcg_records SET status=?, body_json=?, version=version+1, updated_at=?,"
            " updated_by=?, audit_ref=?, reversed_by=?"
            " WHERE record_id=? AND version=? AND org_id=? AND workspace_id=?",
            (
                new_status,
                json.dumps(body, sort_keys=True, separators=(",", ":")),
                now,
                updated_by or record.updated_by,
                audit_ref or record.audit_ref,
                reversed_by or record.reversed_by,
                record.record_id,
                record.version,
                record.org_id,
                record.workspace_id,
            ),
        )
        self.store._conn.commit()
        if cur.rowcount != 1:
            raise HcgValidationError("VERSION_CONFLICT", "record update conflict")
        updated = self.get(
            record.record_id, org_id=record.org_id, workspace_id=record.workspace_id,
            app_instance_id=record.app_instance_id,
        )
        if not updated:
            raise HcgValidationError("NOT_FOUND", "record disappeared")
        return updated

    def mark_reversed(self, record: HcgRecord, *, reversed_by: str, updated_by: str,
                      audit_ref: str = "") -> HcgRecord:
        """Mark a financial record reversed without rewriting amounts."""
        now = self.store._now()
        cur = self.store._conn.execute(
            "UPDATE hcg_records SET status='REVERSED', version=version+1, updated_at=?,"
            " updated_by=?, reversed_by=?, audit_ref=?"
            " WHERE record_id=? AND version=? AND org_id=? AND workspace_id=?",
            (
                now, updated_by, reversed_by, audit_ref or record.audit_ref,
                record.record_id, record.version, record.org_id, record.workspace_id,
            ),
        )
        self.store._conn.commit()
        if cur.rowcount != 1:
            raise HcgValidationError("VERSION_CONFLICT", "reverse conflict")
        return self.get(
            record.record_id, org_id=record.org_id, workspace_id=record.workspace_id,
            app_instance_id=record.app_instance_id,
        )  # type: ignore[return-value]

    def evidence(
        self,
        *,
        org_id: str,
        workspace_id: str,
        app_instance_id: str,
        record_id: str,
        event_type: str,
        summary: str,
        evidence_ref: str = "",
        actor: str = "",
        detail: dict | None = None,
    ) -> dict:
        event_id = new_id("hcgev_")
        now = self.store._now()
        self.store._conn.execute(
            "INSERT INTO hcg_evidence_events (event_id,org_id,workspace_id,app_instance_id,"
            "record_id,event_type,evidence_ref,summary,actor,detail_json,created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                event_id, org_id, workspace_id, app_instance_id, record_id,
                event_type[:80], (evidence_ref or "")[:500], (summary or "")[:500],
                (actor or "")[:120],
                json.dumps(detail or {}, sort_keys=True, separators=(",", ":")),
                now,
            ),
        )
        self.store._conn.commit()
        return {
            "event_id": event_id,
            "record_id": record_id,
            "event_type": event_type,
            "evidence_ref": (evidence_ref or "")[:500],
            "summary": (summary or "")[:500],
            "created_at": now,
        }

    def list_evidence(
        self, *, org_id: str, workspace_id: str, app_instance_id: str = "",
        record_id: str = "", limit: int = 200,
    ) -> list[dict]:
        sql = "SELECT * FROM hcg_evidence_events WHERE org_id=? AND workspace_id=?"
        args: list[Any] = [org_id, workspace_id]
        if app_instance_id:
            sql += " AND app_instance_id=?"
            args.append(app_instance_id)
        if record_id:
            sql += " AND record_id=?"
            args.append(record_id)
        sql += " ORDER BY created_at DESC, event_id LIMIT ?"
        args.append(max(1, min(int(limit), 500)))
        out = []
        for row in self.store._conn.execute(sql, args).fetchall():
            d = dict(row)
            try:
                d["detail"] = json.loads(d.pop("detail_json") or "{}")
            except json.JSONDecodeError:
                d["detail"] = {}
            out.append(d)
        return out

    def export_scope(
        self, *, org_id: str, workspace_id: str, app_instance_id: str
    ) -> dict[str, Any]:
        rows = self.list(
            org_id=org_id, workspace_id=workspace_id, app_instance_id=app_instance_id,
            limit=500, include_archived=False,
        )
        evidence = self.list_evidence(
            org_id=org_id, workspace_id=workspace_id, app_instance_id=app_instance_id, limit=500,
        )
        return {
            "records": [r.to_public() for r in rows],
            "evidence": evidence,
            "record_count": len(rows),
            "evidence_count": len(evidence),
        }

    def replace_scope(
        self,
        *,
        org_id: str,
        workspace_id: str,
        app_instance_id: str,
        payload: dict[str, Any],
    ) -> dict[str, int]:
        """Replace workspace app data for restore (after checkpoint)."""
        self.store._conn.execute(
            "DELETE FROM hcg_records WHERE org_id=? AND workspace_id=? AND app_instance_id=?",
            (org_id, workspace_id, app_instance_id),
        )
        self.store._conn.execute(
            "DELETE FROM hcg_evidence_events WHERE org_id=? AND workspace_id=? AND app_instance_id=?",
            (org_id, workspace_id, app_instance_id),
        )
        n = 0
        for raw in payload.get("records") or []:
            body = raw.get("body") or {}
            self.store._conn.execute(
                "INSERT INTO hcg_records (record_id,record_type,org_id,workspace_id,app_instance_id,"
                "location_id,status,body_json,idempotency_key,version,created_at,updated_at,"
                "created_by,updated_by,audit_ref,reversed_by,reverses_id,archived_at,demo)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    raw["record_id"], raw["record_type"], org_id, workspace_id, app_instance_id,
                    raw.get("location_id") or "", raw.get("status") or "ACTIVE",
                    json.dumps(body, sort_keys=True, separators=(",", ":")),
                    raw.get("idempotency_key") or "",
                    int(raw.get("version") or 1),
                    float(raw.get("created_at") or 0),
                    float(raw.get("updated_at") or 0),
                    raw.get("created_by") or "",
                    raw.get("updated_by") or "",
                    raw.get("audit_ref") or "",
                    raw.get("reversed_by") or "",
                    raw.get("reverses_id") or "",
                    float(raw.get("archived_at") or 0),
                    1 if raw.get("demo") else 0,
                ),
            )
            n += 1
        e = 0
        for ev in payload.get("evidence") or []:
            self.store._conn.execute(
                "INSERT INTO hcg_evidence_events (event_id,org_id,workspace_id,app_instance_id,"
                "record_id,event_type,evidence_ref,summary,actor,detail_json,created_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    ev.get("event_id") or new_id("hcgev_"),
                    org_id, workspace_id, app_instance_id,
                    ev.get("record_id") or "",
                    (ev.get("event_type") or "")[:80],
                    (ev.get("evidence_ref") or "")[:500],
                    (ev.get("summary") or "")[:500],
                    (ev.get("actor") or "")[:120],
                    json.dumps(ev.get("detail") or {}, sort_keys=True, separators=(",", ":")),
                    float(ev.get("created_at") or 0),
                ),
            )
            e += 1
        self.store._conn.commit()
        return {"records": n, "evidence": e}

    @staticmethod
    def _row(row) -> HcgRecord:
        return HcgRecord(
            record_id=row["record_id"],
            record_type=row["record_type"],
            org_id=row["org_id"],
            workspace_id=row["workspace_id"],
            app_instance_id=row["app_instance_id"],
            location_id=row["location_id"] or "",
            status=row["status"],
            body=json.loads(row["body_json"] or "{}"),
            idempotency_key=row["idempotency_key"] or "",
            version=int(row["version"]),
            created_at=float(row["created_at"]),
            updated_at=float(row["updated_at"]),
            created_by=row["created_by"] or "",
            updated_by=row["updated_by"] or "",
            audit_ref=row["audit_ref"] or "",
            reversed_by=row["reversed_by"] or "",
            reverses_id=row["reverses_id"] or "",
            archived_at=float(row["archived_at"] or 0),
            demo=bool(row["demo"]),
        )
