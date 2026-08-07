"""M220 — Trust & Approval Pipeline.

Before any future broker can exist, require multi-stage human approvals.
Nothing becomes active automatically. Never grants live trading.
"""
from __future__ import annotations

import json
import time
from typing import Any

from saathi.platform.tg.broker_sandbox.models import (
    REQUIRED_TRUST_STAGES,
    TrustApprovalStage,
    TrustPipelineStatus,
)
from saathi.platform.tg.broker_sandbox.store import SandboxStore, _uid


class TrustPipelineError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


class TrustApprovalPipeline:
    def __init__(self, store: SandboxStore):
        self.store = store

    def _empty_stages(self) -> dict[str, Any]:
        return {
            s.value: {
                "status": "PENDING",
                "actor": None,
                "reason": None,
                "decided_at": None,
            }
            for s in REQUIRED_TRUST_STAGES
        }

    def create_pipeline(
        self,
        broker_id: str,
        *,
        created_by: str,
        paper_graduation_ref: str = "",
        notes: str = "",
    ) -> dict[str, Any]:
        if broker_id.startswith("catalog.") is False and broker_id != "sandbox.emulator":
            # Still allow any id for architecture tests, but mark
            pass
        pid = _uid("tp")
        now = time.time()
        stages = self._empty_stages()
        self.store.execute(
            """INSERT INTO bs_trust_pipelines(
                id, broker_id, status, stages_json, paper_graduation_ref, notes,
                created_by, created_at, updated_at, completed_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (
                pid, broker_id, TrustPipelineStatus.DRAFT.value,
                json.dumps(stages), paper_graduation_ref, notes,
                created_by, now, now, None,
            ),
        )
        self.store.audit(
            "trust.pipeline_created",
            actor=created_by,
            subject=pid,
            detail={"broker_id": broker_id},
        )
        return self.get_pipeline(pid)

    def get_pipeline(self, pipeline_id: str) -> dict[str, Any]:
        row = self.store.fetchone("SELECT * FROM bs_trust_pipelines WHERE id=?", (pipeline_id,))
        if not row:
            raise TrustPipelineError("PIPELINE_NOT_FOUND", pipeline_id)
        decisions = self.store.fetchall(
            "SELECT * FROM bs_trust_decisions WHERE pipeline_id=? ORDER BY created_at",
            (pipeline_id,),
        )
        stages = json.loads(row["stages_json"] or "{}")
        return {
            "id": row["id"],
            "broker_id": row["broker_id"],
            "status": row["status"],
            "stages": stages,
            "required_stages": [s.value for s in REQUIRED_TRUST_STAGES],
            "paper_graduation_ref": row["paper_graduation_ref"],
            "notes": row["notes"],
            "created_by": row["created_by"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "completed_at": row["completed_at"],
            "decisions": [
                {
                    "id": d["id"],
                    "stage": d["stage"],
                    "decision": d["decision"],
                    "actor": d["actor"],
                    "actor_role": d["actor_role"],
                    "reason": d["reason"],
                    "created_at": d["created_at"],
                }
                for d in decisions
            ],
            "all_approved": all(
                stages.get(s.value, {}).get("status") == "APPROVED"
                for s in REQUIRED_TRUST_STAGES
            ),
            "live_authorized": False,  # hard lock
            "auto_activated": False,
            "paper_only": True,
            "sandbox_only": True,
        }

    def list_pipelines(self, broker_id: str = "") -> list[dict[str, Any]]:
        if broker_id:
            rows = self.store.fetchall(
                "SELECT id FROM bs_trust_pipelines WHERE broker_id=? ORDER BY created_at DESC",
                (broker_id,),
            )
        else:
            rows = self.store.fetchall(
                "SELECT id FROM bs_trust_pipelines ORDER BY created_at DESC"
            )
        return [self.get_pipeline(r["id"]) for r in rows]

    def decide(
        self,
        pipeline_id: str,
        *,
        stage: str,
        decision: str,
        actor: str,
        actor_role: str = "",
        reason: str = "",
    ) -> dict[str, Any]:
        pipe = self.get_pipeline(pipeline_id)
        if pipe["status"] in (
            TrustPipelineStatus.REJECTED.value,
            TrustPipelineStatus.REVOKED.value,
        ):
            raise TrustPipelineError(
                "PIPELINE_CLOSED",
                f"Pipeline is {pipe['status']}; no further decisions",
            )

        stage_u = stage.upper()
        valid = {s.value for s in TrustApprovalStage}
        if stage_u not in valid:
            raise TrustPipelineError("INVALID_STAGE", stage)

        # LLM cannot approve — enforce by role
        if actor_role.upper() in ("LLM", "AI", "ASSISTANT", "AGENT") or actor.lower().startswith("llm:"):
            raise TrustPipelineError(
                "LLM_APPROVAL_FORBIDDEN",
                "LLM may not approve trust stages",
            )

        dec = decision.lower()
        if dec not in ("approve", "reject"):
            raise TrustPipelineError("INVALID_DECISION", decision)

        now = time.time()
        did = _uid("tdec")
        self.store.execute(
            """INSERT INTO bs_trust_decisions(
                id, pipeline_id, stage, decision, actor, actor_role, reason, created_at
            ) VALUES(?,?,?,?,?,?,?,?)""",
            (did, pipeline_id, stage_u, dec, actor, actor_role, reason, now),
        )

        stages = pipe["stages"]
        if dec == "reject":
            stages[stage_u] = {
                "status": "REJECTED",
                "actor": actor,
                "reason": reason,
                "decided_at": now,
            }
            status = TrustPipelineStatus.REJECTED.value
            completed = now
        else:
            stages[stage_u] = {
                "status": "APPROVED",
                "actor": actor,
                "reason": reason,
                "decided_at": now,
            }
            all_ok = all(
                stages.get(s.value, {}).get("status") == "APPROVED"
                for s in REQUIRED_TRUST_STAGES
            )
            if all_ok:
                # Fully approved for SANDBOX only — never live
                status = TrustPipelineStatus.FULLY_APPROVED_SANDBOX.value
                completed = now
            else:
                status = TrustPipelineStatus.IN_PROGRESS.value
                completed = None

        self.store.execute(
            """UPDATE bs_trust_pipelines SET stages_json=?, status=?, updated_at=?, completed_at=?
               WHERE id=?""",
            (json.dumps(stages), status, now, completed, pipeline_id),
        )
        self.store.audit(
            "trust.decision",
            actor=actor,
            subject=pipeline_id,
            detail={"stage": stage_u, "decision": dec, "status": status, "live_authorized": False},
        )
        out = self.get_pipeline(pipeline_id)
        # Invariant: never live
        assert out["live_authorized"] is False
        assert out["auto_activated"] is False
        return out

    def require_all_stages(self, pipeline_id: str) -> dict[str, Any]:
        """Gate: nothing becomes active without full approval."""
        pipe = self.get_pipeline(pipeline_id)
        missing = [
            s.value for s in REQUIRED_TRUST_STAGES
            if pipe["stages"].get(s.value, {}).get("status") != "APPROVED"
        ]
        allowed = pipe["status"] == TrustPipelineStatus.FULLY_APPROVED_SANDBOX.value
        return {
            "pipeline_id": pipeline_id,
            "broker_id": pipe["broker_id"],
            "allowed_sandbox": allowed,
            "allowed_live": False,  # hard lock
            "missing_stages": missing,
            "status": pipe["status"],
            "paper_only": True,
            "message": (
                "Sandbox activation permitted after full multi-stage approval only."
                if allowed
                else "Activation blocked until all approval stages complete."
            ),
        }

    def attempt_activate_without_approval(self, broker_id: str) -> dict[str, Any]:
        """Negative path: automatic activation is impossible."""
        self.store.audit(
            "trust.auto_activate_refused",
            subject=broker_id,
            detail={"reason": "NO_AUTOMATIC_ACTIVATION"},
        )
        return {
            "ok": False,
            "error": "APPROVAL_REQUIRED",
            "broker_id": broker_id,
            "live_authorized": False,
            "message": (
                "Nothing becomes active automatically. Owner, security, credential, risk, "
                "environment, simulation, paper graduation, and manual confirmation are required."
            ),
            "paper_only": True,
        }


__all__ = ["TrustApprovalPipeline", "TrustPipelineError"]
