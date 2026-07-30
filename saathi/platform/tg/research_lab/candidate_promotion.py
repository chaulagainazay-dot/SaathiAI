"""M278 — Research candidate promotion with hard gates and human review."""
from __future__ import annotations

import json
import time
from typing import Any

from saathi.platform.tg.research_lab.errors import ResearchLabError
from saathi.platform.tg.research_lab.models import (
    AUTHORITY_VALUES,
    HUMAN_REVIEW_REQUIRED_FOR_PAPER_CANDIDATE,
    PAPER_CANDIDATE_MEANING,
    PROMOTION_HARD_GATES,
    CandidateState,
)
from saathi.platform.tg.research_lab.storage import ResearchLabStore, evidence_hash, _uid


class CandidatePromotionEngine:
    def __init__(self, store: ResearchLabStore):
        self.store = store

    def evaluate(
        self,
        subject_type: str,
        subject_id: str,
        *,
        gates: dict[str, Any] | None = None,
        oos_failed: bool = False,
        robustness_failed: bool = False,
        stress_breaches: int = 0,
        evidence_complete: bool = False,
        pre_registered: bool = False,
        human_review_override: bool = False,
        llm_override: bool = False,
        actor: str = "system",
    ) -> dict[str, Any]:
        if llm_override or human_review_override is True and actor == "llm":
            raise ResearchLabError(
                "LLM_GATE_OVERRIDE_BLOCKED",
                "LLM may not bypass candidate promotion gates",
            )

        g = dict(PROMOTION_HARD_GATES)
        if gates:
            g.update(gates)

        # Force human review requirement
        g["human_review_required"] = True
        if not HUMAN_REVIEW_REQUIRED_FOR_PAPER_CANDIDATE:
            raise ResearchLabError("POLICY_CORRUPTION", "human review invariant broken")

        failures = []
        if oos_failed:
            failures.append("out_of_sample_failed")
        if robustness_failed:
            failures.append("robustness_failed")
        if stress_breaches > 0:
            failures.append("stress_breaches")
        if not pre_registered:
            failures.append("not_pre_registered")
        if not evidence_complete:
            failures.append("evidence_incomplete")
        if g.get("authority_violation"):
            failures.append("authority_violation")

        # Evaluate required hard gates presence
        for key, expected in PROMOTION_HARD_GATES.items():
            if key == "authority_violation":
                if g.get(key) is True:
                    failures.append("authority_violation")
                continue
            if key == "human_review_required":
                continue
            if expected is True and not g.get(key):
                failures.append(f"gate_missing:{key}")

        state = CandidateState.RESEARCH_ONLY
        if "not_pre_registered" in failures or "gate_missing:pre_registered_experiment" in failures:
            state = CandidateState.DATA_BLOCKED
        elif oos_failed:
            state = CandidateState.VALIDATION_FAILED
        elif robustness_failed:
            state = CandidateState.ROBUSTNESS_FAILED
        elif stress_breaches > 0:
            state = CandidateState.STRESS_FAILED
        elif failures:
            state = CandidateState.REJECTED
        else:
            # Eligible only for committee review — not auto paper candidate
            state = CandidateState.COMMITTEE_REVIEW_REQUIRED

        # PAPER_CANDIDATE requires human approval step (separate method)
        result = {
            "ok": True,
            "subject_type": subject_type,
            "subject_id": subject_id,
            "state": state.value,
            "gates": g,
            "gate_failures": failures,
            "human_review_status": "REQUIRED",
            "paper_candidate_meaning": PAPER_CANDIDATE_MEANING,
            "paper_candidate_authorises_execution": False,
            "automatic_paper_execution": False,
            "promotion_to_paper_candidate": False,
            "limitations": [
                "Promotion only marks eligibility for future paper simulation review",
                "Human approval remains required",
                "Does not enable order execution",
            ],
            **AUTHORITY_VALUES,
        }
        eh = evidence_hash(result)
        result["evidence_hash"] = eh
        cid = _uid("cand")
        now = time.time()
        self.store.execute(
            "INSERT INTO rl_candidates(id, subject_type, subject_id, state, gates_json, result_json, "
            "evidence_hash, human_review_status, created_at, updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (cid, subject_type, subject_id, state.value, json.dumps(g, sort_keys=True),
             json.dumps(result, sort_keys=True, default=str), eh, "REQUIRED", now, now),
        )
        self.store.audit("candidate.evaluated", actor=actor, subject=subject_id,
                         detail={"state": state.value, "failures": failures})
        result["candidate_id"] = cid
        return result

    def human_approve_paper_candidate(
        self,
        candidate_id: str,
        *,
        actor: str,
        with_limitations: bool = True,
    ) -> dict[str, Any]:
        if not actor or actor in ("system", "llm", "automated"):
            raise ResearchLabError(
                "HUMAN_REVIEW_BYPASS_DETECTED",
                "Paper candidate approval requires a human actor",
                detail={"actor": actor},
            )
        row = self.store.fetchone("SELECT * FROM rl_candidates WHERE id=?", (candidate_id,))
        if not row:
            raise ResearchLabError("CANDIDATE_NOT_FOUND", candidate_id)
        if row["state"] != CandidateState.COMMITTEE_REVIEW_REQUIRED.value:
            raise ResearchLabError(
                "CANDIDATE_PROMOTION_GATE_FAILED",
                f"Cannot promote from state {row['state']}",
            )
        state = (
            CandidateState.PAPER_CANDIDATE_WITH_LIMITATIONS
            if with_limitations
            else CandidateState.PAPER_CANDIDATE
        )
        result = json.loads(row["result_json"])
        result["state"] = state.value
        result["human_review_status"] = "APPROVED"
        result["approved_by"] = actor
        result["promotion_to_paper_candidate"] = True
        result["paper_candidate_authorises_execution"] = False
        result["paper_candidate_meaning"] = PAPER_CANDIDATE_MEANING
        eh = evidence_hash(result)
        self.store.execute(
            "UPDATE rl_candidates SET state=?, result_json=?, evidence_hash=?, "
            "human_review_status=?, updated_at=? WHERE id=?",
            (state.value, json.dumps(result, sort_keys=True, default=str), eh, "APPROVED", time.time(), candidate_id),
        )
        self.store.audit("candidate.human_approved", actor=actor, subject=candidate_id,
                         detail={"state": state.value})
        return {"ok": True, "candidate_id": candidate_id, **result}

    def reject(self, candidate_id: str, reason: str, *, actor: str = "system") -> dict[str, Any]:
        row = self.store.fetchone("SELECT * FROM rl_candidates WHERE id=?", (candidate_id,))
        if not row:
            raise ResearchLabError("CANDIDATE_NOT_FOUND", candidate_id)
        result = json.loads(row["result_json"])
        result["state"] = CandidateState.REJECTED.value
        result["rejection_reason"] = reason
        result["human_review_status"] = "REJECTED"
        eh = evidence_hash(result)
        self.store.execute(
            "UPDATE rl_candidates SET state=?, result_json=?, evidence_hash=?, "
            "human_review_status=?, updated_at=? WHERE id=?",
            (CandidateState.REJECTED.value, json.dumps(result, sort_keys=True, default=str),
             eh, "REJECTED", time.time(), candidate_id),
        )
        self.store.audit("candidate.rejected", actor=actor, subject=candidate_id, detail={"reason": reason})
        return {"ok": True, "state": CandidateState.REJECTED.value, "reason": reason, **AUTHORITY_VALUES}

    def revoke(self, candidate_id: str, reason: str, *, actor: str = "system") -> dict[str, Any]:
        row = self.store.fetchone("SELECT * FROM rl_candidates WHERE id=?", (candidate_id,))
        if not row:
            raise ResearchLabError("CANDIDATE_NOT_FOUND", candidate_id)
        if row["state"] not in (
            CandidateState.PAPER_CANDIDATE.value,
            CandidateState.PAPER_CANDIDATE_WITH_LIMITATIONS.value,
            CandidateState.COMMITTEE_REVIEW_REQUIRED.value,
        ):
            raise ResearchLabError("REVOKE_INVALID_STATE", f"Cannot revoke from {row['state']}")
        result = json.loads(row["result_json"])
        result["state"] = CandidateState.REVOKED.value
        result["revocation_reason"] = reason
        result["human_review_status"] = "REVOKED"
        eh = evidence_hash(result)
        self.store.execute(
            "UPDATE rl_candidates SET state=?, result_json=?, evidence_hash=?, "
            "human_review_status=?, updated_at=? WHERE id=?",
            (CandidateState.REVOKED.value, json.dumps(result, sort_keys=True, default=str),
             eh, "REVOKED", time.time(), candidate_id),
        )
        self.store.audit("candidate.revoked", actor=actor, subject=candidate_id, detail={"reason": reason})
        return {"ok": True, "state": CandidateState.REVOKED.value, "reason": reason, **AUTHORITY_VALUES}

    def list(self, state: str | None = None, limit: int = 100) -> dict[str, Any]:
        if state:
            rows = self.store.fetchall(
                "SELECT id, subject_type, subject_id, state, human_review_status, created_at, updated_at "
                "FROM rl_candidates WHERE state=? ORDER BY updated_at DESC LIMIT ?",
                (state, limit),
            )
        else:
            rows = self.store.fetchall(
                "SELECT id, subject_type, subject_id, state, human_review_status, created_at, updated_at "
                "FROM rl_candidates ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            )
        return {"ok": True, "count": len(rows), "candidates": rows, **AUTHORITY_VALUES}

    def get(self, candidate_id: str) -> dict[str, Any]:
        row = self.store.fetchone("SELECT * FROM rl_candidates WHERE id=?", (candidate_id,))
        if not row:
            return {"ok": False, "code": "CANDIDATE_NOT_FOUND", **AUTHORITY_VALUES}
        result = json.loads(row["result_json"])
        return {
            "ok": True,
            "candidate_id": row["id"],
            "subject_type": row["subject_type"],
            "subject_id": row["subject_id"],
            "state": row["state"],
            "human_review_status": row["human_review_status"],
            "result": result,
            **AUTHORITY_VALUES,
        }
