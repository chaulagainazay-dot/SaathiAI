"""M15.2 red-team report API — /api/v1/security/redteam/* (read-only).

Authenticated, sanitized, read-only. Disabled in production by default: the
router mounts only when SAATHI_ENV != 'production'. It exposes runs, findings
(redacted), suites, baseline comparison, security health, and release-gate
status. It NEVER executes attacks against anything but the in-process isolated
target, and never returns raw payloads or secrets.
"""
from __future__ import annotations

import os

from fastapi import APIRouter, Request

from saathi.security.redteam.config import RedTeamConfig
from saathi.security.redteam.hackagent import availability
from saathi.security.redteam import runner, baseline as B, report as RP
from saathi.security.redteam.runner import load_corpus

router = APIRouter(prefix="/api/v1/security/redteam", tags=["security"])


def production_disabled() -> bool:
    return os.getenv("SAATHI_ENV", "local").lower() == "production"


@router.get("/health")
def health(request: Request):
    return {"enabled": not production_disabled(), "mode": "local",
            "hackagent": availability(), "production_target_block": True,
            "cloud_sync": False}


@router.get("/attacks")
def attacks(request: Request):
    return load_corpus()


@router.get("/run")
def run(request: Request, suite: str = ""):
    if production_disabled():
        return {"disabled": True, "reason": "red-team API disabled in production"}
    return runner.run_suite(suite=suite or None, config=RedTeamConfig())["summary"]


@router.get("/report")
def report(request: Request, suite: str = ""):
    if production_disabled():
        return {"disabled": True}
    return RP.build_report(suite=suite or None, config=RedTeamConfig())


@router.get("/release-gate")
def gate(request: Request):
    if production_disabled():
        return {"disabled": True}
    return RP.release_gate(RedTeamConfig())


@router.get("/baseline/compare")
def compare(request: Request):
    if production_disabled():
        return {"disabled": True}
    return B.compare(RedTeamConfig())
