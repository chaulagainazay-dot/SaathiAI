"""Auto-Repair API router — mounted under /api/v1/repair (auth inherited).

The global server middleware already requires auth for /api/v1/* (session,
SAATHI_TOKEN, or local). These routes never push/deploy and never expose
secrets. Code-modifying routes (`run`) default to diagnose-only unless the
caller explicitly opts into a safe repair.
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from saathi.repair import AutoRepairLoop, RepairIncident, RepairHistory
from saathi.repair.incident import RepairEvidence

router = APIRouter(prefix="/api/v1/repair", tags=["repair"])


class DiagnoseRequest(BaseModel):
    source: str = "user_report"
    command: str = ""
    expected_behavior: str = ""
    actual_behavior: str = ""
    exception_type: str | None = None
    stack_trace: str | None = None
    failed_tests: list[str] = []


class RunRequest(DiagnoseRequest):
    approve: bool = False  # explicit approval for Level-2 repairs


def _incident(req: DiagnoseRequest) -> RepairIncident:
    return RepairIncident(
        source=req.source, command=req.command,
        expected_behavior=req.expected_behavior,
        actual_behavior=req.actual_behavior,
        exception_type=req.exception_type, stack_trace=req.stack_trace,
        failed_tests=req.failed_tests, evidence=RepairEvidence(),
    )


@router.post("/diagnose")
def diagnose(req: DiagnoseRequest):
    inc = AutoRepairLoop().diagnose(_incident(req))
    return {"incident_id": inc.incident_id, "category": inc.category.value,
            "confidence": inc.confidence, "policy": inc.policy.value,
            "subsystem": inc.subsystem, "status": inc.status.value}


@router.post("/run")
def run(req: RunRequest):
    # NOTE: /run without a concrete strategy stays diagnose-only by design.
    out = AutoRepairLoop().run(_incident(req), approve=req.approve)
    return out.to_dict()


@router.get("/incidents")
def incidents():
    return {"incidents": RepairHistory().all()}


@router.get("/incidents/{incident_id}")
def incident(incident_id: str):
    rec = RepairHistory().get(incident_id)
    return rec or {"error": "not found"}
