"""FastAPI router — BMA endpoints mounted at /api/v1/bma."""
from __future__ import annotations
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any, Optional

from ..models import StudentInput, Skill
from .master import get_master

router = APIRouter(prefix="/api/v1/bma", tags=["BMA"])


class BMARequest(BaseModel):
    student_id: str
    text: str
    skill: Optional[str] = None       # "writing"|"speaking"|"reading"|"listening"|"grammar"|"vocabulary"
    metadata: dict[str, Any] = {}


class BMAResponse(BaseModel):
    student_id: str
    skill: str
    response: str
    feedback: Optional[str] = None
    corrections: list[dict] = []
    band_estimate: Optional[float] = None
    xp_delta: int = 0
    reflection_notes: list[str] = []
    safe: bool = True


@router.post("/chat", response_model=BMAResponse)
async def bma_chat(req: BMARequest):
    """
    Master agent loop endpoint.
    Detects skill automatically if not provided, runs the full
    Perception → Decision → Action → Reflection cycle.
    """
    skill_enum: Optional[Skill] = None
    if req.skill:
        try:
            skill_enum = Skill(req.skill.lower())
        except ValueError:
            raise HTTPException(400, f"Unknown skill: {req.skill}")

    student_input = StudentInput(
        student_id=req.student_id,
        text=req.text,
        skill=skill_enum,
        metadata=req.metadata,
    )

    try:
        master = get_master()
        result = await master.run_loop(student_input)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"BMA error: {e}")

    return BMAResponse(
        student_id=result.student_id,
        skill=result.skill,
        response=result.response,
        feedback=result.feedback,
        corrections=result.corrections,
        band_estimate=result.band_estimate,
        xp_delta=result.xp_delta,
        reflection_notes=result.reflection_notes,
        safe=result.safe,
    )


@router.get("/memory/{student_id}")
async def get_memory(student_id: str):
    """Return working memory context and cross-skill patterns for a student."""
    master = get_master()
    context = master.memory.get_context(student_id)
    patterns = master.bus.get_cross_patterns(student_id)
    return {"student_id": student_id, "context": context, "cross_patterns": patterns}


@router.delete("/memory/{student_id}")
async def clear_memory(student_id: str):
    """Clear working memory for a student (e.g., end of session)."""
    master = get_master()
    master.memory.working.clear(student_id)
    master.bus.reset(student_id)
    return {"ok": True}
