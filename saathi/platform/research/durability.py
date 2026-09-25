"""RESEARCH-3 typed durability in the existing canonical research database.

Stored records are audit evidence only. Recovery explicitly has no replay,
approval, reservation, order, or execution behavior.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from decimal import Decimal
from enum import Enum
from hashlib import sha256
import inspect
import json
from pathlib import Path
import sqlite3
import time
from typing import Any

from saathi.platform.portfolio_construction.models import StrategyQualificationEvidence
from saathi.platform.research.journal import (
    DecisionOutcome,
    InvestmentDecisionRecord,
    InvestmentLesson,
    LessonStatus,
)
from saathi.platform.research.store import ResearchStore
from saathi.platform.signal import Direction, TradingIntentProposal, TradingSignal


DURABILITY_SCHEMA_VERSION = 1
MAX_RECORD_BYTES = 1_000_000


class PersistenceError(RuntimeError):
    pass


class PersistenceConflictError(PersistenceError):
    pass


class PersistenceCorruptError(PersistenceError):
    pass


class PersistenceBusyError(PersistenceError):
    pass


class UnsupportedSchemaVersion(PersistenceError):
    pass


_SCHEMA_V1 = """
CREATE TABLE IF NOT EXISTS research_durable_decisions (
    decision_id TEXT PRIMARY KEY,
    decision_time TEXT NOT NULL,
    instrument_id TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS research_durable_outcomes (
    outcome_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    decision_id TEXT NOT NULL,
    available_at TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at REAL NOT NULL,
    PRIMARY KEY (outcome_id, revision)
);
CREATE TABLE IF NOT EXISTS research_durable_lessons (
    lesson_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    status TEXT NOT NULL,
    available_at TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at REAL NOT NULL,
    PRIMARY KEY (lesson_id, version)
);
CREATE TABLE IF NOT EXISTS research_durable_signals (
    signal_id TEXT PRIMARY KEY,
    decision_time TEXT NOT NULL,
    valid_until TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS research_durable_intents (
    intent_id TEXT PRIMARY KEY,
    valid_until TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS research_durable_qualifications (
    intent_id TEXT PRIMARY KEY,
    strategy_id TEXT NOT NULL,
    qualification_artifact_sha256 TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS research_durable_construction (
    candidate_portfolio_id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL,
    portfolio_snapshot_ref TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS research_durable_links (
    link_id TEXT PRIMARY KEY,
    from_id TEXT NOT NULL,
    to_id TEXT NOT NULL,
    relation TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_rd_outcomes_decision
    ON research_durable_outcomes(decision_id, revision);
CREATE INDEX IF NOT EXISTS idx_rd_signals_valid
    ON research_durable_signals(valid_until);
CREATE INDEX IF NOT EXISTS idx_rd_intents_valid
    ON research_durable_intents(valid_until);
CREATE INDEX IF NOT EXISTS idx_rd_links_from
    ON research_durable_links(from_id, relation);
CREATE INDEX IF NOT EXISTS idx_rd_links_to
    ON research_durable_links(to_id, relation);
"""


def _dt(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise ValueError("persisted timestamps must be timezone-aware")
    return value.isoformat()


def _parse_dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _canonical(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _content_hash(payload_json: str) -> str:
    return sha256(payload_json.encode("utf-8")).hexdigest()


def _decision_payload(value: InvestmentDecisionRecord) -> dict[str, Any]:
    return {
        "decision_id": value.decision_id,
        "instrument_id": value.instrument_id,
        "decision_time": _dt(value.decision_time),
        "thesis_id": value.thesis_id,
        "status": value.status,
        "expected_direction": value.expected_direction,
        "intended_horizon": value.intended_horizon,
        "research_run_id": value.research_run_id,
        "research_snapshot_id": value.research_snapshot_id,
        "challenge_session_id": value.challenge_session_id,
        "assumptions": list(value.assumptions),
        "invalidation_conditions": list(value.invalidation_conditions),
        "available_at": _dt(value.available_at),
        "valid_until": _dt(value.valid_until),
    }


def _decision_from(payload: dict[str, Any]) -> InvestmentDecisionRecord:
    return InvestmentDecisionRecord(
        decision_id=payload["decision_id"],
        instrument_id=payload["instrument_id"],
        decision_time=_parse_dt(payload["decision_time"]),
        thesis_id=payload["thesis_id"],
        status=payload["status"],
        expected_direction=payload["expected_direction"],
        intended_horizon=payload["intended_horizon"],
        research_run_id=payload.get("research_run_id"),
        research_snapshot_id=payload.get("research_snapshot_id"),
        challenge_session_id=payload.get("challenge_session_id"),
        assumptions=tuple(payload.get("assumptions") or ()),
        invalidation_conditions=tuple(payload.get("invalidation_conditions") or ()),
        available_at=_parse_dt(payload.get("available_at")),
        valid_until=_parse_dt(payload.get("valid_until")),
    )


def _outcome_payload(value: DecisionOutcome) -> dict[str, Any]:
    return {
        "outcome_id": value.outcome_id,
        "decision_id": value.decision_id,
        "observation_start": _dt(value.observation_start),
        "observation_end": _dt(value.observation_end),
        "instrument_return": str(value.instrument_return) if value.instrument_return is not None else None,
        "benchmark_return": str(value.benchmark_return) if value.benchmark_return is not None else None,
        "revision": value.revision,
        "available_at": _dt(value.available_at or value.observation_end),
    }


def _outcome_from(payload: dict[str, Any]) -> DecisionOutcome:
    return DecisionOutcome(
        outcome_id=payload["outcome_id"],
        decision_id=payload["decision_id"],
        observation_start=_parse_dt(payload["observation_start"]),
        observation_end=_parse_dt(payload["observation_end"]),
        instrument_return=(
            Decimal(payload["instrument_return"]) if payload.get("instrument_return") is not None else None
        ),
        benchmark_return=(
            Decimal(payload["benchmark_return"]) if payload.get("benchmark_return") is not None else None
        ),
        revision=int(payload["revision"]),
        available_at=_parse_dt(payload.get("available_at")),
    )


def _lesson_payload(value: InvestmentLesson, *, review_ref: str = "") -> dict[str, Any]:
    return {
        "lesson_id": value.lesson_id,
        "origin_decision_ids": list(value.origin_decision_ids),
        "statement": value.statement,
        "lesson_type": value.lesson_type,
        "scope": value.scope,
        "instrument_scope": value.instrument_scope,
        "available_at": _dt(value.available_at),
        "valid_until": _dt(value.valid_until),
        "status": value.status.value,
        "sample_size": value.sample_size,
        "version": value.version,
        "review_ref": review_ref,
    }


def _lesson_from(payload: dict[str, Any]) -> InvestmentLesson:
    return InvestmentLesson(
        lesson_id=payload["lesson_id"],
        origin_decision_ids=tuple(payload["origin_decision_ids"]),
        statement=payload["statement"],
        lesson_type=payload["lesson_type"],
        scope=payload["scope"],
        instrument_scope=payload.get("instrument_scope"),
        available_at=_parse_dt(payload["available_at"]),
        valid_until=_parse_dt(payload.get("valid_until")),
        status=LessonStatus(payload["status"]),
        sample_size=int(payload["sample_size"]),
        version=int(payload["version"]),
    )


def _signal_payload(value: TradingSignal) -> dict[str, Any]:
    return {
        "signal_id": value.signal_id,
        "strategy_id": value.strategy_id,
        "strategy_version": value.strategy_version,
        "instrument_id": value.instrument_id,
        "direction": value.direction.value,
        "strength": str(value.strength),
        "generated_at": _dt(value.generated_at),
        "decision_time": _dt(value.generated_at),
        "available_at": _dt(value.generated_at),
        "valid_until": _dt(value.valid_until),
        "data_mode": value.data_mode,
        "reason_codes": list(value.reason_codes),
        "quality": value.quality,
        "venue": value.venue,
    }


def _signal_from(payload: dict[str, Any]) -> TradingSignal:
    return TradingSignal(
        signal_id=payload["signal_id"],
        strategy_id=payload["strategy_id"],
        strategy_version=payload["strategy_version"],
        instrument_id=payload["instrument_id"],
        direction=Direction(payload["direction"]),
        strength=Decimal(payload["strength"]),
        generated_at=_parse_dt(payload["generated_at"]),
        valid_until=_parse_dt(payload["valid_until"]),
        data_mode=payload["data_mode"],
        reason_codes=tuple(payload["reason_codes"]),
        quality=payload["quality"],
        venue=payload.get("venue"),
    )


def _intent_payload(value: TradingIntentProposal) -> dict[str, Any]:
    return {
        "intent_id": value.intent_id,
        "signal_refs": list(value.signal_refs),
        "instrument_id": value.instrument_id,
        "direction": value.direction.value,
        "valid_until": _dt(value.valid_until),
        "quality": value.quality,
        "generated_at": _dt(value.generated_at),
        "available_at": _dt(value.generated_at),
        "data_mode": value.data_mode,
        "strategy_id": value.strategy_id,
        "strategy_version": value.strategy_version,
    }


def _intent_from(payload: dict[str, Any]) -> TradingIntentProposal:
    return TradingIntentProposal(
        intent_id=payload["intent_id"],
        signal_refs=tuple(payload["signal_refs"]),
        instrument_id=payload["instrument_id"],
        direction=Direction(payload["direction"]),
        valid_until=_parse_dt(payload["valid_until"]),
        quality=payload["quality"],
        generated_at=_parse_dt(payload.get("generated_at")),
        data_mode=payload.get("data_mode", "UNKNOWN"),
        strategy_id=payload.get("strategy_id", ""),
        strategy_version=payload.get("strategy_version", ""),
    )


class ResearchDurabilityStore:
    """Versioned append-only audit records on a ``ResearchStore`` connection."""

    def __init__(
        self,
        *,
        research_store: ResearchStore | None = None,
        busy_timeout_ms: int = 1_000,
    ):
        self.research_store = research_store or ResearchStore()
        self.connection = self.research_store._conn
        self.db_path = Path(self.research_store.db_path)
        self.connection.execute(f"PRAGMA busy_timeout={max(1, int(busy_timeout_ms))}")
        self.connection.execute("PRAGMA foreign_keys=ON")
        self._migrate()

    @property
    def schema_version(self) -> int:
        row = self.connection.execute(
            "SELECT schema_version FROM research_durability_meta WHERE singleton=1"
        ).fetchone()
        return int(row[0])

    def _migrate(self) -> None:
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS research_durability_meta "
            "(singleton INTEGER PRIMARY KEY CHECK(singleton=1), schema_version INTEGER NOT NULL)"
        )
        row = self.connection.execute(
            "SELECT schema_version FROM research_durability_meta WHERE singleton=1"
        ).fetchone()
        current = int(row[0]) if row else 0
        if current > DURABILITY_SCHEMA_VERSION:
            raise UnsupportedSchemaVersion(
                f"research durability schema {current} is newer than supported {DURABILITY_SCHEMA_VERSION}"
            )
        if current == 0:
            self.connection.executescript(_SCHEMA_V1)
            self.connection.execute(
                "INSERT INTO research_durability_meta(singleton,schema_version) VALUES (1,?)",
                (DURABILITY_SCHEMA_VERSION,),
            )
        else:
            self.connection.executescript(_SCHEMA_V1)
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def _insert(
        self,
        table: str,
        key_columns: tuple[str, ...],
        key_values: tuple[Any, ...],
        payload: dict[str, Any],
        columns: dict[str, Any],
        *,
        commit: bool,
    ) -> str:
        payload_json = _canonical(payload)
        if len(payload_json.encode("utf-8")) > MAX_RECORD_BYTES:
            raise ValueError(f"record exceeds {MAX_RECORD_BYTES} byte durability limit")
        digest = _content_hash(payload_json)
        where = " AND ".join(f"{name}=?" for name in key_columns)
        try:
            row = self.connection.execute(
                f"SELECT content_hash FROM {table} WHERE {where}", key_values
            ).fetchone()
            if row:
                if row[0] == digest:
                    return "DUPLICATE"
                raise PersistenceConflictError(
                    f"immutable identity conflict in {table}: {key_values}"
                )
            values = {
                **columns,
                "content_hash": digest,
                "payload_json": payload_json,
                "created_at": time.time(),
            }
            names = tuple(values)
            placeholders = ",".join("?" for _ in names)
            self.connection.execute(
                f"INSERT INTO {table} ({','.join(names)}) VALUES ({placeholders})",
                tuple(values[name] for name in names),
            )
            if commit:
                self.connection.commit()
            return "RECORDED"
        except sqlite3.OperationalError as exc:
            if commit:
                self.connection.rollback()
            if "locked" in str(exc).lower() or "busy" in str(exc).lower():
                raise PersistenceBusyError("research durability database is locked") from exc
            raise PersistenceError(str(exc)) from exc

    def _load(self, table: str, where: str, values: tuple[Any, ...]) -> dict[str, Any] | None:
        row = self.connection.execute(
            f"SELECT payload_json,content_hash FROM {table} WHERE {where}", values
        ).fetchone()
        if not row:
            return None
        payload_json, digest = row[0], row[1]
        if _content_hash(payload_json) != digest:
            raise PersistenceCorruptError(f"content hash mismatch in {table}")
        try:
            payload = json.loads(payload_json)
        except (TypeError, json.JSONDecodeError) as exc:
            raise PersistenceCorruptError(f"invalid JSON in {table}") from exc
        if not isinstance(payload, dict):
            raise PersistenceCorruptError(f"invalid payload shape in {table}")
        return payload

    def _list(self, table: str, order_by: str) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            f"SELECT payload_json,content_hash FROM {table} ORDER BY {order_by}"
        ).fetchall()
        output = []
        for payload_json, digest in rows:
            if _content_hash(payload_json) != digest:
                raise PersistenceCorruptError(f"content hash mismatch in {table}")
            try:
                value = json.loads(payload_json)
            except (TypeError, json.JSONDecodeError) as exc:
                raise PersistenceCorruptError(f"invalid JSON in {table}") from exc
            if not isinstance(value, dict):
                raise PersistenceCorruptError(f"invalid payload shape in {table}")
            output.append(value)
        return output

    def save_decision(self, value: InvestmentDecisionRecord, *, _commit: bool = True) -> str:
        payload = _decision_payload(value)
        return self._insert(
            "research_durable_decisions",
            ("decision_id",),
            (value.decision_id,),
            payload,
            {
                "decision_id": value.decision_id,
                "decision_time": payload["decision_time"],
                "instrument_id": value.instrument_id,
            },
            commit=_commit,
        )

    def get_decision(self, decision_id: str) -> InvestmentDecisionRecord | None:
        payload = self._load(
            "research_durable_decisions", "decision_id=?", (decision_id,)
        )
        return _decision_from(payload) if payload else None

    def save_outcome(self, value: DecisionOutcome, *, _commit: bool = True) -> str:
        if value.revision < 1:
            raise ValueError("outcome revision must be positive")
        payload = _outcome_payload(value)
        return self._insert(
            "research_durable_outcomes",
            ("outcome_id", "revision"),
            (value.outcome_id, value.revision),
            payload,
            {
                "outcome_id": value.outcome_id,
                "revision": value.revision,
                "decision_id": value.decision_id,
                "available_at": payload["available_at"],
            },
            commit=_commit,
        )

    def list_outcome_revisions(self, outcome_id: str) -> list[DecisionOutcome]:
        rows = self.connection.execute(
            "SELECT payload_json,content_hash FROM research_durable_outcomes "
            "WHERE outcome_id=? ORDER BY revision",
            (outcome_id,),
        ).fetchall()
        values = []
        for payload_json, digest in rows:
            if _content_hash(payload_json) != digest:
                raise PersistenceCorruptError("content hash mismatch in research_durable_outcomes")
            try:
                values.append(_outcome_from(json.loads(payload_json)))
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                raise PersistenceCorruptError("invalid outcome payload") from exc
        return values

    def save_lesson(self, value: InvestmentLesson, *, _commit: bool = True) -> str:
        if value.status is not LessonStatus.OBSERVED or value.version != 1:
            raise PermissionError("lesson cannot self-promote or bypass the transition policy")
        return self._save_lesson_revision(value, review_ref="", commit=_commit)

    def _save_lesson_revision(
        self, value: InvestmentLesson, *, review_ref: str, commit: bool
    ) -> str:
        payload = _lesson_payload(value, review_ref=review_ref)
        return self._insert(
            "research_durable_lessons",
            ("lesson_id", "version"),
            (value.lesson_id, value.version),
            payload,
            {
                "lesson_id": value.lesson_id,
                "version": value.version,
                "status": value.status.value,
                "available_at": payload["available_at"],
            },
            commit=commit,
        )

    def list_lesson_revisions(self, lesson_id: str) -> list[InvestmentLesson]:
        rows = self.connection.execute(
            "SELECT payload_json,content_hash FROM research_durable_lessons "
            "WHERE lesson_id=? ORDER BY version",
            (lesson_id,),
        ).fetchall()
        values = []
        for payload_json, digest in rows:
            if _content_hash(payload_json) != digest:
                raise PersistenceCorruptError("content hash mismatch in research_durable_lessons")
            try:
                values.append(_lesson_from(json.loads(payload_json)))
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                raise PersistenceCorruptError("invalid lesson payload") from exc
        return values

    def transition_lesson(
        self,
        lesson_id: str,
        target: LessonStatus,
        *,
        expected_version: int,
        sample_size: int | None = None,
        review_ref: str = "",
    ) -> InvestmentLesson:
        revisions = self.list_lesson_revisions(lesson_id)
        if not revisions:
            raise KeyError(lesson_id)
        current = revisions[-1]
        if current.version != expected_version:
            raise PersistenceConflictError("lesson version conflict")
        target = LessonStatus(target)
        allowed = {
            LessonStatus.OBSERVED: {
                LessonStatus.VALIDATING,
                LessonStatus.REJECTED,
                LessonStatus.EXPIRED,
            },
            LessonStatus.VALIDATING: {
                LessonStatus.PROMOTED,
                LessonStatus.REJECTED,
                LessonStatus.EXPIRED,
            },
            LessonStatus.PROMOTED: {LessonStatus.SUPERSEDED, LessonStatus.EXPIRED},
        }
        if target not in allowed.get(current.status, set()):
            raise PermissionError(f"invalid lesson transition {current.status.value}->{target.value}")
        next_sample = current.sample_size if sample_size is None else int(sample_size)
        if target is LessonStatus.PROMOTED and (next_sample < 3 or not review_ref):
            raise PermissionError("lesson promotion requires sample_size>=3 and deterministic review reference")
        next_value = replace(
            current,
            status=target,
            sample_size=next_sample,
            version=current.version + 1,
        )
        self._save_lesson_revision(next_value, review_ref=review_ref, commit=True)
        return next_value

    def save_signal(self, value: TradingSignal, *, _commit: bool = True) -> str:
        payload = _signal_payload(value)
        return self._insert(
            "research_durable_signals",
            ("signal_id",),
            (value.signal_id,),
            payload,
            {
                "signal_id": value.signal_id,
                "decision_time": payload["generated_at"],
                "valid_until": payload["valid_until"],
            },
            commit=_commit,
        )

    def get_signal(self, signal_id: str) -> TradingSignal | None:
        payload = self._load("research_durable_signals", "signal_id=?", (signal_id,))
        if not payload:
            return None
        try:
            return _signal_from(payload)
        except (KeyError, TypeError, ValueError) as exc:
            raise PersistenceCorruptError("invalid signal payload") from exc

    def save_intent(self, value: TradingIntentProposal, *, _commit: bool = True) -> str:
        payload = _intent_payload(value)
        return self._insert(
            "research_durable_intents",
            ("intent_id",),
            (value.intent_id,),
            payload,
            {"intent_id": value.intent_id, "valid_until": payload["valid_until"]},
            commit=_commit,
        )

    def get_intent(self, intent_id: str) -> TradingIntentProposal | None:
        payload = self._load("research_durable_intents", "intent_id=?", (intent_id,))
        if not payload:
            return None
        try:
            return _intent_from(payload)
        except (KeyError, TypeError, ValueError) as exc:
            raise PersistenceCorruptError("invalid intent payload") from exc

    def save_qualification_ref(
        self, value: StrategyQualificationEvidence, *, _commit: bool = True
    ) -> str:
        payload = value.to_public()
        return self._insert(
            "research_durable_qualifications",
            ("intent_id",),
            (value.intent_id,),
            payload,
            {
                "intent_id": value.intent_id,
                "strategy_id": value.strategy_id,
                "qualification_artifact_sha256": value.qualification_artifact_sha256,
            },
            commit=_commit,
        )

    def get_qualification_ref(self, intent_id: str) -> dict[str, Any] | None:
        return self._load(
            "research_durable_qualifications", "intent_id=?", (intent_id,)
        )

    def save_construction_audit(self, candidate: Any, *, _commit: bool = True) -> str:
        payload = candidate.to_public()
        if payload.get("authorizes_execution") is not False or payload.get("risk_approved") is not False:
            raise PermissionError("construction audit must remain proposal-only")
        return self._insert(
            "research_durable_construction",
            ("candidate_portfolio_id",),
            (candidate.candidate_portfolio_id,),
            payload,
            {
                "candidate_portfolio_id": candidate.candidate_portfolio_id,
                "request_id": candidate.request_id,
                "portfolio_snapshot_ref": candidate.portfolio_snapshot_ref,
            },
            commit=_commit,
        )

    def get_construction_audit(self, candidate_portfolio_id: str) -> dict[str, Any] | None:
        return self._load(
            "research_durable_construction",
            "candidate_portfolio_id=?",
            (candidate_portfolio_id,),
        )

    def _save_link(
        self,
        from_id: str,
        to_id: str,
        relation: str,
        *,
        commit: bool,
    ) -> str:
        payload = {"from_id": from_id, "to_id": to_id, "relation": relation}
        link_id = "rdlink_" + sha256(_canonical(payload).encode("utf-8")).hexdigest()[:24]
        return self._insert(
            "research_durable_links",
            ("link_id",),
            (link_id,),
            {"link_id": link_id, **payload},
            {
                "link_id": link_id,
                "from_id": from_id,
                "to_id": to_id,
                "relation": relation,
            },
            commit=commit,
        )

    def trace_links(self, record_id: str) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "SELECT payload_json,content_hash FROM research_durable_links "
            "WHERE from_id=? OR to_id=? ORDER BY relation,link_id",
            (record_id, record_id),
        ).fetchall()
        output = []
        for payload_json, digest in rows:
            if _content_hash(payload_json) != digest:
                raise PersistenceCorruptError("content hash mismatch in research_durable_links")
            try:
                output.append(json.loads(payload_json))
            except (TypeError, json.JSONDecodeError) as exc:
                raise PersistenceCorruptError("invalid audit link payload") from exc
        return output

    def persist_audit_bundle(
        self,
        *,
        decision: InvestmentDecisionRecord | None = None,
        outcome: DecisionOutcome | None = None,
        lesson: InvestmentLesson | None = None,
        signal: TradingSignal | None = None,
        intent: TradingIntentProposal | None = None,
        qualification: StrategyQualificationEvidence | None = None,
        candidate: Any = None,
    ) -> dict[str, str]:
        """Persist a linked audit unit atomically; never dispatch recovered data."""
        results: dict[str, str] = {}
        try:
            self.connection.execute("BEGIN IMMEDIATE")
            if decision is not None:
                results["decision"] = self.save_decision(decision, _commit=False)
            if outcome is not None:
                results["outcome"] = self.save_outcome(outcome, _commit=False)
            if lesson is not None:
                results["lesson"] = self.save_lesson(lesson, _commit=False)
            if signal is not None:
                results["signal"] = self.save_signal(signal, _commit=False)
            if intent is not None:
                results["intent"] = self.save_intent(intent, _commit=False)
            if qualification is not None:
                results["qualification"] = self.save_qualification_ref(
                    qualification, _commit=False
                )
            if candidate is not None:
                results["construction"] = self.save_construction_audit(
                    candidate, _commit=False
                )
            if decision is not None and signal is not None:
                self._save_link(
                    decision.decision_id,
                    signal.signal_id,
                    "DECISION_PRODUCED_SIGNAL",
                    commit=False,
                )
            if decision is not None and outcome is not None:
                self._save_link(
                    outcome.outcome_id,
                    decision.decision_id,
                    "OUTCOME_FOR_DECISION",
                    commit=False,
                )
            if lesson is not None:
                for decision_id in lesson.origin_decision_ids:
                    self._save_link(
                        lesson.lesson_id,
                        decision_id,
                        "LESSON_FROM_DECISION",
                        commit=False,
                    )
            if signal is not None and intent is not None:
                self._save_link(
                    signal.signal_id,
                    intent.intent_id,
                    "SIGNAL_PROPOSED_INTENT",
                    commit=False,
                )
            if intent is not None and qualification is not None:
                self._save_link(
                    intent.intent_id,
                    "qualification:" + qualification.qualification_artifact_sha256,
                    "INTENT_USES_QUALIFICATION",
                    commit=False,
                )
            if intent is not None and candidate is not None:
                self._save_link(
                    intent.intent_id,
                    candidate.candidate_portfolio_id,
                    "INTENT_CONSTRUCTED_CANDIDATE",
                    commit=False,
                )
            self.connection.commit()
            return results
        except Exception:
            self.connection.rollback()
            raise

    def recover_non_authoritative_state(self, *, at: datetime) -> dict[str, Any]:
        _dt(at)
        signals = []
        for payload in self._list("research_durable_signals", "decision_time,signal_id"):
            valid_until = _parse_dt(payload["valid_until"])
            signals.append({**payload, "expired": at > valid_until})
        intents = []
        for payload in self._list("research_durable_intents", "valid_until,intent_id"):
            valid_until = _parse_dt(payload["valid_until"])
            intents.append({**payload, "expired": at > valid_until})
        return {
            "signals": signals,
            "intents": intents,
            "replay_allowed": False,
            "authorizes_execution": False,
            "orders_created": 0,
            "cash_reserved": "0",
            "mode": "AUDIT_RECOVERY_ONLY",
        }

    def estimate_storage(self, record_count: int) -> dict[str, Any]:
        if record_count < 0:
            raise ValueError("record_count must be non-negative")
        return {
            "record_count": int(record_count),
            "estimated_bytes": int(record_count) * 6_000,
            "format": "typed-json-sqlite",
            "includes_large_artifacts": False,
        }

    @staticmethod
    def module_source() -> str:
        return inspect.getsource(inspect.getmodule(ResearchDurabilityStore))


__all__ = [
    "DURABILITY_SCHEMA_VERSION",
    "PersistenceBusyError",
    "PersistenceConflictError",
    "PersistenceCorruptError",
    "ResearchDurabilityStore",
    "UnsupportedSchemaVersion",
]
