"""M14 CEO OS API — /api/v1/ceo/* (auth inherited from /api/v1).

Every mutation is owner-scoped. Protected decision states (approve/reject/
implement) require an authenticated user (the middleware) and are never
performed by an agent. Missions execute through M10 only.
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from saathi.ceo.store import default_store
from saathi.ceo.service import CEOService
from saathi.ceo.agent import CEOAgent
from saathi.ceo.models import (
    DecisionStatus, PROTECTED_DECISION_STATES, validate_decision_transition,
    IllegalDecisionTransition,
)

router = APIRouter(prefix="/api/v1/ceo", tags=["ceo"])


def _user(request: Request) -> str:
    return getattr(request.state, "user_id", None) or "ajay"


class BusinessIn(BaseModel):
    name: str
    kind: str = "business"
    source: str = "manual"


class GoalIn(BaseModel):
    description: str
    business_id: str = ""
    unit: str = ""
    target_value: float = 0
    kpi_id: str = ""


class KPIIn(BaseModel):
    name: str
    kpi_type: str
    unit: str = ""
    target: float = 0
    source: str = ""


class ObservationIn(BaseModel):
    value: float
    source: str
    evidence_tier: str = "observed"


class DecisionIn(BaseModel):
    question: str
    context: str = ""
    options: list = []
    recommendation: str = ""


class DecisionResolve(BaseModel):
    status: str


class RiskIn(BaseModel):
    title: str
    category: str
    likelihood: float = 0.5
    impact: float = 0.5
    mitigation: str = ""


class OpportunityIn(BaseModel):
    title: str
    kind: str = ""
    value_estimate: float = 0
    effort: float = 0.5


class FinancialIn(BaseModel):
    kind: str
    state: str
    amount_usd: float
    label: str = ""


class MissionIn(BaseModel):
    objective: str
    strategy: str = "build"


@router.get("/portfolio")
def portfolio(request: Request):
    return CEOService(default_store()).portfolio_summary(_user(request))


@router.get("/brief")
def brief(request: Request):
    return CEOService(default_store()).daily_brief(_user(request))


@router.get("/briefs")
def briefs(request: Request, limit: int = 14):
    return {"briefs": default_store().list_briefs(_user(request), limit=limit)}


@router.post("/review/week")
def review_week(request: Request):
    return CEOService(default_store()).weekly_review(_user(request))


@router.get("/reviews")
def reviews(request: Request, kind: str | None = None):
    return {"reviews": default_store().list_reviews(_user(request), kind=kind)}


# ── businesses / goals ──────────────────────────────────────────────────────
@router.post("/businesses")
def create_business(req: BusinessIn, request: Request):
    return {"id": default_store().add_business(owner=_user(request), name=req.name,
                                              kind=req.kind, source=req.source)}


@router.get("/businesses")
def list_businesses(request: Request):
    return {"businesses": default_store().list_businesses(_user(request))}


@router.post("/goals")
def create_goal(req: GoalIn, request: Request):
    return {"id": default_store().add_goal(
        owner=_user(request), description=req.description, business_id=req.business_id,
        unit=req.unit, target_value=req.target_value, kpi_id=req.kpi_id)}


@router.get("/goals")
def list_goals(request: Request):
    st = default_store()
    goals = st.list_goals(_user(request))
    from saathi.ceo.kpi import goal_progress
    for g in goals:
        try:
            g["progress"] = goal_progress(st, g["id"])
        except Exception:
            g["progress"] = None
    return {"goals": goals}


# ── KPIs ────────────────────────────────────────────────────────────────────
@router.post("/kpis")
def create_kpi(req: KPIIn, request: Request):
    return {"id": default_store().add_kpi(owner=_user(request), name=req.name,
                                         kpi_type=req.kpi_type, unit=req.unit,
                                         target=req.target, source=req.source)}


@router.get("/kpis")
def list_kpis(request: Request):
    from saathi.ceo.kpi import compute_kpi
    st = default_store()
    return {"kpis": [compute_kpi(st, k["id"]).to_dict() for k in st.list_kpis(_user(request))]}


@router.post("/kpis/{kid}/observe")
def observe(kid: str, req: ObservationIn, request: Request):
    st = default_store()
    kdef = st.get_kpi(kid)
    if not kdef or kdef["owner"] != _user(request):
        return {"error": "not found"}
    return {"id": st.add_observation(kid, value=req.value, source=req.source,
                                    evidence_tier=req.evidence_tier)}


# ── decisions (protected finalization) ──────────────────────────────────────
@router.post("/decisions")
def create_decision(req: DecisionIn, request: Request):
    return {"id": default_store().add_decision(
        owner=_user(request), question=req.question, context=req.context,
        options=req.options, recommendation=req.recommendation)}


@router.get("/decisions")
def list_decisions(request: Request, status: str | None = None):
    return {"decisions": default_store().list_decisions(_user(request), status=status)}


@router.post("/decisions/{did}/resolve")
def resolve_decision(did: str, req: DecisionResolve, request: Request):
    """Protected states (approve/reject/implement) require an authenticated
    user — the middleware already guarantees that. Agents cannot reach here as
    a user; they only create `proposed` decisions."""
    st = default_store()
    d = st.get_decision(did)
    if not d or d["owner"] != _user(request):
        return {"error": "not found"}
    try:
        validate_decision_transition(DecisionStatus(d["status"]), DecisionStatus(req.status))
    except (IllegalDecisionTransition, ValueError) as exc:
        return {"error": str(exc)}
    st.set_decision_status(did, req.status, decided_by=f"user:{_user(request)}")
    return {"id": did, "status": req.status}


# ── risks / opportunities ───────────────────────────────────────────────────
@router.post("/risks")
def create_risk(req: RiskIn, request: Request):
    return {"id": default_store().add_risk(
        owner=_user(request), title=req.title, category=req.category,
        likelihood=req.likelihood, impact=req.impact, mitigation=req.mitigation)}


@router.get("/risks")
def list_risks(request: Request, status: str = "open"):
    return {"risks": default_store().list_risks(_user(request), status=status)}


@router.post("/risks/{rid}/to-mission")
def risk_to_mission(rid: str, request: Request):
    try:
        return CEOService(default_store()).convert_risk_to_mission(_user(request), rid)
    except PermissionError as exc:
        return {"error": str(exc)}


@router.post("/opportunities")
def create_opportunity(req: OpportunityIn, request: Request):
    return {"id": default_store().add_opportunity(
        owner=_user(request), title=req.title, kind=req.kind,
        value_estimate=req.value_estimate, effort=req.effort)}


@router.get("/opportunities")
def list_opportunities(request: Request):
    return {"opportunities": default_store().list_opportunities(_user(request))}


@router.post("/opportunities/{oid}/to-project")
def opportunity_to_project(oid: str, request: Request):
    try:
        return CEOService(default_store()).convert_opportunity_to_project(_user(request), oid)
    except PermissionError as exc:
        return {"error": str(exc)}


# ── finance ─────────────────────────────────────────────────────────────────
@router.post("/finance/entries")
def add_financial(req: FinancialIn, request: Request):
    return {"id": default_store().add_financial_entry(
        owner=_user(request), kind=req.kind, state=req.state,
        amount_usd=req.amount_usd, label=req.label, source="manual")}


@router.get("/finance/summary")
def finance_summary(request: Request):
    from saathi.ceo.finance import financial_summary
    return financial_summary(default_store(), _user(request))


# ── missions (via M10) ──────────────────────────────────────────────────────
@router.post("/missions")
def create_mission(req: MissionIn, request: Request):
    return CEOService(default_store()).create_mission(
        _user(request), req.objective, strategy=req.strategy)


# ── alerts ──────────────────────────────────────────────────────────────────
@router.get("/alerts")
def alerts(request: Request):
    return {"alerts": default_store().list_alerts(_user(request))}


# ── CEO agent (bounded proposals) ───────────────────────────────────────────
@router.get("/agent/recommendations")
def recommendations(request: Request):
    return {"recommendations": CEOAgent(default_store()).recommend_missions(_user(request)),
            "cannot_do": CEOAgent(default_store()).cannot_do()}
