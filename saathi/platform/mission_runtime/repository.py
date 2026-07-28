"""Persistence adapter for mission-runtime state on the authoritative PlatformStore."""
from __future__ import annotations

from typing import Any
import json

from saathi.platform.models import new_id
from saathi.platform.mission_runtime.models import (
    DEFAULT_USAGE,
    MissionRuntimeState,
    canonical_json,
    loads,
    validate_mission_transition,
    validate_task_transition,
)


RUNTIME_JSON_FIELDS = {
    "budget_json": "budget",
    "usage_json": "usage",
    "known_blockers_json": "known_blockers",
    "warning_json": "warnings",
}
NODE_JSON_FIELDS = {
    "arguments_json": "arguments",
    "verification_json": "verification",
}


def _row_dict(row: Any) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def _decode(row: dict[str, Any] | None, fields: dict[str, str]) -> dict[str, Any] | None:
    if row is None:
        return None
    out = dict(row)
    for raw_name, public_name in fields.items():
        fallback: Any = [] if public_name in {"known_blockers", "warnings", "verification"} else {}
        out[public_name] = loads(str(out.pop(raw_name, "") or ""), fallback)
    for key in ("cancel_requested", "requires_review", "concurrency_safe"):
        if key in out:
            out[key] = bool(out[key])
    return out


