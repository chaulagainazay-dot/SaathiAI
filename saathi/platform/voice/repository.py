"""Persistence adapter over the authoritative serialized PlatformStore."""
from __future__ import annotations

import json
import sqlite3
from typing import Any

from saathi.platform.models import new_id

from .models import (
    SPEECH_TRANSITIONS,
    SpeechOperation,
    SpeechState,
    VoiceProfile,
)


class VoiceRepository:
    def __init__(self, platform_store):
        self.store = platform_store

    def create_operation(
        self, request, *, operation_id: str, expires_at: float
    ) -> SpeechOperation:
        now = self.store._now()
        operation = SpeechOperation(
            operation_id=operation_id,
            organization_id=request.organization_id,
            workspace_id=request.workspace_id,
            user_id=request.user_id,
            state=SpeechState.QUEUED.value,
            requested_provider=request.provider,
            request_metadata=request.persisted_metadata(),
            text_sha256=request.text_sha256,
            text_length=len(request.text),
            output_format=request.output_format,
            idempotency_key=request.idempotency_key,
            created_at=now,
            updated_at=now,
            expires_at=expires_at,
        )
        try:
            self.store._conn.execute(
                "INSERT INTO voice_speech_operations (operation_id,org_id,workspace_id,"
                "user_id,state,requested_provider,provider,request_json,text_sha256,text_length,"
                "artifact_id,artifact_name,output_format,sample_rate,duration_seconds,"
                "artifact_bytes,streaming_state,fallback_used,fallback_reason,error_category,"
                "idempotency_key,cancel_requested,created_at,started_at,completed_at,expires_at,"
                "updated_at,version) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                self._operation_values(operation),
            )
            self.store._conn.commit()
        except sqlite3.IntegrityError:
            if not request.idempotency_key:
                raise
            existing = self.find_idempotent(
                org_id=request.organization_id,
                workspace_id=request.workspace_id,
                user_id=request.user_id,
                idempotency_key=request.idempotency_key,
            )
            if existing:
                return existing
            raise
        return operation

    @staticmethod
    def _operation_values(operation: SpeechOperation) -> tuple[Any, ...]:
        return (
            operation.operation_id,
            operation.organization_id,
            operation.workspace_id,
            operation.user_id,
            operation.state,
            operation.requested_provider,
            operation.provider,
            json.dumps(
                operation.request_metadata, sort_keys=True, separators=(",", ":")
            ),
            operation.text_sha256,
            operation.text_length,
            operation.artifact_id,
            operation.artifact_name,
            operation.output_format,
            operation.sample_rate,
            operation.duration_seconds,
            operation.artifact_bytes,
            operation.streaming_state,
            int(operation.fallback_used),
            operation.fallback_reason,
            operation.error_category,
            operation.idempotency_key,
            int(operation.cancel_requested),
            operation.created_at,
            operation.started_at,
            operation.completed_at,
            operation.expires_at,
            operation.updated_at,
            operation.version,
        )

    def find_idempotent(
        self, *, org_id: str, workspace_id: str, user_id: str, idempotency_key: str
    ) -> SpeechOperation | None:
        if not idempotency_key:
            return None
        row = self.store._conn.execute(
            "SELECT * FROM voice_speech_operations WHERE org_id=? AND workspace_id=?"
            " AND user_id=? AND idempotency_key=?",
            (org_id, workspace_id, user_id, idempotency_key[:120]),
        ).fetchone()
        return self._operation_row(row) if row else None

    def get_operation(
        self, operation_id: str, *, org_id: str, workspace_id: str
    ) -> SpeechOperation | None:
        row = self.store._conn.execute(
            "SELECT * FROM voice_speech_operations WHERE operation_id=? AND org_id=?"
            " AND workspace_id=?",
            (operation_id, org_id, workspace_id),
        ).fetchone()
        return self._operation_row(row) if row else None

    def get_operation_unscoped(self, operation_id: str) -> SpeechOperation | None:
        row = self.store._conn.execute(
            "SELECT * FROM voice_speech_operations WHERE operation_id=?",
            (operation_id,),
        ).fetchone()
        return self._operation_row(row) if row else None

    def list_operations(
        self,
        *,
        org_id: str,
        workspace_id: str,
        user_id: str = "",
        states: tuple[str, ...] = (),
        limit: int = 100,
    ) -> list[SpeechOperation]:
        sql = "SELECT * FROM voice_speech_operations WHERE 1=1"
        args: list[Any] = []
        if org_id:
            sql += " AND org_id=?"
            args.append(org_id)
        if workspace_id:
            sql += " AND workspace_id=?"
            args.append(workspace_id)
        if user_id:
            sql += " AND user_id=?"
            args.append(user_id)
        if states:
            sql += f" AND state IN ({','.join('?' for _ in states)})"
            args.extend(states)
        sql += " ORDER BY created_at DESC,operation_id LIMIT ?"
        args.append(max(1, min(int(limit), 500)))
        return [
            self._operation_row(row)
            for row in self.store._conn.execute(sql, args).fetchall()
        ]

    def count_nonterminal(self, *, org_id: str, workspace_id: str) -> int:
        states = tuple(
            state.value
            for state in SpeechState
            if state
            not in {
                SpeechState.COMPLETED,
                SpeechState.CANCELLED,
                SpeechState.FAILED,
                SpeechState.UNAVAILABLE,
                SpeechState.EXPIRED,
            }
        )
        row = self.store._conn.execute(
            f"SELECT COUNT(*) FROM voice_speech_operations WHERE org_id=? AND workspace_id=?"
            f" AND state IN ({','.join('?' for _ in states)})",
            (org_id, workspace_id, *states),
        ).fetchone()
        return int(row[0]) if row else 0

    def transition(
        self,
        operation: SpeechOperation,
        target: SpeechState | str,
        **updates: Any,
    ) -> SpeechOperation:
        target_state = SpeechState(target)
        source = SpeechState(operation.state)
        if target_state not in SPEECH_TRANSITIONS[source]:
            raise ValueError(
                f"illegal speech transition {source.value}->{target_state.value}"
            )
        allowed = {
            "provider",
            "artifact_id",
            "artifact_name",
            "output_format",
            "sample_rate",
            "duration_seconds",
            "artifact_bytes",
            "streaming_state",
            "fallback_used",
            "fallback_reason",
            "error_category",
            "cancel_requested",
            "started_at",
            "completed_at",
            "expires_at",
        }
        unknown = set(updates) - allowed
        if unknown:
            raise ValueError(f"unsupported speech updates: {sorted(unknown)}")
        columns = ["state=?", "updated_at=?", "version=version+1"]
        values: list[Any] = [target_state.value, self.store._now()]
        for key, value in updates.items():
            columns.append(f"{key}=?")
            if key in {"fallback_used", "cancel_requested"}:
                value = int(bool(value))
            values.append(value)
        values.extend([operation.operation_id, operation.version])
        cur = self.store._conn.execute(
            f"UPDATE voice_speech_operations SET {','.join(columns)}"
            " WHERE operation_id=? AND version=?",
            values,
        )
        self.store._conn.commit()
        if cur.rowcount != 1:
            raise RuntimeError("speech operation update conflict")
        updated = self.get_operation_unscoped(operation.operation_id)
        if not updated:
            raise RuntimeError("speech operation disappeared")
        return updated

    def request_cancel(self, operation: SpeechOperation) -> SpeechOperation:
        if operation.is_terminal():
            return operation
        cur = self.store._conn.execute(
            "UPDATE voice_speech_operations SET cancel_requested=1,updated_at=?,"
            "version=version+1 WHERE operation_id=? AND version=?",
            (self.store._now(), operation.operation_id, operation.version),
        )
        self.store._conn.commit()
        if cur.rowcount != 1:
            current = self.get_operation_unscoped(operation.operation_id)
            if current:
                return current
            raise RuntimeError("speech cancellation conflict")
        return self.get_operation_unscoped(operation.operation_id)  # type: ignore[return-value]

    def reconcile_interrupted(self) -> int:
        nonterminal = (
            SpeechState.QUEUED.value,
            SpeechState.PREPARING.value,
            SpeechState.SYNTHESIZING.value,
            SpeechState.STREAMING.value,
            SpeechState.PLAYING.value,
        )
        now = self.store._now()
        cur = self.store._conn.execute(
            f"UPDATE voice_speech_operations SET state=?,error_category=?,completed_at=?,"
            f"updated_at=?,version=version+1 WHERE state IN ({','.join('?' for _ in nonterminal)})",
            (
                SpeechState.UNAVAILABLE.value,
                "interrupted_by_restart",
                now,
                now,
                *nonterminal,
            ),
        )
        self.store._conn.commit()
        return cur.rowcount

    def create_evidence(
        self,
        operation: SpeechOperation,
        *,
        event_type: str,
        summary: str,
        artifact_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        evidence_id = new_id("voiceev_")
        self.store._conn.execute(
            "INSERT INTO voice_evidence_events (evidence_id,operation_id,org_id,"
            "workspace_id,user_id,event_type,artifact_id,summary,metadata_json,created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                evidence_id,
                operation.operation_id,
                operation.organization_id,
                operation.workspace_id,
                operation.user_id,
                event_type[:80],
                artifact_id[:160],
                summary[:300],
                json.dumps(metadata or {}, sort_keys=True, separators=(",", ":")),
                self.store._now(),
            ),
        )
        self.store._conn.commit()
        return evidence_id

    def list_evidence(
        self, *, org_id: str, workspace_id: str, user_id: str = "", limit: int = 200
    ) -> list[dict[str, Any]]:
        sql = "SELECT * FROM voice_evidence_events WHERE org_id=? AND workspace_id=?"
        args: list[Any] = [org_id, workspace_id]
        if user_id:
            sql += " AND user_id=?"
            args.append(user_id)
        sql += " ORDER BY created_at DESC,evidence_id LIMIT ?"
        args.append(max(1, min(int(limit), 500)))
        rows = self.store._conn.execute(sql, args).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["metadata"] = json.loads(item.pop("metadata_json") or "{}")
            result.append(item)
        return result

    def create_profile(
        self,
        *,
        org_id: str,
        workspace_id: str,
        owner_id: str,
        body: dict[str, Any],
    ) -> VoiceProfile:
        now = self.store._now()
        profile = VoiceProfile(
            profile_id=body.get("profile_id") or new_id("voicep_"),
            organization_id=org_id,
            workspace_id=workspace_id,
            owner_id=owner_id,
            display_name=body["display_name"],
            provider=body["provider"],
            provider_voice_id=body["provider_voice_id"],
            language=body["language"],
            style=body["style"],
            rate=body["rate"],
            pitch=body["pitch"],
            reference_artifact_id=body["reference_artifact_id"],
            cloning_consent_state=body["cloning_consent_state"],
            module_preference=body["module_preference"],
            accessibility_rate=body["accessibility_rate"],
            status=body["status"],
            created_at=now,
            updated_at=now,
        )
        self.store._conn.execute(
            "INSERT INTO voice_profiles (profile_id,org_id,workspace_id,owner_id,"
            "display_name,provider,provider_voice_id,language,style,rate,pitch,"
            "reference_artifact_id,cloning_consent_state,module_preference,"
            "accessibility_rate,status,version,created_at,updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                profile.profile_id,
                profile.organization_id,
                profile.workspace_id,
                profile.owner_id,
                profile.display_name,
                profile.provider,
                profile.provider_voice_id,
                profile.language,
                profile.style,
                profile.rate,
                profile.pitch,
                profile.reference_artifact_id,
                profile.cloning_consent_state,
                profile.module_preference,
                profile.accessibility_rate,
                profile.status,
                profile.version,
                now,
                now,
            ),
        )
        self.store._conn.commit()
        return profile

    def get_profile(
        self, profile_id: str, *, org_id: str, workspace_id: str
    ) -> VoiceProfile | None:
        row = self.store._conn.execute(
            "SELECT * FROM voice_profiles WHERE profile_id=? AND org_id=? AND workspace_id=?",
            (profile_id, org_id, workspace_id),
        ).fetchone()
        return self._profile_row(row) if row else None

    def list_profiles(
        self, *, org_id: str, workspace_id: str, owner_id: str = "", limit: int = 200
    ) -> list[VoiceProfile]:
        sql = "SELECT * FROM voice_profiles WHERE org_id=? AND workspace_id=?"
        args: list[Any] = [org_id, workspace_id]
        if owner_id:
            sql += " AND owner_id=?"
            args.append(owner_id)
        sql += " ORDER BY updated_at DESC,profile_id LIMIT ?"
        args.append(max(1, min(int(limit), 500)))
        return [
            self._profile_row(row)
            for row in self.store._conn.execute(sql, args).fetchall()
        ]

    def update_profile(
        self, profile: VoiceProfile, updates: dict[str, Any]
    ) -> VoiceProfile:
        allowed = {
            "display_name",
            "provider",
            "provider_voice_id",
            "language",
            "style",
            "rate",
            "pitch",
            "reference_artifact_id",
            "cloning_consent_state",
            "module_preference",
            "accessibility_rate",
            "status",
        }
        values = {key: value for key, value in updates.items() if key in allowed}
        if not values:
            return profile
        columns = ["updated_at=?", "version=version+1"]
        args: list[Any] = [self.store._now()]
        for key, value in values.items():
            columns.append(f"{key}=?")
            args.append(value)
        args.extend([profile.profile_id, profile.version])
        cur = self.store._conn.execute(
            f"UPDATE voice_profiles SET {','.join(columns)}"
            " WHERE profile_id=? AND version=?",
            args,
        )
        self.store._conn.commit()
        if cur.rowcount != 1:
            raise RuntimeError("voice profile update conflict")
        updated = self.get_profile(
            profile.profile_id,
            org_id=profile.organization_id,
            workspace_id=profile.workspace_id,
        )
        if not updated:
            raise RuntimeError("voice profile disappeared")
        return updated

    def delete_profile(self, profile: VoiceProfile) -> bool:
        cur = self.store._conn.execute(
            "DELETE FROM voice_profiles WHERE profile_id=? AND version=?",
            (profile.profile_id, profile.version),
        )
        self.store._conn.commit()
        return cur.rowcount == 1

    @staticmethod
    def _operation_row(row) -> SpeechOperation:
        return SpeechOperation(
            operation_id=row["operation_id"],
            organization_id=row["org_id"],
            workspace_id=row["workspace_id"],
            user_id=row["user_id"],
            state=row["state"],
            requested_provider=row["requested_provider"],
            provider=row["provider"] or "",
            request_metadata=json.loads(row["request_json"] or "{}"),
            text_sha256=row["text_sha256"] or "",
            text_length=int(row["text_length"] or 0),
            artifact_id=row["artifact_id"] or "",
            artifact_name=row["artifact_name"] or "",
            output_format=row["output_format"] or "aiff",
            sample_rate=int(row["sample_rate"] or 0),
            duration_seconds=float(row["duration_seconds"] or 0),
            artifact_bytes=int(row["artifact_bytes"] or 0),
            streaming_state=row["streaming_state"] or "not_started",
            fallback_used=bool(row["fallback_used"]),
            fallback_reason=row["fallback_reason"] or "",
            error_category=row["error_category"] or "",
            idempotency_key=row["idempotency_key"] or "",
            cancel_requested=bool(row["cancel_requested"]),
            created_at=float(row["created_at"]),
            started_at=float(row["started_at"] or 0),
            completed_at=float(row["completed_at"] or 0),
            expires_at=float(row["expires_at"] or 0),
            updated_at=float(row["updated_at"]),
            version=int(row["version"]),
        )

    @staticmethod
    def _profile_row(row) -> VoiceProfile:
        return VoiceProfile(
            profile_id=row["profile_id"],
            organization_id=row["org_id"],
            workspace_id=row["workspace_id"],
            owner_id=row["owner_id"],
            display_name=row["display_name"],
            provider=row["provider"],
            provider_voice_id=row["provider_voice_id"] or "",
            language=row["language"],
            style=row["style"] or "",
            rate=float(row["rate"]),
            pitch=float(row["pitch"]),
            reference_artifact_id=row["reference_artifact_id"] or "",
            cloning_consent_state=row["cloning_consent_state"],
            module_preference=row["module_preference"] or "",
            accessibility_rate=float(row["accessibility_rate"]),
            status=row["status"],
            created_at=float(row["created_at"]),
            updated_at=float(row["updated_at"]),
            version=int(row["version"]),
        )
