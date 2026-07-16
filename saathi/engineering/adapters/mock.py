"""Mock agent adapter — deterministic pilot/tests; no real process."""
from __future__ import annotations

import time
from typing import Any

from saathi.engineering.adapters.base import (
    AdapterLaunchError,
    AgentSessionAdapter,
    LaunchRequest,
)
from saathi.engineering.models import AgentSessionResult, SessionStatus


class MockAgentAdapter(AgentSessionAdapter):
    """Simulates a coding agent without spawning processes."""

    name = "mock"

    def __init__(
        self,
        *,
        behavior: str = "success",
        max_output_chars: int = 8000,
        fail_message: str = "mock_failure",
    ):
        super().__init__(max_output_chars=max_output_chars)
        # behavior: success | timeout | crash | usage_limit | stall
        self.behavior = behavior
        self.fail_message = fail_message

    def start(self, request: LaunchRequest, *, allowed_root: str) -> AgentSessionResult:
        self.validate_working_directory(request.working_directory, allowed_root)
        if not (request.prompt or "").strip():
            raise AdapterLaunchError("empty_prompt")
        sid = request.session_id
        now = time.time()
        status = SessionStatus.RUNNING.value
        if self.behavior == "crash":
            status = SessionStatus.CRASHED.value
        self._sessions[sid] = {
            "status": status,
            "started_at": now,
            "timeout_sec": request.timeout_sec,
            "prompt_len": len(request.prompt),
            "working_directory": str(request.working_directory),
            "ticks": 0,
            "stdout": "mock agent started\n",
            "stderr": "",
            "pid": 0,
        }
        if self.behavior == "crash":
            return AgentSessionResult(
                session_id=sid,
                status=SessionStatus.CRASHED.value,
                process_id=0,
                adapter=self.name,
                started_at=now,
                ended_at=now,
                exit_code=1,
                error=self.fail_message,
                stdout_tail=self._tail("mock agent started\n"),
            )
        return AgentSessionResult(
            session_id=sid,
            status=SessionStatus.RUNNING.value,
            process_id=0,
            adapter=self.name,
            started_at=now,
            stdout_tail=self._tail("mock agent started\n"),
        )

    def poll(self, session_id: str) -> AgentSessionResult:
        s = self._sessions.get(session_id)
        if not s:
            return AgentSessionResult(
                session_id=session_id,
                status=SessionStatus.FAILED.value,
                error="session_not_found",
                adapter=self.name,
            )
        s["ticks"] = int(s.get("ticks", 0)) + 1
        now = time.time()
        started = float(s["started_at"])
        if self.behavior == "timeout" and s["ticks"] >= 2:
            s["status"] = SessionStatus.TIMED_OUT.value
            s["ended_at"] = now
            return AgentSessionResult(
                session_id=session_id,
                status=SessionStatus.TIMED_OUT.value,
                process_id=0,
                adapter=self.name,
                started_at=started,
                ended_at=now,
                exit_code=124,
                error="timeout",
                stdout_tail=self._tail(s.get("stdout", "")),
            )
        if self.behavior == "usage_limit" and s["ticks"] >= 2:
            s["status"] = SessionStatus.USAGE_LIMIT.value
            s["ended_at"] = now
            return AgentSessionResult(
                session_id=session_id,
                status=SessionStatus.USAGE_LIMIT.value,
                process_id=0,
                adapter=self.name,
                started_at=started,
                ended_at=now,
                usage_note="mock_usage_limit",
                error="usage_limit",
            )
        if self.behavior == "stall":
            s["status"] = SessionStatus.STALLED.value
            return AgentSessionResult(
                session_id=session_id,
                status=SessionStatus.STALLED.value,
                process_id=0,
                adapter=self.name,
                started_at=started,
                stdout_tail=self._tail(s.get("stdout", "")),
            )
        if self.behavior == "success" and s["ticks"] >= 2:
            s["status"] = SessionStatus.COMPLETED.value
            s["ended_at"] = now
            s["stdout"] = (s.get("stdout") or "") + "mock agent completed successfully\n"
            return AgentSessionResult(
                session_id=session_id,
                status=SessionStatus.COMPLETED.value,
                process_id=0,
                adapter=self.name,
                started_at=started,
                ended_at=now,
                exit_code=0,
                stdout_tail=self._tail(s["stdout"]),
            )
        s["status"] = SessionStatus.RUNNING.value
        s["stdout"] = (s.get("stdout") or "") + f"tick {s['ticks']}\n"
        return AgentSessionResult(
            session_id=session_id,
            status=SessionStatus.RUNNING.value,
            process_id=0,
            adapter=self.name,
            started_at=started,
            stdout_tail=self._tail(s.get("stdout", "")),
        )

    def request_stop(self, session_id: str, *, force: bool = False) -> AgentSessionResult:
        s = self._sessions.get(session_id)
        if not s:
            return AgentSessionResult(
                session_id=session_id,
                status=SessionStatus.FAILED.value,
                error="session_not_found",
                adapter=self.name,
            )
        now = time.time()
        s["status"] = SessionStatus.STOPPED.value
        s["ended_at"] = now
        s["force"] = force
        return AgentSessionResult(
            session_id=session_id,
            status=SessionStatus.STOPPED.value,
            process_id=0,
            adapter=self.name,
            started_at=float(s["started_at"]),
            ended_at=now,
            exit_code=-9 if force else 0,
            stdout_tail=self._tail(s.get("stdout", "")),
            error="force_stop" if force else "graceful_stop",
        )