class MissionRuntimeRepository:
    """Small SQL adapter; lifecycle and authorization stay in the service."""

    def __init__(self, store):
        self.store = store

    def get_runtime(self, mission_id: str) -> dict[str, Any] | None:
        row = self.store._conn.execute(
            "SELECT * FROM mission_runtimes WHERE mission_id=?", (mission_id,)
        ).fetchone()
        return _decode(_row_dict(row), RUNTIME_JSON_FIELDS)

    def list_runtimes(
        self,
        *,
        org_id: str,
        workspace_id: str,
        project_id: str = "",
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        sql = "SELECT * FROM mission_runtimes WHERE org_id=? AND workspace_id=?"
        args: list[Any] = [org_id, workspace_id]
        if project_id:
            sql += " AND project_id=?"
            args.append(project_id)
        sql += " ORDER BY updated_at DESC LIMIT ?"
        args.append(max(1, min(int(limit), 500)))
        rows = self.store._conn.execute(sql, tuple(args)).fetchall()
        return [_decode(dict(row), RUNTIME_JSON_FIELDS) for row in rows]

    def replace_plan(
        self,
        *,
        runtime: dict[str, Any],
        nodes: list[dict[str, Any]],
        dependencies: list[tuple[str, str]],
    ) -> dict[str, Any]:
        """Persist a fully validated plan in one transaction."""

        mission_id = runtime["mission_id"]
        now = float(runtime["updated_at"])
        with self.store._runtime_lock, self.store._conn:
            prior = self.store._conn.execute(
                "SELECT state FROM mission_runtimes WHERE mission_id=?", (mission_id,)
            ).fetchone()
            if prior and prior["state"] not in {
                MissionRuntimeState.DRAFT.value,
                MissionRuntimeState.PLANNED.value,
            }:
                raise ValueError(f"mission plan is immutable in {prior['state']}")
            active = self.store._conn.execute(
                "SELECT COUNT(*) AS n FROM mission_runtime_nodes "
                "WHERE mission_id=? AND (status='RUNNING' OR attempt>0)",
                (mission_id,),
            ).fetchone()
            if active and int(active["n"]):
                raise ValueError("mission plan cannot replace attempted tasks")

            if prior:
                for table in (
                    "mission_runtime_certifications",
                    "mission_runtime_reviews",
                    "mission_runtime_checkpoints",
                    "mission_runtime_decisions",
                    "mission_runtime_evidence",
                ):
                    self.store._conn.execute(
                        f"DELETE FROM {table} WHERE mission_id=?", (mission_id,)
                    )
                self.store._conn.execute(
                    "DELETE FROM mission_runtime_dependencies WHERE mission_id=?",
                    (mission_id,),
                )
                self.store._conn.execute(
                    "DELETE FROM mission_runtime_nodes WHERE mission_id=?", (mission_id,)
                )
                self.store._conn.execute(
                    "UPDATE mission_runtimes SET objective=?, state='PLANNED', "
                    "max_parallel_tasks=?, budget_json=?, usage_json=?, "
                    "active_phase_id='', active_task_id='', active_agent='', "
                    "known_blockers_json='[]', warning_json='[]', stop_reason='', "
                    "cancel_requested=0, version=version+1, updated_at=? WHERE mission_id=?",
                    (
                        runtime["objective"],
                        runtime["max_parallel_tasks"],
                        canonical_json(runtime["budget"]),
                        canonical_json(DEFAULT_USAGE),
                        now,
                        mission_id,
                    ),
                )
            else:
                self.store._conn.execute(
                    "INSERT INTO mission_runtimes "
                    "(mission_id,org_id,workspace_id,project_id,owner_id,objective,state,"
                    "max_parallel_tasks,budget_json,usage_json,created_at,updated_at) "
                    "VALUES (?,?,?,?,?,?,'PLANNED',?,?,?,?,?)",
                    (
                        mission_id,
                        runtime["org_id"],
                        runtime["workspace_id"],
                        runtime["project_id"],
                        runtime["owner_id"],
                        runtime["objective"],
                        runtime["max_parallel_tasks"],
                        canonical_json(runtime["budget"]),
                        canonical_json(DEFAULT_USAGE),
                        now,
                        now,
                    ),
                )

            for node in nodes:
                self.store._conn.execute(
                    "INSERT INTO mission_runtime_nodes "
                    "(node_id,mission_id,parent_id,node_type,title,objective,status,"
                    "priority,position,agent_type,tool_id,capability,arguments_json,"
                    "approval_id,estimated_effort,token_estimate,max_retries,attempt,"
                    "not_before,requires_review,concurrency_safe,verification_json,"
                    "created_at,updated_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        node["node_id"],
                        mission_id,
                        node["parent_id"],
                        node["node_type"],
                        node["title"],
                        node["objective"],
                        node["status"],
                        node["priority"],
                        node["position"],
                        node["agent_type"],
                        node["tool_id"],
                        node["capability"],
                        canonical_json(node["arguments"]),
                        node["approval_id"],
                        node["estimated_effort"],
                        node["token_estimate"],
                        node["max_retries"],
                        0,
                        0.0,
                        int(node["requires_review"]),
                        int(node["concurrency_safe"]),
                        canonical_json(node["verification"]),
                        now,
                        now,
                    ),
                )
            for task_id, depends_on in dependencies:
                self.store._conn.execute(
                    "INSERT INTO mission_runtime_dependencies "
                    "(mission_id,task_id,depends_on_task_id,created_at) VALUES (?,?,?,?)",
                    (mission_id, task_id, depends_on, now),
                )
        return self.get_runtime(mission_id)

    def list_nodes(self, mission_id: str) -> list[dict[str, Any]]:
        rows = self.store._conn.execute(
            "SELECT * FROM mission_runtime_nodes WHERE mission_id=? "
            "ORDER BY position ASC, created_at ASC",
            (mission_id,),
        ).fetchall()
        return [_decode(dict(row), NODE_JSON_FIELDS) for row in rows]

    def get_node(self, mission_id: str, node_id: str) -> dict[str, Any] | None:
        row = self.store._conn.execute(
            "SELECT * FROM mission_runtime_nodes WHERE mission_id=? AND node_id=?",
            (mission_id, node_id),
        ).fetchone()
        return _decode(_row_dict(row), NODE_JSON_FIELDS)

    def dependencies(self, mission_id: str) -> list[dict[str, str]]:
        rows = self.store._conn.execute(
            "SELECT task_id,depends_on_task_id FROM mission_runtime_dependencies "
            "WHERE mission_id=? ORDER BY task_id,depends_on_task_id",
            (mission_id,),
        ).fetchall()
        return [
            {"task_id": row["task_id"], "depends_on_task_id": row["depends_on_task_id"]}
            for row in rows
        ]

    def transition_runtime(
        self, mission_id: str, target: str, **fields: Any
    ) -> dict[str, Any]:
        allowed = {
            "active_phase_id",
            "active_task_id",
            "active_agent",
            "latest_commit",
            "rollback_sha",
            "test_status",
            "browser_status",
            "stop_reason",
            "started_at",
            "finished_at",
            "last_checkpoint_at",
            "cancel_requested",
        }
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError(f"unsupported runtime fields: {sorted(unknown)}")
        with self.store._runtime_lock, self.store._conn:
            current = self.store._conn.execute(
                "SELECT state FROM mission_runtimes WHERE mission_id=?", (mission_id,)
            ).fetchone()
            if not current:
                raise KeyError(mission_id)
            validate_mission_transition(current["state"], target)
            assignments = ["state=?", "updated_at=?", "version=version+1"]
            values: list[Any] = [target, self.store._now()]
            for key, value in fields.items():
                assignments.append(f"{key}=?")
                values.append(int(value) if key == "cancel_requested" else value)
            values.append(mission_id)
            self.store._conn.execute(
                f"UPDATE mission_runtimes SET {','.join(assignments)} WHERE mission_id=?",
                tuple(values),
            )
        return self.get_runtime(mission_id)

    def update_runtime(self, mission_id: str, **fields: Any) -> dict[str, Any]:
        allowed = {
            "active_phase_id",
            "active_task_id",
            "active_agent",
            "latest_commit",
            "rollback_sha",
            "test_status",
            "browser_status",
            "stop_reason",
            "last_checkpoint_at",
            "max_parallel_tasks",
            "cancel_requested",
        }
        json_fields = {
            "budget": "budget_json",
            "usage": "usage_json",
            "known_blockers": "known_blockers_json",
            "warnings": "warning_json",
        }
        unknown = set(fields) - allowed - set(json_fields)
        if unknown:
            raise ValueError(f"unsupported runtime fields: {sorted(unknown)}")
        assignments = ["updated_at=?", "version=version+1"]
        values: list[Any] = [self.store._now()]
        for key, value in fields.items():
            column = json_fields.get(key, key)
            assignments.append(f"{column}=?")
            if key in json_fields:
                values.append(canonical_json(value))
            elif key == "cancel_requested":
                values.append(int(bool(value)))
            else:
                values.append(value)
        values.append(mission_id)
        with self.store._runtime_lock, self.store._conn:
            result = self.store._conn.execute(
                f"UPDATE mission_runtimes SET {','.join(assignments)} WHERE mission_id=?",
                tuple(values),
            )
            if result.rowcount != 1:
                raise KeyError(mission_id)
        return self.get_runtime(mission_id)

    def transition_task(
        self, mission_id: str, task_id: str, target: str, **fields: Any
    ) -> dict[str, Any]:
        allowed = {
            "attempt",
            "not_before",
            "approval_id",
            "execution_id",
            "outcome_summary",
            "error_code",
            "started_at",
            "finished_at",
        }
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError(f"unsupported task fields: {sorted(unknown)}")
        with self.store._runtime_lock, self.store._conn:
            current = self.store._conn.execute(
                "SELECT status FROM mission_runtime_nodes "
                "WHERE mission_id=? AND node_id=? AND node_type IN ('TASK','SUBTASK')",
                (mission_id, task_id),
            ).fetchone()
            if not current:
                raise KeyError(task_id)
            validate_task_transition(current["status"], target)
            assignments = ["status=?", "updated_at=?"]
            values: list[Any] = [target, self.store._now()]
            for key, value in fields.items():
                assignments.append(f"{key}=?")
                values.append(value)
            values.extend([mission_id, task_id])
            self.store._conn.execute(
                f"UPDATE mission_runtime_nodes SET {','.join(assignments)} "
                "WHERE mission_id=? AND node_id=?",
                tuple(values),
            )
        return self.get_node(mission_id, task_id)

    def update_task(
        self, mission_id: str, task_id: str, **fields: Any
    ) -> dict[str, Any]:
        allowed = {
            "approval_id",
            "execution_id",
            "outcome_summary",
            "error_code",
            "not_before",
            "attempt",
        }
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError(f"unsupported task fields: {sorted(unknown)}")
        assignments = ["updated_at=?"]
        values: list[Any] = [self.store._now()]
        for key, value in fields.items():
            assignments.append(f"{key}=?")
            values.append(value)
        values.extend([mission_id, task_id])
        with self.store._runtime_lock, self.store._conn:
            result = self.store._conn.execute(
                f"UPDATE mission_runtime_nodes SET {','.join(assignments)} "
                "WHERE mission_id=? AND node_id=? "
                "AND node_type IN ('TASK','SUBTASK')",
                tuple(values),
            )
            if result.rowcount != 1:
                raise KeyError(task_id)
        return self.get_node(mission_id, task_id)

    def add_evidence(
        self,
        *,
        mission_id: str,
        task_id: str = "",
        evidence_type: str,
        status: str,
        summary: str,
        reference: str = "",
        check_name: str = "",
        collected_by: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        evidence_id = new_id("mev_")
        created_at = self.store._now()
        self.store._conn.execute(
            "INSERT INTO mission_runtime_evidence "
            "(evidence_id,mission_id,task_id,evidence_type,status,summary,reference,"
            "check_name,collected_by,metadata_json,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                evidence_id,
                mission_id,
                task_id,
                evidence_type,
                status,
                summary,
                reference,
                check_name,
                collected_by,
                canonical_json(metadata or {}),
                created_at,
            ),
        )
        self.store._conn.commit()
        return {
            "evidence_id": evidence_id,
            "mission_id": mission_id,
            "task_id": task_id,
            "evidence_type": evidence_type,
            "status": status,
            "summary": summary,
            "reference": reference,
            "check_name": check_name,
            "collected_by": collected_by,
            "metadata": dict(metadata or {}),
            "created_at": created_at,
        }

    def evidence(self, mission_id: str, *, limit: int = 500) -> list[dict[str, Any]]:
        rows = self.store._conn.execute(
            "SELECT * FROM mission_runtime_evidence WHERE mission_id=? "
            "ORDER BY created_at DESC LIMIT ?",
            (mission_id, max(1, min(int(limit), 2000))),
        ).fetchall()
        out = []
        for row in rows:
            item = dict(row)
            item["metadata"] = loads(item.pop("metadata_json", ""), {})
            out.append(item)
        return out

    def add_decision(
        self,
        *,
        mission_id: str,
        task_id: str = "",
        decision_type: str,
        outcome: str,
        reason: str,
        policy: str,
        human_approval_required: bool = False,
        actor: str = "",
    ) -> dict[str, Any]:
        decision_id = new_id("mdc_")
        created_at = self.store._now()
        self.store._conn.execute(
            "INSERT INTO mission_runtime_decisions "
            "(decision_id,mission_id,task_id,decision_type,outcome,reason,policy,"
            "human_approval_required,actor,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                decision_id,
                mission_id,
                task_id,
                decision_type,
                outcome,
                reason,
                policy,
                int(human_approval_required),
                actor,
                created_at,
            ),
        )
        self.store._conn.commit()
        return {
            "decision_id": decision_id,
            "mission_id": mission_id,
            "task_id": task_id,
            "decision_type": decision_type,
            "outcome": outcome,
            "reason": reason,
            "policy": policy,
            "human_approval_required": bool(human_approval_required),
            "actor": actor,
            "created_at": created_at,
        }

    def decisions(self, mission_id: str, *, limit: int = 500) -> list[dict[str, Any]]:
        rows = self.store._conn.execute(
            "SELECT * FROM mission_runtime_decisions WHERE mission_id=? "
            "ORDER BY created_at DESC LIMIT ?",
            (mission_id, max(1, min(int(limit), 2000))),
        ).fetchall()
        return [
            {**dict(row), "human_approval_required": bool(row["human_approval_required"])}
            for row in rows
        ]

    def add_checkpoint(self, payload: dict[str, Any]) -> dict[str, Any]:
        checkpoint_id = new_id("mcp_")
        created_at = self.store._now()
        self.store._conn.execute(
            "INSERT INTO mission_runtime_checkpoints "
            "(checkpoint_id,mission_id,current_phase_id,active_task_id,active_agent,"
            "completed_tasks_json,pending_tasks_json,resource_usage_json,latest_commit,"
            "rollback_sha,test_status,browser_status,known_blockers_json,snapshot_hash,"
            "created_by,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                checkpoint_id,
                payload["mission_id"],
                payload.get("current_phase_id", ""),
                payload.get("active_task_id", ""),
                payload.get("active_agent", ""),
                canonical_json(payload.get("completed_tasks", [])),
                canonical_json(payload.get("pending_tasks", [])),
                canonical_json(payload.get("resource_usage", {})),
                payload.get("latest_commit", ""),
                payload.get("rollback_sha", ""),
                payload.get("test_status", "NOT_RUN"),
                payload.get("browser_status", "NOT_RUN"),
                canonical_json(payload.get("known_blockers", [])),
                payload["snapshot_hash"],
                payload.get("created_by", ""),
                created_at,
            ),
        )
        self.store._conn.commit()
        return {
            "checkpoint_id": checkpoint_id,
            **payload,
            "created_at": created_at,
        }

    def checkpoints(self, mission_id: str, *, limit: int = 100) -> list[dict[str, Any]]:
        rows = self.store._conn.execute(
            "SELECT * FROM mission_runtime_checkpoints WHERE mission_id=? "
            "ORDER BY created_at DESC LIMIT ?",
            (mission_id, max(1, min(int(limit), 500))),
        ).fetchall()
        out = []
        for row in rows:
            item = dict(row)
            for raw_name, public_name, fallback in (
                ("completed_tasks_json", "completed_tasks", []),
                ("pending_tasks_json", "pending_tasks", []),
                ("resource_usage_json", "resource_usage", {}),
                ("known_blockers_json", "known_blockers", []),
            ):
                item[public_name] = loads(item.pop(raw_name, ""), fallback)
            out.append(item)
        return out

    def add_review(
        self,
        *,
        mission_id: str,
        task_id: str,
        reviewer_agent: str,
        verdict: str,
        findings: list[str],
        evidence_ids: list[str],
    ) -> dict[str, Any]:
        review_id = new_id("mrv_")
        created_at = self.store._now()
        self.store._conn.execute(
            "INSERT INTO mission_runtime_reviews "
            "(review_id,mission_id,task_id,reviewer_agent,verdict,findings_json,"
            "evidence_ids_json,created_at) VALUES (?,?,?,?,?,?,?,?)",
            (
                review_id,
                mission_id,
                task_id,
                reviewer_agent,
                verdict,
                canonical_json(findings),
                canonical_json(evidence_ids),
                created_at,
            ),
        )
        self.store._conn.commit()
        return {
            "review_id": review_id,
            "mission_id": mission_id,
            "task_id": task_id,
            "reviewer_agent": reviewer_agent,
            "verdict": verdict,
            "findings": findings,
            "evidence_ids": evidence_ids,
            "created_at": created_at,
        }

    def reviews(self, mission_id: str) -> list[dict[str, Any]]:
        rows = self.store._conn.execute(
            "SELECT * FROM mission_runtime_reviews WHERE mission_id=? "
            "ORDER BY created_at DESC",
            (mission_id,),
        ).fetchall()
        out = []
        for row in rows:
            item = dict(row)
            item["findings"] = loads(item.pop("findings_json", ""), [])
            item["evidence_ids"] = loads(item.pop("evidence_ids_json", ""), [])
            out.append(item)
        return out

    def add_certification(
        self,
        *,
        mission_id: str,
        verdict: str,
        summary: str,
        evidence_ids: list[str],
        limitations: list[str],
        certified_by: str,
        snapshot_hash: str,
    ) -> dict[str, Any]:
        certification_id = new_id("mcert_")
        created_at = self.store._now()
        self.store._conn.execute(
            "INSERT INTO mission_runtime_certifications "
            "(certification_id,mission_id,verdict,summary,evidence_ids_json,"
            "limitations_json,certified_by,snapshot_hash,created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (
                certification_id,
                mission_id,
                verdict,
                summary,
                canonical_json(evidence_ids),
                canonical_json(limitations),
                certified_by,
                snapshot_hash,
                created_at,
            ),
        )
        self.store._conn.commit()
        return {
            "certification_id": certification_id,
            "mission_id": mission_id,
            "verdict": verdict,
            "summary": summary,
            "evidence_ids": evidence_ids,
            "limitations": limitations,
            "certified_by": certified_by,
            "snapshot_hash": snapshot_hash,
            "created_at": created_at,
        }

    def certifications(self, mission_id: str) -> list[dict[str, Any]]:
        rows = self.store._conn.execute(
            "SELECT * FROM mission_runtime_certifications WHERE mission_id=? "
            "ORDER BY created_at DESC",
            (mission_id,),
        ).fetchall()
        out = []
        for row in rows:
            item = dict(row)
            item["evidence_ids"] = loads(item.pop("evidence_ids_json", ""), [])
            item["limitations"] = loads(item.pop("limitations_json", ""), [])
            out.append(item)
        return out
