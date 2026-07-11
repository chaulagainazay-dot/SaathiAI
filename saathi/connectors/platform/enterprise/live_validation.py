"""M15.3 live connector validation framework.

Declares HOW each connector is validated and at what mode. Standard CI runs only
contract / deterministic / safe-sandbox. Live modes are credentials-gated and
NEVER run without explicit authorization + present credentials. The framework
reports honest per-connector status (implemented/configured/authenticated/
live-tested/environment-blocked) — it never fakes a live result.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum

from saathi.connectors.platform import registry as R


class ValidationMode(str, Enum):
    CONTRACT = "contract"
    DETERMINISTIC = "deterministic"
    SANDBOX = "sandbox"
    LIVE_READ_ONLY = "live_read_only"
    LIVE_REVERSIBLE = "live_reversible"
    LIVE_SIDE_EFFECT = "live_side_effect"


# modes safe to run in standard CI (no live external calls)
CI_SAFE = {ValidationMode.CONTRACT, ValidationMode.DETERMINISTIC, ValidationMode.SANDBOX}


@dataclass
class LiveTarget:
    connector_id: str
    operation: str
    mode: ValidationMode
    read_only: bool
    requires_approval: bool
    cleanup_required: bool = False
    data_sensitivity: str = "low"
    credential_env: str = ""     # env var whose presence gates live runs

    def configured(self) -> bool:
        return bool(self.credential_env and os.getenv(self.credential_env))


# representative live-validation targets (Phase 20). Live modes gated on creds.
LIVE_TARGETS: list[LiveTarget] = [
    LiveTarget("gmail", "gmail.search_email", ValidationMode.LIVE_READ_ONLY, True, False, credential_env="GMAIL_OAUTH"),
    LiveTarget("gmail", "gmail.draft_email", ValidationMode.LIVE_REVERSIBLE, False, True, cleanup_required=True, credential_env="GMAIL_OAUTH"),
    LiveTarget("gmail", "gmail.send_email", ValidationMode.LIVE_SIDE_EFFECT, False, True, data_sensitivity="high", credential_env="GMAIL_OAUTH"),
    LiveTarget("gcal", "gcal.list_calendar_events", ValidationMode.LIVE_READ_ONLY, True, False, credential_env="GCAL_OAUTH"),
    LiveTarget("gcal", "gcal.create_calendar_event", ValidationMode.LIVE_REVERSIBLE, False, True, cleanup_required=True, credential_env="GCAL_OAUTH"),
    LiveTarget("github", "github.inspect_repository", ValidationMode.LIVE_READ_ONLY, True, False, credential_env="GITHUB_TOKEN"),
    LiveTarget("github", "github.create_issue", ValidationMode.LIVE_SIDE_EFFECT, False, True, credential_env="GITHUB_TOKEN"),
    LiveTarget("sqlite", "sqlite.query_database", ValidationMode.SANDBOX, True, False),
    LiveTarget("deploy", "deploy.inspect_deployment", ValidationMode.LIVE_READ_ONLY, True, False, credential_env="VERCEL_TOKEN"),
]


def verification_matrix() -> list[dict]:
    """Honest per-connector verification status. `configured=no` is NOT failure."""
    rows = []
    for c in R.all_connectors():
        targets = [t for t in LIVE_TARGETS if t.connector_id == c.connector_id]
        configured = any(t.configured() for t in targets)
        rows.append({
            "connector_id": c.connector_id,
            "implemented": True,
            "integration_status": c.integration_status,
            "configured": configured,
            "authenticated": configured,   # presence of cred == candidate; live run separate
            "live_tested": False,          # no live run executed in this environment
            "environment_blocked": (not c.local) and not configured,
            "live_modes": sorted({t.mode.value for t in targets}),
        })
    return rows


def ci_safe_targets() -> list[LiveTarget]:
    return [t for t in LIVE_TARGETS if t.mode in CI_SAFE]


def run_ci_safe(engine=None) -> dict:
    """Run only CI-safe validation (deterministic/sandbox) against real adapters.
    Never performs a live external call."""
    from saathi.connectors.platform.execution import ExecutionEngine, ExecRequest
    from saathi.connectors.platform import store as S
    eng = engine or ExecutionEngine(store=S.ConnectorStore(_tmpdb()))
    results = []
    for t in ci_safe_targets():
        aid = eng.store.add_account(owner="validator", connector_id=t.connector_id,
                                    label="ci", state="healthy") \
            if not R.get_connector(t.connector_id).local else ""
        r = eng.execute(ExecRequest(owner="validator", tool_id=t.operation,
                                    account_id=aid, args={"_fixture": "success"}))
        results.append({"operation": t.operation, "mode": t.mode.value,
                        "status": r.status})
    return {"ran": len(results), "results": results,
            "live_modes": "environment_blocked (no credentials / not authorized)"}


def _tmpdb():
    import tempfile
    return tempfile.mktemp(suffix=".db")
