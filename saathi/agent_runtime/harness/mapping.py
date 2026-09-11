"""RunState ↔ HarnessSessionState projection mapping (FM-C2 / M385).

RunState remains authoritative for platform multi-agent execution.
Harness session state is a local projection only — never overrides RunState.
"""
from __future__ import annotations

from typing import Optional

from saathi.agent_runtime.models import RunState
from saathi.agent_runtime.harness.types import HarnessSessionState


# Informative projection table (M385.4).
HARNESS_TO_RUN_STATE = {
    HarnessSessionState.CREATED: RunState.CREATED,
    HarnessSessionState.INITIALIZING: RunState.RUNNING,
    HarnessSessionState.READY: RunState.RUNNING,
    HarnessSessionState.RUNNING: RunState.RUNNING,
    HarnessSessionState.WAITING_FOR_TOOL: RunState.RUNNING,
    HarnessSessionState.WAITING_FOR_APPROVAL: RunState.AWAITING_APPROVAL,
    HarnessSessionState.CANCELLING: RunState.RUNNING,
    HarnessSessionState.CANCELLED: RunState.CANCELLED,
    HarnessSessionState.COMPLETED: RunState.COMPLETED,
    HarnessSessionState.FAILED: RunState.FAILED,
    HarnessSessionState.TIMED_OUT: RunState.TIMED_OUT,
    HarnessSessionState.CLOSED: RunState.COMPLETED,  # closed after terminal success path default
}


def project_harness_to_run_state(
    harness_state: HarnessSessionState,
    *,
    prior_terminal_run: Optional[RunState] = None,
) -> RunState:
    """Project harness state to the typical RunState.

    When the harness is CLOSED, prefer the prior terminal run state if provided
    so CLOSED after CANCELLED does not falsely project COMPLETED.
    """
    if harness_state is HarnessSessionState.CLOSED and prior_terminal_run is not None:
        return prior_terminal_run
    if harness_state is HarnessSessionState.CLOSED:
        return prior_terminal_run or RunState.COMPLETED
    return HARNESS_TO_RUN_STATE[harness_state]
