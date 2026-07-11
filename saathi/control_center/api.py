"""M16 Control Center API — /api/v1/control/* (authenticated, READ-ONLY).

Owner-scoped aggregation + search + action descriptors. This router NEVER
mutates: mutations go to canonical subsystem APIs (connectors/security/ceo)
whose descriptors it returns. Partial subsystem failure degrades to typed cells,
never a 500. Same auth model as the other routers (request.state.user_id).
"""
from __future__ import annotations

from fastapi import APIRouter, Request

from saathi.control_center.aggregator import ControlCenterAggregator
from saathi.control_center import search as _search
from saathi.control_center import actions as _actions

router = APIRouter(prefix="/api/v1/control", tags=["control-center"])


def _user(request: Request) -> str:
    return getattr(request.state, "user_id", None) or "ajay"


@router.get("/overview")
def overview(request: Request):
    return ControlCenterAggregator(_user(request)).overview()


@router.get("/attention")
def attention(request: Request):
    agg = ControlCenterAggregator(_user(request))
    ov = agg.overview()
    return {"items": ov["requires_attention"], "generated_at": ov["generated_at"]}


@router.get("/health")
def platform_health(request: Request):
    return ControlCenterAggregator(_user(request)).platform_health().to_dict()


@router.get("/security")
def security(request: Request):
    return ControlCenterAggregator(_user(request)).security_posture().to_dict()


@router.get("/providers")
def providers(request: Request):
    return ControlCenterAggregator(_user(request)).provider_matrix().to_dict()


@router.get("/release")
def release(request: Request):
    return ControlCenterAggregator(_user(request)).release_readiness().to_dict()


@router.get("/computer")
def computer(request: Request):
    return ControlCenterAggregator(_user(request)).computer_agent().to_dict()


@router.get("/timeline")
def timeline(request: Request, limit: int = 25):
    return ControlCenterAggregator(_user(request)).recent_events(limit=limit).to_dict()


@router.get("/approvals")
def approvals(request: Request):
    return ControlCenterAggregator(_user(request)).pending_approvals().to_dict()


@router.get("/search")
def search(request: Request, q: str = "", types: str = "", limit: int = 30):
    et = [t for t in types.split(",") if t] or None
    return _search.federated_search(owner=_user(request), query=q,
                                    entity_types=et, limit=limit)


@router.get("/actions")
def actions(request: Request):
    return {"actions": _actions.catalog()}
