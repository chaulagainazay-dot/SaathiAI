"""Persistence for real-time voice sessions and transcripts."""
from __future__ import annotations

import json
import sqlite3
from typing import Any

from saathi.platform.models import new_id

from .models import (
    ConversationSession,
    ConversationState,
    InterruptionRecord,
    TranscriptEntry,
)


class VoiceRuntimeRepository:
    def __init__(self, platform_store):
        self.store = platform_store

    def create_session(self, session: ConversationSession) -> ConversationSession:
        self.store._conn.execute(
            """
            INSERT INTO voice_runtime_sessions (
                session_id, org_id, workspace_id, user_id, conversation_id, state,
                input_mode, input_state, playback_state, stt_provider, voice_profile_id,
                sample_rate, max_recording_seconds, silence_timeout_ms, min_speech_ms,
                partial_user_transcript, partial_assistant_response,
                active_speech_operation_id, active_playback_id, error_category,
                error_message, evidence_id, project_id, locale, yeti_mode, version,
                created_at, updated_at, last_activity_at, expires_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            self._session_values(session),
        )
        self.store._conn.commit()
        return session

    def save_session(self, session: ConversationSession) -> ConversationSession:
        session.version = int(session.version) + 1
        session.updated_at = self.store._now()
        session.last_activity_at = session.updated_at
        cur = self.store._conn.execute(
            """
            UPDATE voice_runtime_sessions SET
                conversation_id=?, state=?, input_mode=?, input_state=?,
                playback_state=?, stt_provider=?, voice_profile_id=?, sample_rate=?,
                max_recording_seconds=?, silence_timeout_ms=?, min_speech_ms=?,
                partial_user_transcript=?, partial_assistant_response=?,
                active_speech_operation_id=?, active_playback_id=?, error_category=?,
                error_message=?, evidence_id=?, project_id=?, locale=?, yeti_mode=?,
                version=?, updated_at=?, last_activity_at=?, expires_at=?
            WHERE session_id=? AND org_id=? AND workspace_id=? AND version=?
            """,
            (
                session.conversation_id,
                session.state,
                session.input_mode,
                session.input_state,
                session.playback_state,
                session.stt_provider,
                session.voice_profile_id,
                session.sample_rate,
                session.max_recording_seconds,
                session.silence_timeout_ms,
                session.min_speech_ms,
                session.partial_user_transcript,
                session.partial_assistant_response,
                session.active_speech_operation_id,
                session.active_playback_id,
                session.error_category,
                session.error_message,
                session.evidence_id,
                session.project_id,
                session.locale,
                session.yeti_mode,
                session.version,
                session.updated_at,
                session.last_activity_at,
                session.expires_at,
                session.session_id,
                session.organization_id,
                session.workspace_id,
                session.version - 1,
            ),
        )
        if cur.rowcount != 1:
            raise sqlite3.IntegrityError("voice session version conflict")
        self.store._conn.commit()
        return session

    def get_session(
        self, session_id: str, *, org_id: str, workspace_id: str
    ) -> ConversationSession | None:
        row = self.store._conn.execute(
            """
            SELECT * FROM voice_runtime_sessions
            WHERE session_id=? AND org_id=? AND workspace_id=?
            """,
            (session_id, org_id, workspace_id),
        ).fetchone()
        if not row:
            return None
        session = self._row_to_session(row)
        session.transcript = self.list_transcript(session_id)
        session.interruptions = self.list_interruptions(session_id)
        return session

    def list_sessions(
        self, *, org_id: str, workspace_id: str, user_id: str, limit: int = 20
    ) -> list[ConversationSession]:
        rows = self.store._conn.execute(
            """
            SELECT * FROM voice_runtime_sessions
            WHERE org_id=? AND workspace_id=? AND user_id=?
            ORDER BY updated_at DESC LIMIT ?
            """,
            (org_id, workspace_id, user_id, max(1, min(int(limit), 50))),
        ).fetchall()
        sessions = []
        for row in rows:
            session = self._row_to_session(row)
            session.transcript = self.list_transcript(session.session_id)
            session.interruptions = self.list_interruptions(session.session_id)
            sessions.append(session)
        return sessions

    def count_active_for_user(
        self, *, org_id: str, workspace_id: str, user_id: str
    ) -> int:
        row = self.store._conn.execute(
            """
            SELECT COUNT(*) AS c FROM voice_runtime_sessions
            WHERE org_id=? AND workspace_id=? AND user_id=?
              AND state NOT IN ('FINISHED','FAILED')
            """,
            (org_id, workspace_id, user_id),
        ).fetchone()
        return int(row["c"] if row else 0)

    def add_transcript(self, session_id: str, entry: TranscriptEntry) -> TranscriptEntry:
        self.store._conn.execute(
            """
            INSERT INTO voice_runtime_transcripts (
                entry_id, session_id, role, text, is_partial, is_final, provider,
                confidence, speech_operation_id, interrupted, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                entry.entry_id,
                session_id,
                entry.role,
                entry.text,
                int(entry.is_partial),
                int(entry.is_final),
                entry.provider,
                entry.confidence,
                entry.speech_operation_id,
                int(entry.interrupted),
                entry.created_at,
            ),
        )
        self.store._conn.commit()
        return entry

    def list_transcript(self, session_id: str) -> list[TranscriptEntry]:
        rows = self.store._conn.execute(
            """
            SELECT * FROM voice_runtime_transcripts
            WHERE session_id=? ORDER BY created_at ASC
            """,
            (session_id,),
        ).fetchall()
        return [
            TranscriptEntry(
                entry_id=row["entry_id"],
                role=row["role"],
                text=row["text"] or "",
                is_partial=bool(row["is_partial"]),
                is_final=bool(row["is_final"]),
                provider=row["provider"] or "",
                confidence=float(row["confidence"] or 0.0),
                speech_operation_id=row["speech_operation_id"] or "",
                created_at=float(row["created_at"] or 0.0),
                interrupted=bool(row["interrupted"]),
            )
            for row in rows
        ]

    def add_interruption(
        self, session_id: str, record: InterruptionRecord
    ) -> InterruptionRecord:
        self.store._conn.execute(
            """
            INSERT INTO voice_runtime_interruptions (
                interruption_id, session_id, reason, from_state, to_state,
                preserved_text, created_at
            ) VALUES (?,?,?,?,?,?,?)
            """,
            (
                record.interruption_id,
                session_id,
                record.reason,
                record.from_state,
                record.to_state,
                record.preserved_text,
                record.created_at,
            ),
        )
        self.store._conn.commit()
        return record

    def list_interruptions(self, session_id: str) -> list[InterruptionRecord]:
        rows = self.store._conn.execute(
            """
            SELECT * FROM voice_runtime_interruptions
            WHERE session_id=? ORDER BY created_at ASC
            """,
            (session_id,),
        ).fetchall()
        return [
            InterruptionRecord(
                interruption_id=row["interruption_id"],
                reason=row["reason"] or "",
                from_state=row["from_state"] or "",
                to_state=row["to_state"] or "",
                preserved_text=row["preserved_text"] or "",
                created_at=float(row["created_at"] or 0.0),
            )
            for row in rows
        ]

    def create_evidence(
        self,
        session: ConversationSession,
        *,
        event_type: str,
        summary: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        evidence_id = new_id("vrev_")
        self.store._conn.execute(
            """
            INSERT INTO voice_runtime_evidence (
                evidence_id, session_id, org_id, workspace_id, user_id,
                event_type, summary, metadata_json, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?)
            """,
            (
                evidence_id,
                session.session_id,
                session.organization_id,
                session.workspace_id,
                session.user_id,
                event_type,
                summary[:500],
                json.dumps(metadata or {}, sort_keys=True, separators=(",", ":")),
                self.store._now(),
            ),
        )
        self.store._conn.commit()
        return evidence_id

    @staticmethod
    def _session_values(session: ConversationSession) -> tuple[Any, ...]:
        return (
            session.session_id,
            session.organization_id,
            session.workspace_id,
            session.user_id,
            session.conversation_id,
            session.state,
            session.input_mode,
            session.input_state,
            session.playback_state,
            session.stt_provider,
            session.voice_profile_id,
            session.sample_rate,
            session.max_recording_seconds,
            session.silence_timeout_ms,
            session.min_speech_ms,
            session.partial_user_transcript,
            session.partial_assistant_response,
            session.active_speech_operation_id,
            session.active_playback_id,
            session.error_category,
            session.error_message,
            session.evidence_id,
            session.project_id,
            session.locale,
            session.yeti_mode,
            session.version,
            session.created_at,
            session.updated_at,
            session.last_activity_at,
            session.expires_at,
        )

    @staticmethod
    def _row_to_session(row) -> ConversationSession:
        return ConversationSession(
            session_id=row["session_id"],
            organization_id=row["org_id"],
            workspace_id=row["workspace_id"],
            user_id=row["user_id"],
            conversation_id=row["conversation_id"] or "",
            state=row["state"] or ConversationState.IDLE.value,
            input_mode=row["input_mode"] or "toggle",
            input_state=row["input_state"] or "idle",
            playback_state=row["playback_state"] or "idle",
            stt_provider=row["stt_provider"] or "auto",
            voice_profile_id=row["voice_profile_id"] or "yeti_teacher",
            sample_rate=int(row["sample_rate"] or 16000),
            max_recording_seconds=float(row["max_recording_seconds"] or 30.0),
            silence_timeout_ms=float(row["silence_timeout_ms"] or 900.0),
            min_speech_ms=float(row["min_speech_ms"] or 150.0),
            partial_user_transcript=row["partial_user_transcript"] or "",
            partial_assistant_response=row["partial_assistant_response"] or "",
            active_speech_operation_id=row["active_speech_operation_id"] or "",
            active_playback_id=row["active_playback_id"] or "",
            error_category=row["error_category"] or "",
            error_message=row["error_message"] or "",
            evidence_id=row["evidence_id"] or "",
            project_id=row["project_id"] or "",
            locale=row["locale"] or "en-US",
            yeti_mode=row["yeti_mode"] or "general",
            version=int(row["version"] or 1),
            created_at=float(row["created_at"] or 0.0),
            updated_at=float(row["updated_at"] or 0.0),
            last_activity_at=float(row["last_activity_at"] or 0.0),
            expires_at=float(row["expires_at"] or 0.0),
        )
